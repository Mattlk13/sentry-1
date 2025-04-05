from typing import Literal

from sentry.search.eap import constants
from sentry.search.eap.columns import (
    ResolvedAttribute,
    VirtualColumnDefinition,
    datetime_processor,
    project_context_constructor,
    project_term_resolver,
    simple_sentry_field,
)
from sentry.search.eap.common_columns import COMMON_COLUMNS
from sentry.utils.validators import is_event_id, is_span_id

OURLOG_ATTRIBUTE_DEFINITIONS = {
    column.public_alias: column
    for column in COMMON_COLUMNS
    + [
        ResolvedAttribute(
            public_alias="span_id",
            internal_name="sentry.span_id",
            search_type="string",
            validator=is_span_id,
        ),
        ResolvedAttribute(
            public_alias="log.body",
            internal_name="sentry.body",
            search_type="string",
        ),
        ResolvedAttribute(
            public_alias="log.severity_number",
            internal_name="sentry.severity_number",
            search_type="integer",
        ),
        ResolvedAttribute(
            public_alias="log.severity_text",
            internal_name="sentry.severity_text",
            search_type="string",
        ),
        # Message maps to body, this is to allow wildcard searching
        ResolvedAttribute(
            public_alias="message",
            internal_name="sentry.body",
            search_type="string",
            secondary_alias=True,
        ),
        ResolvedAttribute(
            public_alias="trace",
            internal_name="sentry.trace_id",
            search_type="string",
            validator=is_event_id,
        ),
        ResolvedAttribute(
            public_alias="timestamp",
            internal_name="sentry.timestamp",
            search_type="string",
            processor=datetime_processor,
        ),
        simple_sentry_field("browser.name"),
        simple_sentry_field("environment"),
    ]
}

OURLOG_VIRTUAL_CONTEXTS = {
    key: VirtualColumnDefinition(
        constructor=project_context_constructor(key),
        term_resolver=project_term_resolver,
        filter_column="project.id",
    )
    for key in constants.PROJECT_FIELDS
}

LOGS_INTERNAL_TO_PUBLIC_ALIAS_MAPPINGS: dict[Literal["string", "number"], dict[str, str]] = {
    "string": {
        definition.internal_name: definition.public_alias
        for definition in OURLOG_ATTRIBUTE_DEFINITIONS.values()
        if not definition.secondary_alias and definition.search_type == "string"
    }
    | {
        # sentry.service is the project id as a string, but map to project for convenience
        "sentry.service": "project",
    },
    "number": {
        definition.internal_name: definition.public_alias
        for definition in OURLOG_ATTRIBUTE_DEFINITIONS.values()
        if not definition.secondary_alias and definition.search_type != "string"
    },
}
