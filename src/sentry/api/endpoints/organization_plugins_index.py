from rest_framework.request import Request
from rest_framework.response import Response

from sentry.api.api_owners import ApiOwner
from sentry.api.api_publish_status import ApiPublishStatus
from sentry.api.base import region_silo_endpoint
from sentry.api.bases.organization import OrganizationEndpoint
from sentry.api.serializers import serialize
from sentry.api.serializers.models.organization_plugin import OrganizationPluginSerializer
from sentry.api.serializers.models.plugin import PluginSerializer
from sentry.models.options.project_option import ProjectOption
from sentry.models.organization import Organization
from sentry.plugins.base import plugins


@region_silo_endpoint
class OrganizationPluginsEndpoint(OrganizationEndpoint):
    owner = ApiOwner.INTEGRATIONS
    publish_status = {
        "GET": ApiPublishStatus.PRIVATE,
    }

    def get(self, request: Request, organization: Organization) -> Response:
        all_plugins = {p.slug: p for p in plugins.all()}

        if "plugins" in request.GET:
            if request.GET.get("plugins") == "_all":
                return Response(
                    serialize([p for p in plugins.all()], request.user, PluginSerializer())
                )

            desired_plugins = set(request.GET.getlist("plugins"))
        else:
            desired_plugins = set(all_plugins.keys())

        # Ignore plugins that are not available to this Sentry install.
        desired_plugins = desired_plugins & set(all_plugins.keys())

        # Each tuple represents an enabled Plugin (of only the ones we care
        # about) and its corresponding Project.
        enabled_plugins = ProjectOption.objects.filter(
            key__in=["%s:enabled" % slug for slug in desired_plugins],
            project__organization=organization,
        ).select_related("project")

        resources = []

        for project_option in enabled_plugins:
            resources.append(
                serialize(
                    all_plugins[project_option.key.split(":")[0]],
                    request.user,
                    OrganizationPluginSerializer(project_option.project),
                )
            )

        return Response(resources)
