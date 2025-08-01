import logging
from urllib.parse import unquote

import pytest
from django.test import override_settings
from django.urls import re_path, reverse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from sentry.api.base import Endpoint
from sentry.api.bases.organization import ControlSiloOrganizationEndpoint, OrganizationEndpoint
from sentry.api.endpoints.internal.rpc import InternalRpcServiceEndpoint
from sentry.api.permissions import SentryIsAuthenticated
from sentry.models.apitoken import ApiToken
from sentry.ratelimits.config import RateLimitConfig
from sentry.silo.base import SiloMode
from sentry.testutils.cases import APITestCase
from sentry.testutils.silo import all_silo_test, assume_test_silo_mode, control_silo_test
from sentry.types.ratelimit import RateLimit, RateLimitCategory
from sentry.utils.snuba import RateLimitExceeded


class DummyEndpoint(Endpoint):
    permission_classes = (SentryIsAuthenticated,)

    def get(self, request):
        return Response({"ok": True})


class DummyFailEndpoint(Endpoint):
    permission_classes = (AllowAny,)

    def get(self, request):
        raise Exception("this is bad yo")


class SnubaRateLimitedEndpoint(Endpoint):
    permission_classes = (AllowAny,)

    def get(self, request):
        raise RateLimitExceeded(
            "Query on could not be run due to allocation policies, ... 'rejection_threshold': 40, 'quota_used': 41, ...",
            policy="ConcurrentRateLimitAllocationPolicy",
            quota_used=41,
            rejection_threshold=40,
            quota_unit="no_units",
            storage_key="test_storage_key",
        )


class RateLimitedEndpoint(Endpoint):
    permission_classes = (AllowAny,)
    enforce_rate_limit = True
    rate_limits = RateLimitConfig(
        group="foo",
        limit_overrides={
            "GET": {
                RateLimitCategory.IP: RateLimit(limit=0, window=1),
                RateLimitCategory.USER: RateLimit(limit=0, window=1),
                RateLimitCategory.ORGANIZATION: RateLimit(limit=0, window=1),
            },
        },
    )

    def get(self, request):
        raise NotImplementedError


class ConcurrentRateLimitedEndpoint(Endpoint):
    permission_classes = (AllowAny,)
    enforce_rate_limit = True
    rate_limits = RateLimitConfig(
        group="foo",
        limit_overrides={
            "GET": {
                RateLimitCategory.IP: RateLimit(limit=20, window=1, concurrent_limit=1),
                RateLimitCategory.USER: RateLimit(limit=20, window=1, concurrent_limit=1),
                RateLimitCategory.ORGANIZATION: RateLimit(limit=20, window=1, concurrent_limit=1),
            },
        },
    )

    def get(self, request):
        return Response({"ok": True})


class MyOrganizationEndpoint(OrganizationEndpoint):
    def get(self, request, organization):
        return Response({"ok": True})


class MyControlOrganizationEndpoint(ControlSiloOrganizationEndpoint):
    def get(self, request, organization_context, organization):
        return Response({"ok": True})


urlpatterns = [
    re_path(r"^/dummy$", DummyEndpoint.as_view(), name="dummy-endpoint"),
    re_path(r"^api/0/internal/test$", DummyEndpoint.as_view(), name="internal-dummy-endpoint"),
    re_path(r"^/dummyfail$", DummyFailEndpoint.as_view(), name="dummy-fail-endpoint"),
    re_path(
        r"^snubaratelimit$", SnubaRateLimitedEndpoint.as_view(), name="snuba-ratelimit-endpoint"
    ),
    re_path(r"^/dummyratelimit$", RateLimitedEndpoint.as_view(), name="ratelimit-endpoint"),
    re_path(
        r"^/dummyratelimitconcurrent$",
        ConcurrentRateLimitedEndpoint.as_view(),
        name="concurrent-ratelimit-endpoint",
    ),
    re_path(
        r"^(?P<organization_id_or_slug>[^/]+)/stats_v2/$",
        MyOrganizationEndpoint.as_view(),
        name="sentry-api-0-organization-stats-v2",
    ),
    re_path(
        r"^(?P<organization_id_or_slug>[^/]+)/members/$",
        MyControlOrganizationEndpoint.as_view(),
        name="sentry-api-0-organization-members",
    ),
    # Need to retain RPC endpoint for cross-silo calls
    re_path(
        r"^api/0/internal/rpc/(?P<service_name>\w+)/(?P<method_name>\w+)/$",
        InternalRpcServiceEndpoint.as_view(),
        name="sentry-api-0-rpc-service",
    ),
]

access_log_fields = (
    "method",
    "view",
    "response",
    "user_id",
    "is_app",
    "token_type",
    "organization_id",
    "auth_id",
    "path",
    "caller_ip",
    "user_agent",
    "rate_limited",
    "rate_limit_category",
    "request_duration_seconds",
    "group",
    "rate_limit_type",
    "concurrent_limit",
    "concurrent_requests",
    "reset_time",
    "limit",
    "remaining",
    "snuba_policy",
    "snuba_quota_unit",
    "snuba_storage_key",
    "snuba_quota_used",
    "snuba_rejection_threshold",
)


@override_settings(ROOT_URLCONF=__name__)
@override_settings(LOG_API_ACCESS=True)
class LogCaptureAPITestCase(APITestCase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self, caplog):
        self._caplog = caplog

    def assert_access_log_recorded(self):
        sentinel = object()
        for record in self.captured_logs:
            for field in access_log_fields:
                assert getattr(record, field, sentinel) != sentinel, field

    @property
    def captured_logs(self):
        return [r for r in self._caplog.records if r.name == "sentry.access.api"]

    def get_tested_log(self, **kwargs):
        tested_log_path = unquote(reverse(self.endpoint, **kwargs))
        return next(log for log in self.captured_logs if log.path == tested_log_path)


@all_silo_test
class TestAccessLogSnubaRateLimited(LogCaptureAPITestCase):
    endpoint = "snuba-ratelimit-endpoint"

    def test_access_log_snuba_rate_limited(self) -> None:
        """Test that Snuba rate limits are properly logged by access log middleware."""
        self._caplog.set_level(logging.INFO, logger="sentry")
        self.get_error_response(status_code=429)
        self.assert_access_log_recorded()

        assert self.captured_logs[0].rate_limit_type == "RateLimitType.SNUBA"
        assert self.captured_logs[0].rate_limited == "True"

        # All the types from the standard rate limit metadata should not be set
        assert self.captured_logs[0].remaining == "None"
        assert self.captured_logs[0].concurrent_limit == "None"
        assert self.captured_logs[0].concurrent_requests == "None"
        assert self.captured_logs[0].limit == "None"
        assert self.captured_logs[0].reset_time == "None"

        # Snuba rate limit specific fields should be set
        assert self.captured_logs[0].snuba_policy == "ConcurrentRateLimitAllocationPolicy"
        assert self.captured_logs[0].snuba_quota_unit == "no_units"
        assert self.captured_logs[0].snuba_storage_key == "test_storage_key"
        assert self.captured_logs[0].snuba_quota_used == "41"
        assert self.captured_logs[0].snuba_rejection_threshold == "40"


@all_silo_test
@override_settings(SENTRY_SELF_HOSTED=False)
class TestAccessLogRateLimited(LogCaptureAPITestCase):
    endpoint = "ratelimit-endpoint"

    def test_access_log_rate_limited(self) -> None:
        self._caplog.set_level(logging.INFO, logger="sentry")
        self.get_error_response(status_code=429)
        self.assert_access_log_recorded()
        # no token because the endpoint was not hit
        assert self.captured_logs[0].token_type == "None"
        assert self.captured_logs[0].limit == "0"
        assert self.captured_logs[0].remaining == "0"
        assert self.captured_logs[0].group == RateLimitedEndpoint.rate_limits.group


@all_silo_test
@override_settings(SENTRY_SELF_HOSTED=False)
class TestAccessLogConcurrentRateLimited(LogCaptureAPITestCase):
    endpoint = "concurrent-ratelimit-endpoint"

    def test_concurrent_request_finishes(self) -> None:
        self._caplog.set_level(logging.INFO, logger="sentry")
        for i in range(10):
            self.get_success_response()
        # these requests were done in succession, so we should not have any
        # rate limiting
        self.assert_access_log_recorded()
        for i in range(10):
            assert self.captured_logs[i].token_type == "None"
            assert self.captured_logs[0].group == RateLimitedEndpoint.rate_limits.group
            assert self.captured_logs[i].concurrent_requests == "1"
            assert self.captured_logs[i].concurrent_limit == "1"
            assert self.captured_logs[i].rate_limit_type == "RateLimitType.NOT_LIMITED"
            assert self.captured_logs[i].limit == "20"
            # we cannot assert on the exact amount of remaining requests because
            # we may be crossing a second boundary during our test. That would make things
            # flaky.
            assert int(self.captured_logs[i].remaining) < 20


@all_silo_test
class TestAccessLogSuccess(LogCaptureAPITestCase):
    endpoint = "dummy-endpoint"

    def test_access_log_success(self) -> None:
        self._caplog.set_level(logging.INFO, logger="sentry")
        with assume_test_silo_mode(SiloMode.CONTROL):
            token = ApiToken.objects.create(user=self.user, scope_list=["event:read", "org:read"])
        self.login_as(user=self.create_user())
        self.get_success_response(extra_headers={"HTTP_AUTHORIZATION": f"Bearer {token.token}"})
        self.assert_access_log_recorded()
        tested_log = self.get_tested_log()
        assert tested_log.token_type == "api_token"
        assert tested_log.token_last_characters == token.token_last_characters

    def test_with_subdomain_redirect(self) -> None:
        # the subdomain middleware is in between this and the access log middelware
        # meaning if a request is rejected between those then it will not have `auth`
        # set up properly
        # this previously logged an error to sentry
        resp = self.get_response(extra_headers={"HTTP_HOST": "invalid_domain.testserver"})
        assert resp.status_code == 302
        records = [record for record in self._caplog.records if record.levelno == logging.ERROR]
        assert not records  # no errors should occur


@all_silo_test
@override_settings(LOG_API_ACCESS=False)
class TestAccessLogSuccessNotLoggedInDev(LogCaptureAPITestCase):
    endpoint = "dummy-endpoint"

    def test_access_log_success(self) -> None:
        token = None
        with assume_test_silo_mode(SiloMode.CONTROL):
            token = ApiToken.objects.create(user=self.user, scope_list=["event:read", "org:read"])
        self.login_as(user=self.create_user())
        self.get_success_response(extra_headers={"HTTP_AUTHORIZATION": f"Bearer {token.token}"})
        assert len(self.captured_logs) == 0


@all_silo_test
class TestAccessLogSkippedForExcludedPath(LogCaptureAPITestCase):
    endpoint = "internal-dummy-endpoint"

    def test_access_log_skipped(self) -> None:
        self._caplog.set_level(logging.INFO, logger="sentry")
        token = None
        with assume_test_silo_mode(SiloMode.CONTROL):
            token = ApiToken.objects.create(user=self.user, scope_list=["event:read", "org:read"])
        self.login_as(user=self.create_user())
        self.get_success_response(extra_headers={"HTTP_AUTHORIZATION": f"Bearer {token.token}"})
        assert len(self.captured_logs) == 0


@all_silo_test
class TestAccessLogFail(LogCaptureAPITestCase):
    endpoint = "dummy-fail-endpoint"

    def test_access_log_fail(self) -> None:
        self.get_error_response(status_code=500)
        self.assert_access_log_recorded()


class TestOrganizationIdPresentForRegion(LogCaptureAPITestCase):
    endpoint = "sentry-api-0-organization-stats-v2"

    def setUp(self) -> None:
        self.login_as(user=self.user)

    def test_org_id_populated(self) -> None:
        self._caplog.set_level(logging.INFO, logger="sentry")
        self.get_success_response(
            self.organization.slug,
            qs_params={
                "project": [-1],
                "category": ["error"],
                "statsPeriod": "1d",
                "interval": "1d",
                "field": ["sum(quantity)"],
            },
        )

        tested_log = self.get_tested_log(args=[self.organization.slug])
        assert tested_log.organization_id == str(self.organization.id)


@control_silo_test
class TestOrganizationIdPresentForControl(LogCaptureAPITestCase):
    endpoint = "sentry-api-0-organization-members"

    def setUp(self) -> None:
        self.login_as(user=self.user)

    def test_org_id_populated(self) -> None:
        self._caplog.set_level(logging.INFO, logger="sentry")
        self.get_success_response(
            self.organization.slug,
            qs_params={
                "project": [-1],
                "category": ["error"],
                "statsPeriod": "1d",
                "interval": "1d",
                "field": ["sum(quantity)"],
            },
        )

        tested_log = self.get_tested_log(args=[self.organization.slug])
        assert tested_log.organization_id == str(self.organization.id)
