from typing import Any
from uuid import UUID, uuid4

import orjson
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from sentry import features
from sentry.api.fields.actor import ActorField
from sentry.constants import MIGRATED_CONDITIONS, TICKET_ACTIONS
from sentry.models.environment import Environment
from sentry.rules import rules
from sentry.rules.actions.sentry_apps.base import SentryAppEventAction


@extend_schema_field(field=OpenApiTypes.OBJECT)
class RuleNodeField(serializers.Field):
    def __init__(self, type):
        super().__init__()
        self.type_name = type

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = orjson.loads(data.replace("'", '"'))
            except Exception:
                raise ValidationError("Failed trying to parse dict from string")
        elif not isinstance(data, dict):
            msg = "Incorrect type. Expected a mapping, but got %s"
            raise ValidationError(msg % type(data).__name__)

        if "id" not in data:
            raise ValidationError("Missing attribute 'id'")

        for key, value in list(data.items()):
            if not value:
                del data[key]

        cls = rules.get(data["id"], self.type_name)
        if cls is None:
            msg = "Invalid node. Could not find '%s'"
            raise ValidationError(msg % data["id"])

        # instance of a RuleBase class
        node = cls(project=self.context["project"], data=data)

        # Nodes with user-declared fields will manage their own validation
        if isinstance(node, SentryAppEventAction):
            if not data.get("hasSchemaFormConfig"):
                raise ValidationError("Please configure your integration settings.")
            node.self_validate()
            return data

        form = node.get_form_instance()
        if not form:
            return data

        if not form.is_valid():
            # XXX(epurkhiser): Very hacky, but we really just want validation
            # errors that are more specific, not just 'this wasn't filled out',
            # give a more generic error for those.
            # Still hacky, but a bit clearer, for each field there can be a list of errors so
            # we get the first error's message for each field and then get the first error message from that list
            first_error_message = [
                error_list[0]["message"]
                for field, error_list in form.errors.get_json_data().items()
            ][0]

            if first_error_message != "This field is required.":
                raise ValidationError(first_error_message)

            raise ValidationError("Ensure all required fields are filled in.")

        # Update data from cleaned form values
        data.update(form.cleaned_data)

        if getattr(form, "_pending_save", False):
            data["pending_save"] = True
        return data


class RuleSetSerializer(serializers.Serializer):
    conditions = serializers.ListField(child=RuleNodeField(type="condition/event"), required=False)
    filters = serializers.ListField(child=RuleNodeField(type="filter/event"), required=False)
    actionMatch = serializers.ChoiceField(
        choices=(("all", "all"), ("any", "any"), ("none", "none"))
    )
    filterMatch = serializers.ChoiceField(
        choices=(("all", "all"), ("any", "any"), ("none", "none")), required=False
    )
    frequency = serializers.IntegerField(min_value=5, max_value=60 * 24 * 30)

    def validate(self, attrs):
        # ensure that if filters are passed in that a filterMatch is also supplied
        filters = attrs.get("filters")
        if filters:
            filter_match = attrs.get("filterMatch")
            if not filter_match:
                raise serializers.ValidationError(
                    {
                        "filterMatch": "Must select a filter match (all, any, none) if filters are supplied."
                    }
                )

        # ensure that if a user has alert-filters enabled, they do not use old conditions
        project = self.context["project"]
        conditions = attrs.get("conditions", tuple())
        project_has_filters = features.has("projects:alert-filters", project)
        if project_has_filters:
            old_conditions = [
                condition for condition in conditions if condition["id"] in MIGRATED_CONDITIONS
            ]
            if old_conditions:
                raise serializers.ValidationError(
                    {
                        "conditions": "Conditions evaluating an event attribute, tag, or level are outdated please use an appropriate filter instead."
                    }
                )

        # ensure that if a user has alert-filters enabled, they do not use a 'none' match on conditions
        if project_has_filters and attrs.get("actionMatch") == "none":
            raise serializers.ValidationError(
                {
                    "conditions": "The 'none' match on conditions is outdated and no longer supported."
                }
            )

        return attrs


class RulePreviewSerializer(RuleSetSerializer):
    endpoint = serializers.DateTimeField(required=False, allow_null=True)


class DummyRuleSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=256, required=False, allow_null=True, allow_blank=True, default="Test Alert"
    )
    actions = serializers.ListField(child=RuleNodeField(type="action/event"), required=False)

    def validate_name(self, name):
        if name == "" or name is None:
            return "Test Alert"
        return name

    def validate(self, attrs):
        return validate_actions(attrs)


class RuleSerializer(RuleSetSerializer):
    name = serializers.CharField(max_length=256)
    environment = serializers.CharField(max_length=64, required=False, allow_null=True)
    actions = serializers.ListField(child=RuleNodeField(type="action/event"), required=False)
    owner = ActorField(required=False, allow_null=True)

    def validate_environment(self, environment):
        if environment is None:
            return environment

        try:
            environment = Environment.get_for_organization_id(
                self.context["project"].organization_id, environment
            ).id
        except Environment.DoesNotExist:
            raise serializers.ValidationError("This environment has not been created.")

        return environment

    def validate_conditions(self, conditions):
        for condition in conditions:
            if condition.get("name"):
                del condition["name"]

        return conditions

    def validate(self, attrs):
        return super().validate(validate_actions(attrs))


ACTION_UUID_KEY = "uuid"


def ensure_action_uuid(action: dict[Any, Any]) -> None:
    """
    Ensure that each action is uniquely identifiable.
    The function will check that a UUID key and value exists in the action.
    If the key does not exist, or it's not a valid UUID, it will create a new one and assign it to the action.

    Does not add an uuid to the action if it is empty.
    """
    if not action:
        return

    if ACTION_UUID_KEY in action:
        existing_uuid = action[ACTION_UUID_KEY]
        try:
            UUID(existing_uuid)
        except (ValueError, TypeError):
            pass
        else:
            return

    action[ACTION_UUID_KEY] = str(uuid4())


def validate_actions(attrs):
    # XXX(meredith): For rules that have the Slack integration as an action
    # we need to check if the channel_id needs to be looked up via an async task.
    # If the "pending_save" attribute is set we want to bubble that up to the
    # project_rule(_details) endpoints by setting it on attrs
    actions = attrs.get("actions", tuple())
    for action in actions:
        ensure_action_uuid(action)

        if action.get("name"):
            del action["name"]
        # XXX(colleen): For ticket rules we need to ensure the user has
        # at least done minimal configuration
        if action["id"] in TICKET_ACTIONS:
            if not action.get("dynamic_form_fields"):
                raise serializers.ValidationError(
                    {"actions": "Must configure issue link settings."}
                )
        # remove this attribute because we don't want it to be saved in the rule
        if action.pop("pending_save", None):
            attrs["pending_save"] = True
            break

    return attrs
