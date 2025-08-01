from collections import defaultdict
from typing import TypedDict

import sentry_sdk
from rest_framework.request import Request
from rest_framework.response import Response

from sentry import tagstore
from sentry.api.api_publish_status import ApiPublishStatus
from sentry.api.base import region_silo_endpoint
from sentry.api.bases import NoProjects, OrganizationEventsV2EndpointBase
from sentry.api.paginator import GenericOffsetPaginator
from sentry.api.utils import handle_query_errors, update_snuba_params_with_timestamp
from sentry.models.organization import Organization
from sentry.search.utils import DEVICE_CLASS


class _TopValue(TypedDict):
    name: str
    value: int | str
    count: int


class _KeyTopValues(TypedDict):
    key: str
    topValues: list[_TopValue]


@region_silo_endpoint
class OrganizationEventsFacetsEndpoint(OrganizationEventsV2EndpointBase):
    publish_status = {
        "GET": ApiPublishStatus.PRIVATE,
    }

    def get(self, request: Request, organization: Organization) -> Response:
        if not self.has_feature(organization, request):
            return Response(status=404)

        try:
            snuba_params = self.get_snuba_params(request, organization)
        except NoProjects:
            return Response([])

        update_snuba_params_with_timestamp(request, snuba_params, timestamp_key="traceTimestamp")

        dataset = self.get_dataset(request)

        def data_fn(offset, limit):
            with sentry_sdk.start_span(op="discover.endpoint", name="discover_query"):
                with handle_query_errors():
                    facets = dataset.get_facets(
                        query=request.GET.get("query"),
                        snuba_params=snuba_params,
                        referrer="api.organization-events-facets.top-tags",
                        per_page=limit,
                        cursor=offset,
                    )

            with sentry_sdk.start_span(op="discover.endpoint", name="populate_results") as span:
                span.set_data("facet_count", len(facets or []))
                resp: dict[str, _KeyTopValues]
                resp = defaultdict(lambda: {"key": "", "topValues": []})
                for row in facets:
                    values = resp[row.key]
                    values["key"] = tagstore.backend.get_standardized_key(row.key)
                    values["topValues"].append(
                        {
                            "name": tagstore.backend.get_tag_value_label(row.key, row.value),
                            "value": row.value,
                            "count": row.count,
                        }
                    )

                if "project" in resp:
                    # Replace project ids with slugs as that is what we generally expose to users
                    # and filter out projects that the user doesn't have access too.
                    projects = {p.id: p.slug for p in self.get_projects(request, organization)}
                    filtered_values = []
                    for v in resp["project"]["topValues"]:
                        if isinstance(v["value"], int) and v["value"] in projects:
                            name = projects[v["value"]]
                            v.update({"name": name})
                            filtered_values.append(v)

                    resp["project"]["topValues"] = filtered_values

                if "device.class" in resp:
                    # Map device.class tag values to low, medium, or high
                    filtered_values = []
                    for v in resp["device.class"]["topValues"]:
                        for key, value in DEVICE_CLASS.items():
                            if v["value"] in value:
                                v.update({"name": key, "value": key})
                                filtered_values.append(v)
                                continue

                    resp["device.class"]["topValues"] = filtered_values

            return list(resp.values())

        if request.GET.get("includeAll"):
            return Response(data_fn(0, 10000))

        return self.paginate(
            request=request,
            paginator=GenericOffsetPaginator(data_fn=data_fn),
            default_per_page=10,
            on_results=lambda results: sorted(results, key=lambda result: str(result.get("key"))),
        )
