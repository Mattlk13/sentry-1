from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Any, cast
from urllib.parse import quote as urlquote

import sentry_sdk
from django.http.request import HttpRequest
from django.utils import timezone
from rest_framework.exceptions import ParseError, ValidationError
from rest_framework.request import Request
from sentry_relay.consts import SPAN_STATUS_CODE_TO_NAME

from sentry import features, quotas
from sentry.api.api_owners import ApiOwner
from sentry.api.base import CURSOR_LINK_HEADER
from sentry.api.bases import NoProjects
from sentry.api.bases.organization import FilterParamsDateNotNull, OrganizationEndpoint
from sentry.api.helpers.error_upsampling import (
    are_any_projects_error_upsampled,
    convert_fields_for_upsampling,
)
from sentry.api.helpers.mobile import get_readable_device_name
from sentry.api.helpers.teams import get_teams
from sentry.api.serializers.snuba import SnubaTSResultSerializer
from sentry.api.utils import handle_query_errors
from sentry.discover.arithmetic import is_equation, strip_equation
from sentry.discover.models import DatasetSourcesTypes, DiscoverSavedQueryTypes
from sentry.exceptions import InvalidSearchQuery
from sentry.models.dashboard_widget import DashboardWidgetTypes
from sentry.models.dashboard_widget import DatasetSourcesTypes as DashboardDatasetSourcesTypes
from sentry.models.group import Group
from sentry.models.organization import Organization
from sentry.models.project import Project
from sentry.models.team import Team
from sentry.search.eap.constants import SAMPLING_MODE_MAP, VALID_GRANULARITIES
from sentry.search.events.constants import DURATION_UNITS, SIZE_UNITS
from sentry.search.events.fields import get_function_alias
from sentry.search.events.types import SAMPLING_MODES, SnubaParams
from sentry.snuba import discover
from sentry.snuba.dataset import Dataset
from sentry.snuba.metrics.extraction import MetricSpecType
from sentry.snuba.utils import DATASET_LABELS, DATASET_OPTIONS, get_dataset
from sentry.users.services.user.serial import serialize_generic_user
from sentry.utils import snuba
from sentry.utils.cursors import Cursor
from sentry.utils.dates import get_interval_from_range, get_rollup_from_request, parse_stats_period
from sentry.utils.http import absolute_uri
from sentry.utils.snuba import MAX_FIELDS, SnubaTSResult


def get_query_columns(columns, rollup):
    """
    Backwards compatibility for incidents which uses the old
    column aliases as it straddles both versions of events/discover.
    We will need these aliases until discover2 flags are enabled for all users.
    We need these rollup columns to generate correct events-stats results
    """
    column_map = {
        "user_count": "count_unique(user)",
        "event_count": "count()",
    }

    return [column_map.get(column, column) for column in columns]


def resolve_axis_column(
    column: str,
    index: int = 0,
    transform_alias_to_input_format: bool = False,
    use_rpc: bool = False,
) -> str:
    if is_equation(column) and not use_rpc:
        return f"equation[{index}]"

    # Function columns on input have names like `"p95(duration)"`. By default, we convert them to their aliases like `"p95_duration"`. Here, we want to preserve the original name, so we return the column as-is
    if transform_alias_to_input_format:
        return column

    return get_function_alias(column)


class OrganizationEventsEndpointBase(OrganizationEndpoint):
    owner = ApiOwner.PERFORMANCE

    def has_feature(self, organization: Organization, request: Request) -> bool:
        return (
            features.has("organizations:discover-basic", organization, actor=request.user)
            or features.has("organizations:performance-view", organization, actor=request.user)
            or features.has(
                "organizations:performance-issues-all-events-tab", organization, actor=request.user
            )
        )

    def get_equation_list(
        self, organization: Organization, request: Request, param_name: str = "field"
    ) -> list[str]:
        """equations have a prefix so that they can be easily included alongside our existing fields"""
        return [
            strip_equation(field)
            for field in request.GET.getlist(param_name)[:]
            if is_equation(field)
        ]

    def get_field_list(
        self, organization: Organization, request: Request, param_name: str = "field"
    ) -> list[str]:
        return [field for field in request.GET.getlist(param_name)[:] if not is_equation(field)]

    def get_teams(self, request: Request, organization: Organization) -> list[Team]:
        if not request.user:
            return []

        teams = get_teams(request, organization)
        if not teams:
            teams = Team.objects.get_for_user(organization, request.user)

        return [team for team in teams]

    def get_dataset(self, request: Request) -> Any:
        dataset_label = request.GET.get("dataset", Dataset.Discover.value)
        result = get_dataset(dataset_label)
        if result is None:
            raise ParseError(detail=f"dataset must be one of: {', '.join(DATASET_OPTIONS.keys())}")
        sentry_sdk.set_tag("query.dataset", dataset_label)
        return result

    def get_snuba_params(
        self,
        request: Request,
        organization: Organization,
        check_global_views: bool = True,
        quantize_date_params: bool = True,
    ) -> SnubaParams:
        """Returns params to make snuba queries with"""
        with sentry_sdk.start_span(op="discover.endpoint", name="filter_params(dataclass)"):
            if (
                len(self.get_field_list(organization, request))
                + len(self.get_equation_list(organization, request))
                > MAX_FIELDS
            ):
                raise ParseError(
                    detail=f"You can view up to {MAX_FIELDS} fields at a time. Please delete some and try again."
                )

            filter_params = self.get_filter_params(request, organization)
            query = request.GET.get("query", "")
            sampling_mode = request.GET.get("sampling", None)
            if sampling_mode is not None:
                if sampling_mode.upper() not in SAMPLING_MODE_MAP:
                    raise InvalidSearchQuery(f"sampling mode: {sampling_mode} is not supported")
                sampling_mode = cast(SAMPLING_MODES, sampling_mode.upper())

            if quantize_date_params:
                filter_params = self.quantize_date_params(request, filter_params)
            params = SnubaParams(
                start=filter_params["start"],
                end=filter_params["end"],
                environments=filter_params.get("environment_objects", []),
                projects=filter_params["project_objects"],
                user=serialize_generic_user(
                    request.user if request.user.is_authenticated else None
                ),
                teams=self.get_teams(request, organization),
                organization=organization,
                query_string=query,
                sampling_mode=sampling_mode,
                debug=request.user.is_superuser and "debug" in request.GET,
            )

            if check_global_views:
                has_global_views = features.has(
                    "organizations:global-views", organization, actor=request.user
                )
                fetching_replay_data = request.headers.get("X-Sentry-Replay-Request") == "1"
                if not has_global_views and len(params.projects) > 1 and not fetching_replay_data:
                    raise ParseError(detail="You cannot view events from multiple projects.")

            return params

    def get_orderby(self, request: Request) -> list[str] | None:
        sort = request.GET.getlist("sort")
        if sort:
            return sort
        # Deprecated. `sort` should be used as it is supported by
        # more endpoints.
        orderby = request.GET.getlist("orderby")
        if orderby:
            return orderby
        return None

    def quantize_date_params(
        self, request: Request, params: FilterParamsDateNotNull
    ) -> FilterParamsDateNotNull:
        # We only need to perform this rounding on relative date periods
        if "statsPeriod" not in request.GET:
            return params
        results = params.copy()
        duration = (params["end"] - params["start"]).total_seconds()
        # Only perform rounding on durations longer than an hour
        if duration > 3600:
            # Round to 15 minutes if over 30 days, otherwise round to the minute
            round_to = 15 * 60 if duration >= 30 * 24 * 3600 else 60
            key = params.get("organization_id", 0)

            results["start"] = snuba.quantize_time(
                params["start"], key, duration=round_to, rounding=snuba.ROUND_DOWN
            )
            results["end"] = snuba.quantize_time(
                params["end"], key, duration=round_to, rounding=snuba.ROUND_UP
            )
        return results


class OrganizationEventsV2EndpointBase(OrganizationEventsEndpointBase):
    owner = ApiOwner.PERFORMANCE

    def build_cursor_link(self, request: HttpRequest, name: str, cursor: Cursor | None) -> str:
        # The base API function only uses the last query parameter, but this endpoint
        # needs all the parameters, particularly for the "field" query param.
        querystring = "&".join(
            f"{urlquote(query[0])}={urlquote(value)}"
            for query in request.GET.lists()
            if query[0] != "cursor"
            for value in query[1]
        )

        base_url = absolute_uri(urlquote(request.path))
        if querystring:
            base_url = f"{base_url}?{querystring}"
        else:
            base_url = base_url + "?"

        return CURSOR_LINK_HEADER.format(
            uri=base_url,
            cursor=str(cursor),
            name=name,
            has_results="true" if bool(cursor) else "false",
        )

    def handle_on_demand(self, request: Request) -> tuple[bool, MetricSpecType]:
        use_on_demand_metrics = request.GET.get("useOnDemandMetrics") == "true"
        on_demand_metric_type = MetricSpecType.SIMPLE_QUERY
        on_demand_metric_type_value = request.GET.get("onDemandType")
        if use_on_demand_metrics and on_demand_metric_type_value:
            on_demand_metric_type = MetricSpecType(on_demand_metric_type_value)

        return use_on_demand_metrics, on_demand_metric_type

    def save_split_decision(self, widget, has_errors, has_transactions_data, organization, user):
        """This can be removed once the discover dataset has been fully split"""
        source = DashboardDatasetSourcesTypes.INFERRED.value
        if has_errors and not has_transactions_data:
            decision = DashboardWidgetTypes.ERROR_EVENTS
            sentry_sdk.set_tag("discover.split_reason", "query_result")
        elif not has_errors and has_transactions_data:
            decision = DashboardWidgetTypes.TRANSACTION_LIKE
            sentry_sdk.set_tag("discover.split_reason", "query_result")
        else:
            # In the case that neither side has data, or both sides have data, default to errors.
            decision = DashboardWidgetTypes.ERROR_EVENTS
            source = DashboardDatasetSourcesTypes.FORCED.value
            sentry_sdk.set_tag("discover.split_reason", "default")

        sentry_sdk.set_tag("discover.split_decision", decision)
        if decision is not None and widget.discover_widget_split != decision:
            widget.discover_widget_split = decision
            widget.dataset_source = source
            widget.save()

        return decision

    def save_discover_saved_query_split_decision(
        self, query, dataset_inferred_from_query, has_errors, has_transactions_data
    ):
        """
        This can be removed once the discover dataset has been fully split.
        If dataset is ambiguous (i.e., could be either transactions or errors),
        default to errors.
        """
        dataset_source = DatasetSourcesTypes.INFERRED.value
        if dataset_inferred_from_query:
            decision = dataset_inferred_from_query
            sentry_sdk.set_tag("discover.split_reason", "inferred_from_query")
        elif has_errors and not has_transactions_data:
            decision = DiscoverSavedQueryTypes.ERROR_EVENTS
            sentry_sdk.set_tag("discover.split_reason", "query_result")
        elif not has_errors and has_transactions_data:
            decision = DiscoverSavedQueryTypes.TRANSACTION_LIKE
            sentry_sdk.set_tag("discover.split_reason", "query_result")
        else:
            # In the case that neither or both datasets return data,
            # default to Errors.
            decision = DiscoverSavedQueryTypes.ERROR_EVENTS
            dataset_source = DatasetSourcesTypes.FORCED.value
            sentry_sdk.set_tag("discover.split_reason", "default")

        sentry_sdk.set_tag("discover.split_decision", decision)
        if query.dataset != decision:
            query.dataset = decision
            query.dataset_source = dataset_source
            query.save()

        return decision

    def handle_unit_meta(
        self, result_meta: dict[str, str]
    ) -> tuple[dict[str, str], dict[str, str | None]]:
        units: dict[str, str | None] = {}
        meta: dict[str, str] = result_meta.copy()
        for key, value in result_meta.items():
            units[key], meta[key] = self.get_unit_and_type(key, value)
        return meta, units

    def get_unit_and_type(self, field, field_type):
        if field_type in SIZE_UNITS:
            return field_type, "size"
        elif field_type in DURATION_UNITS:
            return field_type, "duration"
        elif field_type == "rate":
            if field in ["eps()", "sps()", "tps()", "sample_eps()"]:
                return "1/second", field_type
            elif field in ["epm()", "spm()", "tpm()", "sample_epm()"]:
                return "1/minute", field_type
            else:
                return None, field_type
        elif field_type == "duration":
            return "millisecond", field_type
        else:
            return None, field_type

    def handle_results_with_meta(
        self,
        request: Request,
        organization: Organization,
        project_ids: Sequence[int],
        results: dict[str, Any],
        standard_meta: bool | None = False,
        dataset: Any | None = None,
    ) -> dict[str, Any]:
        with sentry_sdk.start_span(op="discover.endpoint", name="base.handle_results"):
            data = self.handle_data(request, organization, project_ids, results.get("data"))
            meta = results.get("meta", {})
            fields_meta = meta.get("fields", {})

            if standard_meta:
                isMetricsData = meta.pop("isMetricsData", False)
                isMetricsExtractedData = meta.pop("isMetricsExtractedData", False)
                discoverSplitDecision = meta.pop("discoverSplitDecision", None)
                full_scan = meta.pop("full_scan", None)
                debug_info = meta.pop("debug_info", None)
                fields, units = self.handle_unit_meta(fields_meta)
                meta = {
                    "fields": fields,
                    "units": units,
                    "isMetricsData": isMetricsData,
                    "isMetricsExtractedData": isMetricsExtractedData,
                    "tips": meta.get("tips", {}),
                    "datasetReason": meta.get("datasetReason", discover.DEFAULT_DATASET_REASON),
                }
                if dataset is not None:
                    meta["dataset"] = DATASET_LABELS.get(dataset, "unknown")

                if discoverSplitDecision is not None:
                    meta["discoverSplitDecision"] = discoverSplitDecision

                if full_scan is not None:
                    meta["dataScanned"] = "full" if full_scan else "partial"
                else:
                    # If this key isn't in meta there wasn't any sampling and we can assume all the data was scanned
                    meta["dataScanned"] = "full"

                # Only appears in meta when debug is passed to the endpoint
                if debug_info:
                    meta["debug_info"] = debug_info
            else:
                meta = fields_meta

            meta["isMetricsData"] = meta.get("isMetricsData", False)
            meta["isMetricsExtractedData"] = meta.get("isMetricsExtractedData", False)

            if not data:
                return {"data": [], "meta": meta}
            if "confidence" in results:
                meta["accuracy"] = {
                    "confidence": results["confidence"],
                }
                # Confidence being a top level key is going to be deprecated in favour of confidence being in the meta
                return {"data": data, "meta": meta, "confidence": results["confidence"]}
            return {"data": data, "meta": meta}

    def handle_data(
        self,
        request: Request,
        organization: Organization,
        project_ids: Sequence[int],
        results: Sequence[Any] | None,
    ) -> Sequence[Any] | None:
        if not results:
            return results

        first_row = results[0]

        if "transaction.status" in first_row:
            for row in results:
                if "transaction.status" in row and type(row["transaction.status"]) is int:
                    row["transaction.status"] = SPAN_STATUS_CODE_TO_NAME.get(
                        row["transaction.status"]
                    )

        fields = self.get_field_list(organization, request)
        if "issue" in fields:  # Look up the short ID and return that in the results
            self.handle_issues(results, project_ids, organization)

        if "device" in fields and request.GET.get("readable"):
            self.handle_readable_device(results, project_ids, organization)

        if not ("project.id" in first_row or "projectid" in first_row):
            return results

        for result in results:
            for key in ("projectid", "project.id"):
                if key in result and key not in fields:
                    del result[key]

        return results

    def handle_error_upsampling(self, project_ids: Sequence[int], results: dict[str, Any]):
        """
        If the query is for error upsampled projects, we convert various functions under the hood.
        We need to rename these fields before returning the results to the client, to hide the conversion.
        This is done here to work around a limitation in how aliases are handled in the SnQL parser.
        """
        if are_any_projects_error_upsampled(project_ids):
            data = results.get("data", [])
            fields_meta = results.get("meta", {}).get("fields", {})
            convert_fields_for_upsampling(data, fields_meta)

    def handle_issues(
        self, results: Sequence[Any], project_ids: Sequence[int], organization: Organization
    ) -> None:
        issue_ids = {row.get("issue.id") for row in results if row.get("issue.id")}
        issues = Group.objects.get_issues_mapping(issue_ids, project_ids, organization)
        for result in results:
            if "issue.id" in result:
                result["issue"] = issues.get(result["issue.id"], "unknown")

    def handle_readable_device(
        self, results: Sequence[Any], project_ids: Sequence[int], organization: Organization
    ) -> None:
        for result in results:
            if "device" in result:
                readable_value = get_readable_device_name(result["device"])
                if readable_value:
                    result["readable"] = readable_value

    def get_rollup(
        self, request: Request, snuba_params: SnubaParams, top_events: int, use_rpc: bool
    ) -> int:
        """TODO: we should eventually rely on `SnubaParams.granularity_secs` instead"""
        try:
            rollup = get_rollup_from_request(
                request,
                snuba_params.date_range,
                default_interval=None,
                error=InvalidSearchQuery(),
                top_events=top_events,
                allow_interval_over_range=not use_rpc,
            )
        # If the user sends an invalid interval, use the default instead
        except InvalidSearchQuery:
            # on RPC don't use default interval on error
            if use_rpc:
                raise
            sentry_sdk.set_tag("user.invalid_interval", request.GET.get("interval"))
            date_range = snuba_params.date_range
            stats_period = parse_stats_period(get_interval_from_range(date_range, False))
            rollup = int(stats_period.total_seconds()) if stats_period is not None else 3600
        return rollup

    def validate_comparison_delta(
        self,
        comparison_delta: timedelta | None,
        snuba_params: SnubaParams,
        organization: Organization,
    ) -> None:
        if comparison_delta is not None:
            retention = quotas.backend.get_event_retention(organization=organization)
            comparison_start = snuba_params.start_date - comparison_delta
            if retention and comparison_start < timezone.now() - timedelta(days=retention):
                raise ValidationError("Comparison period is outside your retention window")

    def get_event_stats_data(
        self,
        request: Request,
        organization: Organization,
        get_event_stats: Callable[
            [list[str], str, SnubaParams, int, bool, timedelta | None],
            SnubaTSResult | dict[str, SnubaTSResult],
        ],
        top_events: int = 0,
        query_column: str = "count()",
        snuba_params: SnubaParams | None = None,
        query: str | None = None,
        allow_partial_buckets: bool = False,
        zerofill_results: bool = True,
        comparison_delta: timedelta | None = None,
        additional_query_columns: list[str] | None = None,
        dataset: Any | None = None,
        transform_alias_to_input_format: bool = False,
        use_rpc: bool = False,
    ) -> dict[str, Any]:
        with handle_query_errors():
            with sentry_sdk.start_span(op="discover.endpoint", name="base.stats_query_creation"):
                _columns = [query_column]
                # temporary change to make topN query work for multi-axes requests
                if additional_query_columns is not None:
                    _columns.extend(additional_query_columns)

                columns = request.GET.getlist("yAxis", _columns)

                if query is None:
                    query = request.GET.get("query", "")
                if snuba_params is None:
                    try:
                        # events-stats is still used by events v1 which doesn't require global views
                        snuba_params = self.get_snuba_params(
                            request, organization, check_global_views=False
                        )
                    except NoProjects:
                        return {"data": []}

                if use_rpc and snuba_params.date_range.total_seconds() < min(VALID_GRANULARITIES):
                    raise InvalidSearchQuery(
                        f"Timeseries queries must be for periods of at least {min(VALID_GRANULARITIES)} seconds"
                    )
                rollup = self.get_rollup(request, snuba_params, top_events, use_rpc)
                snuba_params.granularity_secs = rollup
                self.validate_comparison_delta(comparison_delta, snuba_params, organization)

                query_columns = get_query_columns(columns, rollup)
            with sentry_sdk.start_span(op="discover.endpoint", name="base.stats_query"):
                result = get_event_stats(
                    query_columns, query, snuba_params, rollup, zerofill_results, comparison_delta
                )

        serializer = SnubaTSResultSerializer(organization, None, request.user)

        with sentry_sdk.start_span(op="discover.endpoint", name="base.stats_serialization"):
            # When the request is for top_events, result can be a SnubaTSResult in the event that
            # there were no top events found. In this case, result contains a zerofilled series
            # that acts as a placeholder.
            is_multiple_axis = len(query_columns) > 1
            if isinstance(result, dict):
                results = {}
                for key, event_result in result.items():
                    if is_multiple_axis:
                        results[key] = self.serialize_multiple_axis(
                            request,
                            organization,
                            serializer,
                            event_result,
                            snuba_params,
                            columns,
                            query_columns,
                            allow_partial_buckets,
                            zerofill_results=zerofill_results,
                            dataset=dataset,
                            transform_alias_to_input_format=transform_alias_to_input_format,
                            use_rpc=use_rpc,
                        )
                        if request.query_params.get("useOnDemandMetrics") == "true":
                            results[key]["isMetricsExtractedData"] = self._query_if_extracted_data(
                                results, key, query_columns
                            )
                    else:
                        column = resolve_axis_column(
                            query_columns[0], 0, transform_alias_to_input_format, use_rpc
                        )
                        results[key] = serializer.serialize(
                            event_result,
                            column=column,
                            allow_partial_buckets=allow_partial_buckets,
                            zerofill_results=zerofill_results,
                        )
                        meta = self.handle_results_with_meta(
                            request,
                            organization,
                            snuba_params.project_ids,
                            event_result.data,
                            True,
                            dataset=dataset,
                        )["meta"]
                        self.update_meta_with_accuracy(meta, event_result, column)
                        results[key]["meta"] = meta

                serialized_result = results
            elif is_multiple_axis:
                serialized_result = self.serialize_multiple_axis(
                    request,
                    organization,
                    serializer,
                    result,
                    snuba_params,
                    columns,
                    query_columns,
                    allow_partial_buckets,
                    zerofill_results=zerofill_results,
                    dataset=dataset,
                    transform_alias_to_input_format=transform_alias_to_input_format,
                    use_rpc=use_rpc,
                )
                if top_events > 0 and isinstance(result, SnubaTSResult):
                    serialized_result = {"": serialized_result}
            else:
                extra_columns = None
                if comparison_delta:
                    extra_columns = ["comparisonCount"]
                column = resolve_axis_column(
                    query_columns[0], 0, transform_alias_to_input_format, use_rpc
                )
                serialized_result = serializer.serialize(
                    result,
                    column=column,
                    allow_partial_buckets=allow_partial_buckets,
                    zerofill_results=zerofill_results,
                    extra_columns=extra_columns,
                    confidence_column=column,
                )
                meta = self.handle_results_with_meta(
                    request,
                    organization,
                    snuba_params.project_ids,
                    result.data,
                    True,
                    dataset=dataset,
                )["meta"]
                self.update_meta_with_accuracy(meta, result, column)
                serialized_result["meta"] = meta

            return serialized_result

    def _query_if_extracted_data(
        self, results: dict[str, Any], key: str, query_columns: list[str]
    ) -> bool:
        ret_value = False
        try:
            for c in query_columns:
                # At least one of the columns has required extracted data
                if results[key][c].get("meta", {}).get("isMetricsExtractedData"):
                    ret_value = True
                    break
        except Exception as error:
            sentry_sdk.capture_exception(error)

        return ret_value

    def serialize_multiple_axis(
        self,
        request: Request,
        organization: Organization,
        serializer: SnubaTSResultSerializer,
        event_result: SnubaTSResult,
        snuba_params: SnubaParams,
        columns: Sequence[str],
        query_columns: list[str],
        allow_partial_buckets: bool,
        zerofill_results: bool = True,
        dataset: Any | None = None,
        transform_alias_to_input_format: bool = False,
        use_rpc: bool = False,
    ) -> dict[str, Any]:
        # Return with requested yAxis as the key
        result = {}
        equations = 0
        meta = self.handle_results_with_meta(
            request,
            organization,
            snuba_params.project_ids,
            event_result.data,
            True,
            dataset=dataset,
        )["meta"]
        for index, query_column in enumerate(query_columns):
            result[columns[index]] = serializer.serialize(
                event_result,
                resolve_axis_column(
                    query_column, equations, transform_alias_to_input_format, use_rpc
                ),
                order=index,
                allow_partial_buckets=allow_partial_buckets,
                zerofill_results=zerofill_results,
            )
            if is_equation(query_column):
                equations += 1
            column_meta = meta.copy()
            self.update_meta_with_accuracy(column_meta, event_result, query_column)
            result[columns[index]]["meta"] = column_meta
        # Set order if multi-axis + top events
        if "order" in event_result.data:
            result["order"] = event_result.data["order"]

        return result

    def update_meta_with_accuracy(self, meta, event_result, query_column) -> None:
        if "processed_timeseries" in event_result.data:
            processed_timeseries = event_result.data["processed_timeseries"]
            meta["accuracy"] = {
                "confidence": self.serialize_accuracy_data(
                    processed_timeseries.confidence, query_column
                ),
                "sampleCount": self.serialize_accuracy_data(
                    processed_timeseries.sample_count, query_column
                ),
                "samplingRate": self.serialize_accuracy_data(
                    processed_timeseries.sampling_rate, query_column, null_zero=True
                ),
            }

    def serialize_accuracy_data(
        self,
        data: Any,
        column: str,
        null_zero: bool = False,
    ):
        serialized_values = []
        for timestamp, group in itertools.groupby(data, key=lambda r: r["time"]):
            for row in group:
                row_value = row.get(column, None)
                if row_value == 0 and null_zero:
                    row_value = None
                serialized_values.append(
                    {
                        "timestamp": timestamp,
                        "value": row_value,
                    }
                )
        return serialized_values


class KeyTransactionBase(OrganizationEventsV2EndpointBase):
    def has_feature(self, organization: Organization, request: Request) -> bool:
        return features.has("organizations:performance-view", organization, actor=request.user)

    def get_project(self, request: Request, organization: Organization) -> Project:
        projects = self.get_projects(request, organization)

        if len(projects) != 1:
            raise ParseError("Only 1 project per Key Transaction")
        return projects[0]
