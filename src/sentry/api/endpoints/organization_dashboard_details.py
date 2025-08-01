import sentry_sdk
from django.db import IntegrityError, router, transaction
from django.db.models import F
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from sentry import features
from sentry.api.api_owners import ApiOwner
from sentry.api.api_publish_status import ApiPublishStatus
from sentry.api.base import region_silo_endpoint
from sentry.api.bases.organization import OrganizationEndpoint
from sentry.api.endpoints.organization_dashboards import OrganizationDashboardsPermission
from sentry.api.exceptions import ResourceDoesNotExist
from sentry.api.serializers import serialize
from sentry.api.serializers.models.dashboard import DashboardDetailsModelSerializer
from sentry.api.serializers.rest_framework import DashboardDetailsSerializer
from sentry.apidocs.constants import (
    RESPONSE_BAD_REQUEST,
    RESPONSE_FORBIDDEN,
    RESPONSE_NO_CONTENT,
    RESPONSE_NOT_FOUND,
)
from sentry.apidocs.examples.dashboard_examples import DashboardExamples
from sentry.apidocs.parameters import DashboardParams, GlobalParams
from sentry.models.dashboard import (
    Dashboard,
    DashboardFavoriteUser,
    DashboardLastVisited,
    DashboardTombstone,
)
from sentry.models.organization import Organization
from sentry.models.organizationmember import OrganizationMember

EDIT_FEATURE = "organizations:dashboards-edit"
READ_FEATURE = "organizations:dashboards-basic"


class OrganizationDashboardBase(OrganizationEndpoint):
    owner = ApiOwner.PERFORMANCE
    permission_classes = (OrganizationDashboardsPermission,)

    def convert_args(
        self, request: Request, organization_id_or_slug, dashboard_id, *args, **kwargs
    ):
        args, kwargs = super().convert_args(request, organization_id_or_slug, *args, **kwargs)

        try:
            kwargs["dashboard"] = self._get_dashboard(request, kwargs["organization"], dashboard_id)
        except (Dashboard.DoesNotExist, ValueError):
            raise ResourceDoesNotExist

        return (args, kwargs)

    def _get_dashboard(self, request: Request, organization, dashboard_id):
        prebuilt = Dashboard.get_prebuilt(organization, request.user, dashboard_id)
        sentry_sdk.set_tag("dashboard.is_prebuilt", prebuilt is not None)
        if prebuilt:
            return prebuilt
        return Dashboard.objects.get(id=dashboard_id, organization_id=organization.id)


@extend_schema(tags=["Dashboards"])
@region_silo_endpoint
class OrganizationDashboardDetailsEndpoint(OrganizationDashboardBase):
    publish_status = {
        "DELETE": ApiPublishStatus.PUBLIC,
        "GET": ApiPublishStatus.PUBLIC,
        "PUT": ApiPublishStatus.PUBLIC,
    }

    @extend_schema(
        operation_id="Retrieve an Organization's Custom Dashboard",
        parameters=[GlobalParams.ORG_ID_OR_SLUG, DashboardParams.DASHBOARD_ID],
        responses={
            200: DashboardDetailsModelSerializer,
            403: RESPONSE_FORBIDDEN,
            404: RESPONSE_NOT_FOUND,
        },
        examples=DashboardExamples.DASHBOARD_GET_RESPONSE,
    )
    def get(self, request: Request, organization, dashboard) -> Response:
        """
        Return details about an organization's custom dashboard.
        """
        if not features.has(READ_FEATURE, organization, actor=request.user):
            return Response(status=404)

        if isinstance(dashboard, dict):
            return self.respond(dashboard)

        return self.respond(serialize(dashboard, request.user))

    @extend_schema(
        operation_id="Delete an Organization's Custom Dashboard",
        parameters=[GlobalParams.ORG_ID_OR_SLUG, DashboardParams.DASHBOARD_ID],
        responses={
            204: RESPONSE_NO_CONTENT,
            403: RESPONSE_FORBIDDEN,
            404: RESPONSE_NOT_FOUND,
        },
    )
    def delete(self, request: Request, organization, dashboard) -> Response:
        """
        Delete an organization's custom dashboard, or tombstone
        a pre-built dashboard which effectively deletes it.
        """
        if not features.has(EDIT_FEATURE, organization, actor=request.user):
            return Response(status=404)

        self.check_object_permissions(request, dashboard)

        num_dashboards = Dashboard.objects.filter(organization=organization).count()
        num_tombstones = DashboardTombstone.objects.filter(organization=organization).count()

        if isinstance(dashboard, dict):
            if num_dashboards > 0:
                DashboardTombstone.objects.get_or_create(
                    organization=organization, slug=dashboard["id"]
                )
            else:
                return self.respond({"Cannot delete last Dashboard."}, status=409)
        elif (num_dashboards > 1) or (num_tombstones == 0):
            dashboard.delete()
        else:
            return self.respond({"Cannot delete last Dashboard."}, status=409)

        return self.respond(status=204)

    @extend_schema(
        operation_id="Edit an Organization's Custom Dashboard",
        parameters=[GlobalParams.ORG_ID_OR_SLUG, DashboardParams.DASHBOARD_ID],
        request=DashboardDetailsSerializer,
        responses={
            200: DashboardDetailsModelSerializer,
            400: RESPONSE_BAD_REQUEST,
            403: RESPONSE_FORBIDDEN,
            404: RESPONSE_NOT_FOUND,
        },
        examples=DashboardExamples.DASHBOARD_PUT_RESPONSE,
    )
    def put(self, request: Request, organization: Organization, dashboard) -> Response:
        """
        Edit an organization's custom dashboard as well as any bulk
        edits on widgets that may have been made. (For example, widgets
        that have been rearranged, updated queries and fields, specific
        display types, and so on.)
        """
        if not features.has(EDIT_FEATURE, organization, actor=request.user):
            return Response(status=404)

        self.check_object_permissions(request, dashboard)

        tombstone = None
        if isinstance(dashboard, dict):
            tombstone = dashboard["id"]
            dashboard = None

        serializer = DashboardDetailsSerializer(
            data=request.data,
            instance=dashboard,
            context={
                "organization": organization,
                "request": request,
                "projects": self.get_projects(request, organization),
                "environment": self.request.GET.getlist("environment"),
            },
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        try:
            with transaction.atomic(router.db_for_write(DashboardTombstone)):
                serializer.save()
                if tombstone:
                    DashboardTombstone.objects.get_or_create(
                        organization=organization, slug=tombstone
                    )
        except IntegrityError:
            return self.respond({"Dashboard with that title already exists."}, status=409)

        return self.respond(serialize(serializer.instance, request.user), status=200)


@region_silo_endpoint
class OrganizationDashboardVisitEndpoint(OrganizationDashboardBase):
    publish_status = {
        "POST": ApiPublishStatus.PRIVATE,
    }

    def post(self, request: Request, organization, dashboard) -> Response:
        """
        Update last_visited and increment visits counter
        """
        if not features.has(EDIT_FEATURE, organization, actor=request.user):
            return Response(status=404)

        if isinstance(dashboard, dict):
            return Response(status=204)

        dashboard.visits = F("visits") + 1
        dashboard.last_visited = timezone.now()
        dashboard.save(update_fields=["visits", "last_visited"])

        org_member = OrganizationMember.objects.filter(
            user_id=request.user.pk, organization_id=organization.id
        ).first()
        if not org_member:
            return Response(status=403)

        DashboardLastVisited.objects.create_or_update(
            dashboard=dashboard,
            member=org_member,
            values={"last_visited": timezone.now()},
        )

        return Response(status=204)


@region_silo_endpoint
class OrganizationDashboardFavoriteEndpoint(OrganizationDashboardBase):
    """
    Endpoint for managing the favorite status of dashboards for users
    """

    publish_status = {
        "PUT": ApiPublishStatus.PRIVATE,
    }

    def put(self, request: Request, organization: Organization, dashboard) -> Response:
        """
        Toggle favorite status for current user by adding or removing
        current user from dashboard favorites
        """
        if not features.has(EDIT_FEATURE, organization, actor=request.user):
            return Response(status=404)

        if not request.user.is_authenticated:
            return Response(status=401)

        if isinstance(dashboard, dict):
            return Response(status=204)

        is_favorited = request.data.get("isFavorited")

        if features.has(
            "organizations:dashboards-starred-reordering", organization, actor=request.user
        ):
            if is_favorited:
                DashboardFavoriteUser.objects.insert_favorite_dashboard(
                    organization=organization,
                    user_id=request.user.id,
                    dashboard=dashboard,
                )
            else:
                DashboardFavoriteUser.objects.delete_favorite_dashboard(
                    organization=organization,
                    user_id=request.user.id,
                    dashboard=dashboard,
                )
            return Response(status=204)

        current_favorites = set(dashboard.favorited_by)

        if is_favorited and request.user.id not in current_favorites:
            current_favorites.add(request.user.id)
        elif not is_favorited and request.user.id in current_favorites:
            current_favorites.remove(request.user.id)
        else:
            return Response(status=204)

        dashboard.favorited_by = current_favorites

        return Response(status=204)
