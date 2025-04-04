from typing import Literal, cast

from sentry_protos.snuba.v1.attribute_conditional_aggregation_pb2 import (
    AttributeConditionalAggregation,
)
from sentry_protos.snuba.v1.endpoint_trace_item_table_pb2 import Column
from sentry_protos.snuba.v1.formula_pb2 import Literal as LiteralValue
from sentry_protos.snuba.v1.trace_item_attribute_pb2 import (
    AttributeAggregation,
    AttributeKey,
    AttributeValue,
    Function,
    StrArray,
)
from sentry_protos.snuba.v1.trace_item_filter_pb2 import (
    ComparisonFilter,
    ExistsFilter,
    TraceItemFilter,
)

from sentry.search.eap import constants
from sentry.search.eap.columns import (
    AttributeArgumentDefinition,
    FormulaDefinition,
    ResolvedArguments,
    ResolverSettings,
    ValueArgumentDefinition,
)
from sentry.search.eap.constants import RESPONSE_CODE_MAP
from sentry.search.eap.spans.utils import WEB_VITALS_MEASUREMENTS, transform_vital_score_to_ratio
from sentry.search.eap.utils import literal_validator
from sentry.search.events.constants import WEB_VITALS_PERFORMANCE_SCORE_WEIGHTS


def get_total_span_count(settings: ResolverSettings) -> Column:
    """
    This column represents a count of the all of spans.
    It works by counting the number of spans that have the attribute "sentry.exclusive_time_ms" (which is set on every span)
    """
    extrapolation_mode = settings["extrapolation_mode"]
    return Column(
        aggregation=AttributeAggregation(
            aggregate=Function.FUNCTION_COUNT,
            key=AttributeKey(type=AttributeKey.TYPE_DOUBLE, name="sentry.exclusive_time_ms"),
            label="total",
            extrapolation_mode=extrapolation_mode,
        )
    )


def division(args: ResolvedArguments, _: ResolverSettings) -> Column.BinaryFormula:
    dividend = cast(AttributeKey, args[0])
    divisor = cast(AttributeKey, args[1])

    return Column.BinaryFormula(
        left=Column(key=dividend, label="dividend"),
        op=Column.BinaryFormula.OP_DIVIDE,
        right=Column(key=divisor, label="divisor"),
    )


def avg_compare(args: ResolvedArguments, settings: ResolverSettings) -> Column.BinaryFormula:
    extrapolation_mode = settings["extrapolation_mode"]
    attribute = cast(AttributeKey, args[0])
    comparison_attribute = cast(AttributeKey, args[1])
    first_value = cast(str, args[2])
    second_value = cast(str, args[3])

    avg_first = Column(
        conditional_aggregation=AttributeConditionalAggregation(
            aggregate=Function.FUNCTION_AVG,
            key=attribute,
            filter=TraceItemFilter(
                comparison_filter=ComparisonFilter(
                    key=comparison_attribute,
                    op=ComparisonFilter.OP_EQUALS,
                    value=AttributeValue(val_str=first_value),
                )
            ),
            extrapolation_mode=extrapolation_mode,
        )
    )

    avg_second = Column(
        conditional_aggregation=AttributeConditionalAggregation(
            aggregate=Function.FUNCTION_AVG,
            key=attribute,
            filter=TraceItemFilter(
                comparison_filter=ComparisonFilter(
                    key=comparison_attribute,
                    op=ComparisonFilter.OP_EQUALS,
                    value=AttributeValue(val_str=second_value),
                )
            ),
            extrapolation_mode=extrapolation_mode,
        )
    )

    percentage_change = Column.BinaryFormula(
        left=Column(
            formula=Column.BinaryFormula(
                left=avg_second,
                op=Column.BinaryFormula.OP_SUBTRACT,
                right=avg_first,
            )
        ),
        op=Column.BinaryFormula.OP_DIVIDE,
        right=avg_first,
    )

    return percentage_change


def failure_rate(_: ResolvedArguments, settings: ResolverSettings) -> Column.BinaryFormula:
    extrapolation_mode = settings["extrapolation_mode"]

    return Column.BinaryFormula(
        left=Column(
            conditional_aggregation=AttributeConditionalAggregation(
                aggregate=Function.FUNCTION_COUNT,
                key=AttributeKey(
                    name="sentry.trace.status",
                    type=AttributeKey.TYPE_STRING,
                ),
                filter=TraceItemFilter(
                    comparison_filter=ComparisonFilter(
                        key=AttributeKey(
                            name="sentry.trace.status",
                            type=AttributeKey.TYPE_STRING,
                        ),
                        op=ComparisonFilter.OP_NOT_IN,
                        value=AttributeValue(
                            val_str_array=StrArray(
                                values=["ok", "cancelled", "unknown"],
                            ),
                        ),
                    )
                ),
                label="trace_status_count",
                extrapolation_mode=extrapolation_mode,
            ),
        ),
        op=Column.BinaryFormula.OP_DIVIDE,
        right=get_total_span_count(settings),
    )


def opportunity_score(args: ResolvedArguments, settings: ResolverSettings) -> Column.BinaryFormula:
    extrapolation_mode = settings["extrapolation_mode"]

    score_attribute = cast(AttributeKey, args[0])
    ratio_attribute = transform_vital_score_to_ratio([score_attribute])

    score_ratio = Column.BinaryFormula(
        left=Column(
            conditional_aggregation=AttributeConditionalAggregation(
                aggregate=Function.FUNCTION_COUNT,
                filter=TraceItemFilter(
                    exists_filter=ExistsFilter(key=ratio_attribute),
                ),
                key=ratio_attribute,
                extrapolation_mode=extrapolation_mode,
            )
        ),
        op=Column.BinaryFormula.OP_SUBTRACT,
        right=Column(
            conditional_aggregation=AttributeConditionalAggregation(
                aggregate=Function.FUNCTION_SUM,
                filter=TraceItemFilter(
                    exists_filter=ExistsFilter(key=ratio_attribute),
                ),
                key=ratio_attribute,
                extrapolation_mode=extrapolation_mode,
            )
        ),
    )
    web_vital = score_attribute.name.split(".")[-1]

    if web_vital == "total":
        return score_ratio

    weight = WEB_VITALS_PERFORMANCE_SCORE_WEIGHTS[web_vital]

    return Column.BinaryFormula(
        left=Column(formula=score_ratio),
        op=Column.BinaryFormula.OP_MULTIPLY,
        right=Column(literal=LiteralValue(val_double=weight)),
    )


def http_response_rate(args: ResolvedArguments, settings: ResolverSettings) -> Column.BinaryFormula:
    extrapolation_mode = settings["extrapolation_mode"]

    code = cast(Literal[1, 2, 3, 4, 5], args[0])

    response_codes = RESPONSE_CODE_MAP[code]
    return Column.BinaryFormula(
        left=Column(
            conditional_aggregation=AttributeConditionalAggregation(
                aggregate=Function.FUNCTION_COUNT,
                key=AttributeKey(
                    name="sentry.status_code",
                    type=AttributeKey.TYPE_STRING,
                ),
                filter=TraceItemFilter(
                    comparison_filter=ComparisonFilter(
                        key=AttributeKey(
                            name="sentry.status_code",
                            type=AttributeKey.TYPE_STRING,
                        ),
                        op=ComparisonFilter.OP_IN,
                        value=AttributeValue(
                            val_str_array=StrArray(
                                values=response_codes,  # It is faster to exact matches then startsWith
                            ),
                        ),
                    )
                ),
                label="error_request_count",
                extrapolation_mode=extrapolation_mode,
            ),
        ),
        op=Column.BinaryFormula.OP_DIVIDE,
        right=Column(
            conditional_aggregation=AttributeConditionalAggregation(
                aggregate=Function.FUNCTION_COUNT,
                key=AttributeKey(
                    name="sentry.status_code",
                    type=AttributeKey.TYPE_STRING,
                ),
                label="total_request_count",
                extrapolation_mode=extrapolation_mode,
            ),
        ),
    )


def trace_status_rate(args: ResolvedArguments, settings: ResolverSettings) -> Column.BinaryFormula:
    extrapolation_mode = settings["extrapolation_mode"]

    status = cast(str, args[0])

    return Column.BinaryFormula(
        left=Column(
            conditional_aggregation=AttributeConditionalAggregation(
                aggregate=Function.FUNCTION_COUNT,
                key=AttributeKey(
                    name="sentry.trace.status",
                    type=AttributeKey.TYPE_STRING,
                ),
                filter=TraceItemFilter(
                    comparison_filter=ComparisonFilter(
                        key=AttributeKey(
                            name="sentry.trace.status",
                            type=AttributeKey.TYPE_STRING,
                        ),
                        op=ComparisonFilter.OP_EQUALS,
                        value=AttributeValue(
                            val_str=status,
                        ),
                    )
                ),
                label="trace_status_count",
                extrapolation_mode=extrapolation_mode,
            ),
        ),
        op=Column.BinaryFormula.OP_DIVIDE,
        right=get_total_span_count(settings),
    )


def cache_miss_rate(_: ResolvedArguments, settings: ResolverSettings) -> Column.BinaryFormula:
    extrapolation_mode = settings["extrapolation_mode"]

    return Column.BinaryFormula(
        left=Column(
            conditional_aggregation=AttributeConditionalAggregation(
                aggregate=Function.FUNCTION_COUNT,
                key=AttributeKey(
                    name="cache.hit",
                    type=AttributeKey.TYPE_BOOLEAN,
                ),
                filter=TraceItemFilter(
                    comparison_filter=ComparisonFilter(
                        key=AttributeKey(
                            name="cache.hit",
                            type=AttributeKey.TYPE_BOOLEAN,
                        ),
                        op=ComparisonFilter.OP_EQUALS,
                        value=AttributeValue(
                            val_bool=False,
                        ),
                    )
                ),
                label="cache_miss_count",
                extrapolation_mode=extrapolation_mode,
            ),
        ),
        op=Column.BinaryFormula.OP_DIVIDE,
        right=Column(
            conditional_aggregation=AttributeConditionalAggregation(
                aggregate=Function.FUNCTION_COUNT,
                key=AttributeKey(
                    name="cache.hit",
                    type=AttributeKey.TYPE_BOOLEAN,
                ),
                label="total_cache_count",
                extrapolation_mode=extrapolation_mode,
            ),
        ),
    )


def ttfd_contribution_rate(
    _: ResolvedArguments, settings: ResolverSettings
) -> Column.BinaryFormula:
    extrapolation_mode = settings["extrapolation_mode"]

    return Column.BinaryFormula(
        left=Column(
            conditional_aggregation=AttributeConditionalAggregation(
                aggregate=Function.FUNCTION_COUNT,
                key=AttributeKey(name="sentry.ttfd", type=AttributeKey.TYPE_STRING),
                filter=TraceItemFilter(
                    comparison_filter=ComparisonFilter(
                        key=AttributeKey(name="sentry.ttfd", type=AttributeKey.TYPE_STRING),
                        op=ComparisonFilter.OP_EQUALS,
                        value=AttributeValue(val_str="ttfd"),
                    )
                ),
                label="ttfd_count",
                extrapolation_mode=extrapolation_mode,
            ),
        ),
        op=Column.BinaryFormula.OP_DIVIDE,
        right=get_total_span_count(settings),
    )


def ttid_contribution_rate(
    _: ResolvedArguments, settings: ResolverSettings
) -> Column.BinaryFormula:
    extrapolation_mode = settings["extrapolation_mode"]

    return Column.BinaryFormula(
        left=Column(
            conditional_aggregation=AttributeConditionalAggregation(
                aggregate=Function.FUNCTION_COUNT,
                key=AttributeKey(name="sentry.ttid", type=AttributeKey.TYPE_STRING),
                filter=TraceItemFilter(
                    comparison_filter=ComparisonFilter(
                        key=AttributeKey(name="sentry.ttid", type=AttributeKey.TYPE_STRING),
                        op=ComparisonFilter.OP_EQUALS,
                        value=AttributeValue(val_str="ttid"),
                    )
                ),
                label="ttid_count",
                extrapolation_mode=extrapolation_mode,
            ),
        ),
        op=Column.BinaryFormula.OP_DIVIDE,
        right=get_total_span_count(settings),
    )


def time_spent_percentage(
    args: ResolvedArguments, settings: ResolverSettings
) -> Column.BinaryFormula:
    extrapolation_mode = settings["extrapolation_mode"]

    attribute = cast(AttributeKey, args[0])
    """TODO: This function isn't fully implemented, when https://github.com/getsentry/eap-planning/issues/202 is merged we can properly divide by the total time"""

    return Column.BinaryFormula(
        left=Column(
            aggregation=AttributeAggregation(
                aggregate=Function.FUNCTION_SUM,
                key=attribute,
                extrapolation_mode=extrapolation_mode,
            )
        ),
        op=Column.BinaryFormula.OP_DIVIDE,
        right=Column(
            aggregation=AttributeAggregation(
                aggregate=Function.FUNCTION_SUM,
                key=attribute,
                extrapolation_mode=extrapolation_mode,
            )
        ),
    )


def epm(_: ResolvedArguments, settings: ResolverSettings) -> Column.BinaryFormula:
    extrapolation_mode = settings["extrapolation_mode"]
    interval = settings["query_settings"]["snuba_params"].interval
    granularity_secs = settings["query_settings"]["granularity_secs"]

    # having a granularity_secs implies that the request is for a time series, and each datapoint should be divided by it
    divisor = granularity_secs if granularity_secs else interval

    return Column.BinaryFormula(
        left=Column(
            aggregation=AttributeAggregation(
                aggregate=Function.FUNCTION_COUNT,
                key=AttributeKey(type=AttributeKey.TYPE_DOUBLE, name="sentry.exclusive_time_ms"),
                extrapolation_mode=extrapolation_mode,
            )
        ),
        op=Column.BinaryFormula.OP_DIVIDE,
        right=Column(
            literal=LiteralValue(val_double=divisor / 60),
        ),
    )


SPAN_FORMULA_DEFINITIONS = {
    "http_response_rate": FormulaDefinition(
        default_search_type="percentage",
        is_aggregate=True,
        arguments=[
            ValueArgumentDefinition(
                argument_types={"integer"},
                validator=literal_validator(["1", "2", "3", "4", "5"]),
            )
        ],
        formula_resolver=http_response_rate,
    ),
    "cache_miss_rate": FormulaDefinition(
        default_search_type="percentage",
        arguments=[],
        formula_resolver=cache_miss_rate,
        is_aggregate=True,
    ),
    "trace_status_rate": FormulaDefinition(
        default_search_type="percentage",
        is_aggregate=True,
        arguments=[
            ValueArgumentDefinition(
                argument_types={"string"},
            )
        ],
        formula_resolver=trace_status_rate,
    ),
    "failure_rate": FormulaDefinition(
        default_search_type="percentage",
        arguments=[],
        formula_resolver=failure_rate,
        is_aggregate=True,
    ),
    "ttfd_contribution_rate": FormulaDefinition(
        default_search_type="percentage",
        arguments=[],
        formula_resolver=ttfd_contribution_rate,
        is_aggregate=True,
    ),
    "ttid_contribution_rate": FormulaDefinition(
        default_search_type="percentage",
        arguments=[],
        formula_resolver=ttid_contribution_rate,
        is_aggregate=True,
    ),
    "opportunity_score": FormulaDefinition(
        default_search_type="percentage",
        arguments=[
            AttributeArgumentDefinition(
                attribute_types={
                    "duration",
                    "number",
                },
                validator=literal_validator(WEB_VITALS_MEASUREMENTS),
            ),
        ],
        formula_resolver=opportunity_score,
        is_aggregate=True,
    ),
    "avg_compare": FormulaDefinition(
        default_search_type="percentage",
        arguments=[
            AttributeArgumentDefinition(
                attribute_types={
                    "duration",
                    "number",
                    "percentage",
                    *constants.SIZE_TYPE,
                    *constants.DURATION_TYPE,
                },
            ),
            AttributeArgumentDefinition(attribute_types={"string"}),
            ValueArgumentDefinition(argument_types={"string"}),
            ValueArgumentDefinition(argument_types={"string"}),
        ],
        formula_resolver=avg_compare,
        is_aggregate=True,
    ),
    "division": FormulaDefinition(
        default_search_type="number",
        arguments=[
            AttributeArgumentDefinition(
                attribute_types={
                    "duration",
                    "number",
                    "percentage",
                    *constants.SIZE_TYPE,
                    *constants.DURATION_TYPE,
                },
            ),
            AttributeArgumentDefinition(
                attribute_types={
                    "duration",
                    "number",
                    "percentage",
                    *constants.SIZE_TYPE,
                    *constants.DURATION_TYPE,
                },
            ),
        ],
        formula_resolver=division,
        is_aggregate=True,
    ),
    "time_spent_percentage": FormulaDefinition(
        default_search_type="percentage",
        arguments=[
            AttributeArgumentDefinition(
                attribute_types={
                    "duration",
                    "number",
                    "percentage",
                    *constants.SIZE_TYPE,
                    *constants.DURATION_TYPE,
                },
                default_arg="span.self_time",
                validator=literal_validator(["span.self_time", "span.duration"]),
            )
        ],
        formula_resolver=time_spent_percentage,
        is_aggregate=True,
    ),
    "epm": FormulaDefinition(
        default_search_type="number", arguments=[], formula_resolver=epm, is_aggregate=True
    ),
}
