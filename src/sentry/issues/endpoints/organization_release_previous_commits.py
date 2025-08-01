import sentry_sdk
from rest_framework.request import Request
from rest_framework.response import Response

from sentry import analytics
from sentry.analytics.events.release_get_previous_commits import ReleaseGetPreviousCommitsEvent
from sentry.api.api_owners import ApiOwner
from sentry.api.api_publish_status import ApiPublishStatus
from sentry.api.base import region_silo_endpoint
from sentry.api.bases.organization import OrganizationReleasesBaseEndpoint
from sentry.api.exceptions import ResourceDoesNotExist
from sentry.api.serializers import serialize
from sentry.models.organization import Organization
from sentry.models.release import Release
from sentry.ratelimits.config import RateLimitConfig


@region_silo_endpoint
class OrganizationReleasePreviousCommitsEndpoint(OrganizationReleasesBaseEndpoint):
    publish_status = {
        "GET": ApiPublishStatus.PRIVATE,
    }
    owner = ApiOwner.ISSUES
    rate_limits = RateLimitConfig(group="CLI")

    def get(self, request: Request, organization: Organization, version: str) -> Response:
        """
        Retrieve an Organization's Most Recent Release with Commits
        ````````````````````````````````````````````````````````````

        :pparam string organization_id_or_slug: the id or slug of the organization the
                                          release belongs to.
        :pparam string version: the version identifier of the release.
        :auth: required
        """

        try:
            release = Release.objects.get(organization_id=organization.id, version=version)
        except Release.DoesNotExist:
            raise ResourceDoesNotExist

        if not self.has_release_permission(request, organization, release):
            raise ResourceDoesNotExist

        start_date = release.date_released or release.date_added

        prev_release_with_commits = (
            Release.objects.filter(
                organization_id=organization.id,
                projects__in=release.projects.all(),
                last_commit_id__isnull=False,
            )
            .extra(
                select={"date": "COALESCE(date_released, date_added)"},
                where=["COALESCE(date_released, date_added) <= %s"],
                params=[start_date],
            )
            .extra(order_by=["-date"])[:1]
        )

        try:
            analytics.record(
                ReleaseGetPreviousCommitsEvent(
                    user_id=request.user.id if request.user and request.user.id else None,
                    organization_id=organization.id,
                    project_ids=[project.id for project in release.projects.all()],
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)

        if not prev_release_with_commits:
            return Response({})

        return Response(
            serialize(
                prev_release_with_commits[0],
                request.user,
            )
        )
