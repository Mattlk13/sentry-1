from __future__ import annotations

import abc
import functools
import logging
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict
from urllib.parse import quote as urlquote

import sentry_sdk
from django.conf import settings
from django.http import HttpResponse
from django.http.request import HttpRequest
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.exceptions import ParseError
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from sentry_sdk import Scope

from sentry import analytics, options, tsdb
from sentry.analytics.events.release_set_commits import ReleaseSetCommitsLocalEvent
from sentry.api.api_owners import ApiOwner
from sentry.api.api_publish_status import ApiPublishStatus
from sentry.api.exceptions import StaffRequired, SuperuserRequired
from sentry.apidocs.hooks import HTTP_METHOD_NAME
from sentry.auth import access
from sentry.auth.staff import has_staff_option
from sentry.middleware import is_frontend_request
from sentry.organizations.absolute_url import generate_organization_url
from sentry.ratelimits.config import DEFAULT_RATE_LIMIT_CONFIG, RateLimitConfig
from sentry.silo.base import SiloLimit, SiloMode
from sentry.snuba.query_sources import QuerySource
from sentry.types.ratelimit import RateLimit, RateLimitCategory
from sentry.utils.audit import create_audit_entry
from sentry.utils.cursors import Cursor
from sentry.utils.dates import to_datetime
from sentry.utils.http import (
    absolute_uri,
    is_using_customer_domain,
    is_valid_origin,
    origin_from_request,
)
from sentry.utils.sdk import capture_exception, merge_context_into_scope

from ..utils.pagination_factory import (
    annotate_span_with_pagination_args,
    clamp_pagination_per_page,
    get_cursor,
    get_paginator,
)
from .authentication import (
    ApiKeyAuthentication,
    OrgAuthTokenAuthentication,
    UserAuthTokenAuthentication,
    update_token_access_record,
)
from .paginator import BadPaginationError, MissingPaginationError, Paginator
from .permissions import (
    NoPermission,
    StaffPermission,
    SuperuserOrStaffFeatureFlaggedPermission,
    SuperuserPermission,
)

__all__ = [
    "Endpoint",
    "StatsMixin",
    "control_silo_endpoint",
    "region_silo_endpoint",
]

PAGINATION_DEFAULT_PER_PAGE = 100

ONE_MINUTE = 60
ONE_HOUR = ONE_MINUTE * 60
ONE_DAY = ONE_HOUR * 24

CURSOR_LINK_HEADER = (
    '<{uri}&cursor={cursor}>; rel="{name}"; results="{has_results}"; cursor="{cursor}"'
)

DEFAULT_AUTHENTICATION = (
    UserAuthTokenAuthentication,
    OrgAuthTokenAuthentication,
    ApiKeyAuthentication,
    SessionAuthentication,
)

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("sentry.audit.api")
api_access_logger = logging.getLogger("sentry.access.api")


def allow_cors_options(func):
    """
    Decorator that adds automatic handling of OPTIONS requests for CORS

    If the request is OPTIONS (i.e. pre flight CORS) construct a OK (200) response
    in which we explicitly enable the caller and add the custom headers that we support
    For other requests just add the appropriate CORS headers

    :param func: the original request handler
    :return: a request handler that shortcuts OPTIONS requests and just returns an OK (CORS allowed)
    """

    @functools.wraps(func)
    def allow_cors_options_wrapper(self, request: Request, *args, **kwargs):
        if request.method == "OPTIONS":
            response = HttpResponse(status=200)
            response["Access-Control-Max-Age"] = "3600"  # don't ask for options again for 1 hour
        else:
            response = func(self, request, *args, **kwargs)

        return apply_cors_headers(
            request=request, response=response, allowed_methods=self._allowed_methods()
        )

    return allow_cors_options_wrapper


def apply_cors_headers(
    request: HttpRequest, response: HttpResponse, allowed_methods: list[str] | None = None
) -> HttpResponse:
    if allowed_methods is None:
        allowed_methods = []
    allow = ", ".join(allowed_methods)
    if not allow or "*" in allow:
        with sentry_sdk.isolation_scope() as scope:
            scope.set_level("warning")
            scope.set_context(
                "cors_headers",
                {
                    "url": request.path,
                    "method": request.method,
                    "origin": request.META.get("HTTP_ORIGIN", ""),
                    "allow": allow,
                },
            )
            sentry_sdk.capture_message("api.cors.no_methods")

    response["Allow"] = allow
    response["Access-Control-Allow-Methods"] = allow
    response["Access-Control-Allow-Headers"] = (
        "X-Sentry-Auth, X-Requested-With, Origin, Accept, "
        "Content-Type, Authentication, Authorization, Content-Encoding, "
        "sentry-trace, baggage, X-CSRFToken"
    )
    response["Access-Control-Expose-Headers"] = (
        "X-Sentry-Error, X-Sentry-Direct-Hit, X-Hits, X-Max-Hits, Endpoint, Retry-After, Link"
    )

    if request.META.get("HTTP_ORIGIN") == "null":
        # if ORIGIN header is explicitly specified as 'null' leave it alone
        origin: str | None = "null"
    else:
        origin = origin_from_request(request)

    if origin is None or origin == "null":
        response["Access-Control-Allow-Origin"] = "*"
    else:
        response["Access-Control-Allow-Origin"] = origin

    # If the requesting origin is a subdomain of
    # the application's base-hostname we should allow cookies
    # to be sent.
    basehost = options.get("system.base-hostname")
    if basehost and origin:
        if "," not in origin and (
            origin.endswith(("://" + basehost, "." + basehost))
            or origin in settings.ALLOWED_CREDENTIAL_ORIGINS
        ):
            response["Access-Control-Allow-Credentials"] = "true"

    return response


class BaseEndpointMixin(abc.ABC):
    """
    Inherit from this class when adding mixin classes that call `Endpoint` methods. This allows typing to
    work correctly
    """

    @abc.abstractmethod
    def create_audit_entry(
        self, request: Request, transaction_id=None, *, data: dict[str, Any], **kwargs
    ):
        pass

    @abc.abstractmethod
    def respond(self, context: object | None = None, **kwargs: Any) -> Response:
        pass

    @abc.abstractmethod
    def paginate(
        self,
        request,
        on_results=None,
        paginator=None,
        paginator_cls=Paginator,
        default_per_page: int | None = None,
        max_per_page: int | None = None,
        cursor_cls=Cursor,
        response_cls=Response,
        response_kwargs=None,
        count_hits=None,
        **paginator_kwargs,
    ):
        pass


class Endpoint(APIView):
    # Note: the available renderer and parser classes can be found in conf/server.py.
    authentication_classes: tuple[type[BaseAuthentication], ...] = DEFAULT_AUTHENTICATION
    permission_classes: tuple[type[BasePermission], ...] = (NoPermission,)

    cursor_name = "cursor"

    owner: ApiOwner = ApiOwner.UNOWNED
    publish_status: dict[HTTP_METHOD_NAME, ApiPublishStatus] = {}
    rate_limits: (
        RateLimitConfig
        | dict[str, dict[RateLimitCategory, RateLimit]]
        | Callable[..., RateLimitConfig | dict[str, dict[RateLimitCategory, RateLimit]]]
    ) = DEFAULT_RATE_LIMIT_CONFIG
    enforce_rate_limit: bool = settings.SENTRY_RATELIMITER_ENABLED

    def build_cursor_link(self, request: HttpRequest, name: str, cursor: Cursor) -> str:
        if request.GET.get("cursor") is None:
            querystring = request.GET.urlencode()
        else:
            mutable_query_dict = request.GET.copy()
            mutable_query_dict.pop("cursor")
            querystring = mutable_query_dict.urlencode()

        url_prefix = (
            generate_organization_url(request.subdomain)
            if is_using_customer_domain(request)
            else None
        )
        base_url = absolute_uri(urlquote(request.path), url_prefix=url_prefix)

        if querystring:
            base_url = f"{base_url}?{querystring}"
        else:
            base_url = f"{base_url}?"

        return CURSOR_LINK_HEADER.format(
            uri=base_url,
            cursor=str(cursor),
            name=name,
            has_results="true" if bool(cursor) else "false",
        )

    def convert_args(self, request: Request, *args, **kwargs):
        return (args, kwargs)

    def permission_denied(self, request, message=None, code=None):
        """
        Raise a specific superuser exception if the user can become superuser
        and the only permission class is SuperuserPermission. Otherwise, raises
        the appropriate exception according to parent DRF function.
        """
        permissions = self.get_permissions()
        if request.user.is_authenticated and len(permissions) == 1:
            permission_cls = permissions[0]
            enforce_staff_permission = has_staff_option(request.user)

            # TODO(schew2381): Remove SuperuserOrStaffFeatureFlaggedPermission
            # from isinstance checks once feature flag is removed.
            if enforce_staff_permission:
                is_staff_user = request.user.is_staff
                has_only_staff_permission = isinstance(
                    permission_cls, (StaffPermission, SuperuserOrStaffFeatureFlaggedPermission)
                )

                if is_staff_user and has_only_staff_permission:
                    raise StaffRequired()
            else:
                is_superuser_user = request.user.is_superuser
                has_only_superuser_permission = isinstance(
                    permission_cls, (SuperuserPermission, SuperuserOrStaffFeatureFlaggedPermission)
                )

                if is_superuser_user and has_only_superuser_permission:
                    raise SuperuserRequired()

        super().permission_denied(request, message, code)

    def handle_exception_with_details(
        self,
        request: Request,
        exc: Exception,
        handler_context: Mapping[str, Any] | None = None,
        scope: Scope | None = None,
    ) -> Response:
        """
        Handle exceptions which arise while processing incoming API requests.

        :param request:          The incoming request.
        :param exc:              The exception raised during handling.
        :param handler_context:  (Optional) Extra data which will be attached to the event sent to
                                 Sentry, under the "Request Handler Data" heading.
        :param scope:            (Optional) A `Scope` object containing extra data which will be
                                 attached to the event sent to Sentry.

        :returns: A 500 response including the event id of the captured Sentry event.
        """
        try:
            # Django REST Framework's built-in exception handler. If `settings.EXCEPTION_HANDLER`
            # exists and returns a response, that's used. Otherwise, `exc` is just re-raised
            # and caught below.
            response = self.handle_exception(exc)
        except Exception as err:
            import sys
            import traceback

            sys.stderr.write(traceback.format_exc())

            scope = scope or sentry_sdk.Scope()
            if handler_context:
                merge_context_into_scope("Request Handler Data", handler_context, scope)
            event_id = capture_exception(err, scope=scope)

            response_body = {"detail": "Internal Error", "errorId": event_id}
            response = Response(response_body, status=500)
            response.exception = True

        return response

    def create_audit_entry(
        self, request: Request, transaction_id=None, *, data: dict[str, Any], **kwargs
    ):
        return create_audit_entry(request, transaction_id, audit_logger, data=data, **kwargs)

    def initialize_request(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Request:
        # XXX: Since DRF 3.x, when the request is passed into
        # `initialize_request` it's set as an internal variable on the returned
        # request. Then when we call `rv.auth` it attempts to authenticate,
        # fails and sets `user` and `auth` to None on the internal request. We
        # keep track of these here and reassign them as needed.
        orig_auth = getattr(request, "auth", None)
        orig_user = getattr(request, "user", None)
        rv = super().initialize_request(request, *args, **kwargs)
        # If our request is being made via our internal API client, we need to
        # stitch back on auth and user information
        if getattr(request, "__from_api_client__", False):
            if rv.auth is None:
                rv.auth = orig_auth
            if rv.user is None:
                rv.user = orig_user  # type: ignore[unreachable]  # the request here is partially initialized
        return rv

    def has_pagination(self, response: Response) -> bool:
        # If response is paginated, it will have a "Link" header
        return response.headers.get("Link") is not None

    @csrf_exempt
    @allow_cors_options
    def dispatch(self, request: Request, *args, **kwargs) -> Response:
        """
        Identical to rest framework's dispatch except we add the ability
        to convert arguments (for common URL params).
        """
        with sentry_sdk.start_span(op="base.dispatch.setup", name=type(self).__name__):
            self.args = args
            self.kwargs = kwargs
            request = self.initialize_request(request, *args, **kwargs)
            # XXX: without this seemingly useless access to `.body` we are
            # unable to access `request.body` later on due to `rest_framework`
            # loading the request body via `request.read()`
            request.body
            self.request = request
            self.headers = self.default_response_headers  # deprecate?

        if request.META.get("HTTP_REFERER"):
            sentry_sdk.set_tag("http.referer", request.META.get("HTTP_REFERER"))

        start_time = time.time()

        origin = request.META.get("HTTP_ORIGIN", "null")
        # A "null" value should be treated as no Origin for us.
        # See RFC6454 for more information on this behavior.
        if origin == "null":
            origin = None

        try:
            with sentry_sdk.start_span(op="base.dispatch.request", name=type(self).__name__):
                if origin:
                    if request.auth:
                        allowed_origins = request.auth.get_allowed_origins()
                    else:
                        allowed_origins = None
                    if not is_valid_origin(origin, allowed=allowed_origins):
                        response = Response(f"Invalid origin: {origin}", status=400)
                        self.response = self.finalize_response(request, response, *args, **kwargs)
                        return self.response

                if request.auth:
                    update_token_access_record(request.auth)

                self.initial(request, *args, **kwargs)

                if getattr(request, "access", None) is None:
                    # setup default access
                    request.access = access.from_request(request)

                # Get the appropriate handler method
                assert request.method is not None
                method = request.method.lower()
                if method in self.http_method_names and hasattr(self, method):
                    handler = getattr(self, method)

                    # Only convert args when using defined handlers
                    (args, kwargs) = self.convert_args(request, *args, **kwargs)
                    self.args = args
                    self.kwargs = kwargs
                else:
                    handler = self.http_method_not_allowed

            with sentry_sdk.start_span(
                op="base.dispatch.execute",
                name=".".join(
                    getattr(part, "__name__", None) or str(part) for part in (type(self), handler)
                ),
            ) as span:
                response = handler(request, *args, **kwargs)

        except Exception as exc:
            response = self.handle_exception_with_details(request, exc)

        if origin:
            self.add_cors_headers(request, response)

        self.response = self.finalize_response(request, response, *args, **kwargs)

        if settings.SENTRY_API_RESPONSE_DELAY:
            duration = time.time() - start_time

            if duration < (settings.SENTRY_API_RESPONSE_DELAY / 1000.0):
                with sentry_sdk.start_span(
                    op="base.dispatch.sleep",
                    name=type(self).__name__,
                ) as span:
                    span.set_data("SENTRY_API_RESPONSE_DELAY", settings.SENTRY_API_RESPONSE_DELAY)
                    time.sleep(settings.SENTRY_API_RESPONSE_DELAY / 1000.0 - duration)

        # Only enforced in dev environment
        if settings.ENFORCE_PAGINATION:
            assert request.method is not None
            if request.method.lower() == "get":
                status = getattr(self.response, "status_code", 0)
                # Response can either be Response or HttpResponse, check if
                # it's value is an array and that it was an OK response
                if (
                    200 <= status < 300
                    and hasattr(self.response, "data")
                    and isinstance(self.response.data, list)
                ):
                    # if not paginated and not in  settings.SENTRY_API_PAGINATION_ALLOWLIST, raise error
                    if (
                        handler.__self__.__class__.__name__
                        not in settings.SENTRY_API_PAGINATION_ALLOWLIST
                        and not self.has_pagination(self.response)
                    ):
                        raise MissingPaginationError(handler.__func__.__qualname__)
        return self.response

    def add_cors_headers(self, request: Request, response):
        response["Access-Control-Allow-Origin"] = request.META["HTTP_ORIGIN"]
        response["Access-Control-Allow-Methods"] = ", ".join(self.http_method_names)

    def add_cursor_headers(self, request: Request, response, cursor_result):
        if cursor_result.hits is not None:
            response["X-Hits"] = cursor_result.hits
        if cursor_result.max_hits is not None:
            response["X-Max-Hits"] = cursor_result.max_hits
        response["Link"] = ", ".join(
            [
                self.build_cursor_link(request, "previous", cursor_result.prev),
                self.build_cursor_link(request, "next", cursor_result.next),
            ]
        )

    def respond(self, context: object | None = None, **kwargs: Any) -> Response:
        return Response(context, **kwargs)

    def respond_with_text(self, text):
        return self.respond({"text": text})

    def get_per_page(
        self, request: Request, default_per_page: int | None = None, max_per_page: int | None = None
    ):
        default_per_page = default_per_page or PAGINATION_DEFAULT_PER_PAGE
        max_per_page = max_per_page or 100

        try:
            return clamp_pagination_per_page(
                request.GET.get("per_page", default_per_page),
                default_per_page=default_per_page,
                max_per_page=max_per_page,
            )
        except ValueError as e:
            raise ParseError(detail=str(e))

    def get_cursor_from_request(self, request: Request, cursor_cls=Cursor):
        try:
            return get_cursor(request.GET.get(self.cursor_name), cursor_cls)
        except ValueError as e:
            raise ParseError(detail=str(e))

    def paginate(
        self,
        request,
        on_results=None,
        paginator=None,
        paginator_cls=Paginator,
        default_per_page: int | None = None,
        max_per_page: int | None = None,
        cursor_cls=Cursor,
        response_cls=Response,
        response_kwargs=None,
        count_hits=None,
        **paginator_kwargs,
    ):
        try:
            per_page = self.get_per_page(request, default_per_page, max_per_page)
            cursor = self.get_cursor_from_request(request, cursor_cls)
            with sentry_sdk.start_span(
                op="base.paginate.get_result",
                name=type(self).__name__,
            ) as span:
                annotate_span_with_pagination_args(span, per_page)
                paginator = get_paginator(paginator, paginator_cls, paginator_kwargs)
                result_args = dict(count_hits=count_hits) if count_hits is not None else dict()
                cursor_result = paginator.get_result(
                    limit=per_page,
                    cursor=cursor,
                    **result_args,
                )
        except BadPaginationError as e:
            raise ParseError(detail=str(e))

        if response_kwargs is None:
            response_kwargs = {}

        # map results based on callback
        if on_results:
            with sentry_sdk.start_span(
                op="base.paginate.on_results",
                name=type(self).__name__,
            ):
                results = on_results(cursor_result.results)
        else:
            results = cursor_result.results

        response = response_cls(results, **response_kwargs)
        self.add_cursor_headers(request, response, cursor_result)
        return response

    def get_request_source(self, request: Request) -> QuerySource:
        """
        This is an estimate of query source. Treat it more like a good guess and
        don't write logic that depends on it. Used for monitoring only atm.
        """
        if is_frontend_request(request):
            return QuerySource.FRONTEND
        return QuerySource.API


class StatsArgsDict(TypedDict):
    start: datetime
    end: datetime
    rollup: int
    environment_ids: list[int]


class StatsMixin:
    def _parse_args(
        self, request: Request, environment_id=None, restrict_rollups=True
    ) -> StatsArgsDict:
        """
        Parse common stats parameters from the query string. This includes
        `since`, `until`, and `resolution`.

        :param boolean restrict_rollups: When False allows any rollup value to
        be specified. Be careful using this as this allows for fine grain
        rollups that may put strain on the system.
        """
        try:
            resolution_s = request.GET.get("resolution")
            if resolution_s:
                resolution = self._parse_resolution(resolution_s)
                if restrict_rollups and resolution not in tsdb.backend.get_rollups():
                    raise ValueError
            else:
                resolution = None
        except ValueError:
            raise ParseError(detail="Invalid resolution")

        try:
            end_s = request.GET.get("until")
            if end_s:
                end = to_datetime(float(end_s))
            else:
                end = datetime.now(timezone.utc)
        except ValueError:
            raise ParseError(detail="until must be a numeric timestamp.")

        try:
            start_s = request.GET.get("since")
            if start_s:
                start = to_datetime(float(start_s))
                assert start <= end
            else:
                start = end - timedelta(days=1, seconds=-1)
        except ValueError:
            raise ParseError(detail="since must be a numeric timestamp")
        except AssertionError:
            raise ParseError(detail="start must be before or equal to end")

        if not resolution:
            resolution = tsdb.backend.get_optimal_rollup(start, end)

        return {
            "start": start,
            "end": end,
            "rollup": resolution,
            "environment_ids": environment_id and [environment_id],
        }

    def _parse_resolution(self, value: str) -> int:
        if value.endswith("h"):
            return int(value[:-1]) * ONE_HOUR
        elif value.endswith("d"):
            return int(value[:-1]) * ONE_DAY
        elif value.endswith("m"):
            return int(value[:-1]) * ONE_MINUTE
        elif value.endswith("s"):
            return int(value[:-1])
        else:
            raise ValueError(value)


class ReleaseAnalyticsMixin:
    def track_set_commits_local(self, request: Request, organization_id=None, project_ids=None):
        try:
            analytics.record(
                ReleaseSetCommitsLocalEvent(
                    user_id=request.user.id if request.user and request.user.id else None,
                    organization_id=organization_id,
                    project_ids=project_ids,
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)


class EndpointSiloLimit(SiloLimit):
    def modify_endpoint_class(self, decorated_class: type[Endpoint]) -> type:
        dispatch_override = self.create_override(decorated_class.dispatch)
        new_class = type(
            decorated_class.__name__,
            (decorated_class,),
            {
                "dispatch": dispatch_override,
                "silo_limit": self,
            },
        )
        new_class.__module__ = decorated_class.__module__
        return new_class

    def modify_endpoint_method(self, decorated_method: Callable[..., Any]) -> Callable[..., Any]:
        return self.create_override(decorated_method)

    def handle_when_unavailable(
        self,
        original_method: Callable[..., Any],
        current_mode: SiloMode,
        available_modes: Iterable[SiloMode],
    ) -> Callable[..., Any]:
        def handle(obj: Any, request: Request, *args: Any, **kwargs: Any) -> HttpResponse:
            mode_str = ", ".join(str(m) for m in available_modes)
            message = (
                f"Received {request.method} request at {request.path!r} to server in "
                f"{current_mode} mode. This endpoint is available only in: {mode_str}"
            )
            if settings.FAIL_ON_UNAVAILABLE_API_CALL:
                raise self.AvailabilityError(message)
            else:
                logger.warning(message)
                return HttpResponse(status=status.HTTP_404_NOT_FOUND)

        return handle

    def __call__(self, decorated_obj: Any) -> Any:
        if isinstance(decorated_obj, type):
            if not issubclass(decorated_obj, Endpoint):
                raise ValueError("`@EndpointSiloLimit` can decorate only Endpoint subclasses")
            return self.modify_endpoint_class(decorated_obj)

        if callable(decorated_obj):
            return self.modify_endpoint_method(decorated_obj)

        raise TypeError("`@EndpointSiloLimit` must decorate a class or method")


control_silo_endpoint = EndpointSiloLimit(SiloMode.CONTROL)
"""
Apply to endpoints that exist in CONTROL silo.
If a request is received and the application is not in CONTROL
mode 404s will be returned.
"""

region_silo_endpoint = EndpointSiloLimit(SiloMode.REGION)
"""
Apply to endpoints that exist in REGION silo.
If a request is received and the application is not in REGION
mode 404s will be returned.
"""

all_silo_endpoint = EndpointSiloLimit(SiloMode.CONTROL, SiloMode.REGION, SiloMode.MONOLITH)
"""
Apply to endpoints that are available in all silo modes.

This should be rarely used, but is relevant for resources like ROBOTS.txt.
"""
