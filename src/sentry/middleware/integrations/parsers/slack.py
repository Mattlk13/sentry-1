from __future__ import annotations

import logging
from collections.abc import Sequence
from urllib.parse import parse_qs

import orjson
import sentry_sdk
from django.http.response import HttpResponse, HttpResponseBase
from rest_framework import status
from rest_framework.request import Request
from slack_sdk.errors import SlackApiError

from sentry.hybridcloud.outbox.category import WebhookProviderIdentifier
from sentry.hybridcloud.services.organization_mapping.model import RpcOrganizationMapping
from sentry.integrations.messaging import commands
from sentry.integrations.middleware.hybrid_cloud.parser import (
    BaseRequestParser,
    create_async_request_payload,
)
from sentry.integrations.models.integration import Integration
from sentry.integrations.slack.message_builder.routing import SlackRoutingData, decode_action_id
from sentry.integrations.slack.requests.base import SlackRequestError
from sentry.integrations.slack.requests.event import is_event_challenge
from sentry.integrations.slack.sdk_client import SlackSdkClient
from sentry.integrations.slack.views import SALT
from sentry.integrations.slack.views.link_identity import SlackLinkIdentityView
from sentry.integrations.slack.views.link_team import SlackLinkTeamView
from sentry.integrations.slack.views.unlink_identity import SlackUnlinkIdentityView
from sentry.integrations.slack.views.unlink_team import SlackUnlinkTeamView
from sentry.integrations.slack.webhooks.action import (
    NOTIFICATION_SETTINGS_ACTION_OPTIONS,
    UNFURL_ACTION_OPTIONS,
    SlackActionEndpoint,
)
from sentry.integrations.slack.webhooks.base import SlackDMEndpoint
from sentry.integrations.slack.webhooks.command import SlackCommandsEndpoint
from sentry.integrations.slack.webhooks.event import SlackEventEndpoint
from sentry.integrations.slack.webhooks.options_load import SlackOptionsLoadEndpoint
from sentry.integrations.types import EXTERNAL_PROVIDERS, ExternalProviders
from sentry.middleware.integrations.tasks import convert_to_async_slack_response
from sentry.types.region import Region
from sentry.utils import json
from sentry.utils.signing import unsign

logger = logging.getLogger(__name__)

ACTIONS_ENDPOINT_ALL_SILOS_ACTIONS = UNFURL_ACTION_OPTIONS + NOTIFICATION_SETTINGS_ACTION_OPTIONS


class SlackRequestParser(BaseRequestParser):
    provider = EXTERNAL_PROVIDERS[ExternalProviders.SLACK]  # "slack"
    webhook_identifier = WebhookProviderIdentifier.SLACK
    response_url: str | None = None
    action_option: str | None = None

    control_classes = [
        SlackLinkIdentityView,
        SlackUnlinkIdentityView,
    ]

    region_classes = [
        SlackLinkTeamView,
        SlackUnlinkTeamView,
        SlackCommandsEndpoint,
        SlackEventEndpoint,
        SlackOptionsLoadEndpoint,
    ]

    webhook_endpoints = [
        SlackCommandsEndpoint,
        SlackActionEndpoint,
        SlackEventEndpoint,
        SlackOptionsLoadEndpoint,
    ]
    """
    Endpoints which provide integration info in the request headers.
    See: `src/sentry/integrations/slack/webhooks`
    """

    django_views = [
        SlackLinkTeamView,
        SlackUnlinkTeamView,
        SlackLinkIdentityView,
        SlackUnlinkIdentityView,
    ]
    """
    Views which contain integration info in query params
    See: `src/sentry/integrations/slack/views`
    """

    def build_loading_modal(self, external_id: str, title: str):
        return {
            "type": "modal",
            "external_id": external_id,
            "title": {"type": "plain_text", "text": title},
            "blocks": [
                {
                    "type": "section",
                    "block_id": "loading_block",
                    "text": {"type": "mrkdwn", "text": "Loading..."},
                }
            ],
        }

    def parse_slack_payload(self, request) -> tuple[dict, str]:
        try:
            decoded_body = parse_qs(request.body.decode(encoding="utf-8"))
            payload_list = decoded_body.get("payload")

            if not payload_list or not isinstance(payload_list, list) or len(payload_list) != 1:
                raise ValueError(
                    "Error parsing Slack payload: 'payload' not found or not a list of length 1"
                )

            payload = json.loads(payload_list[0])

            # Extract action_ts from the payload
            # we need to grab the action_ts to use as the external_id for the loading modal
            # https://api.slack.com/reference/interaction-payloads/block-actions
            actions = payload.get("actions", None)
            if not actions or not isinstance(actions, list):
                raise ValueError("Error parsing Slack payload: 'actions' not found")
            if len(actions) != 1:
                raise ValueError("Error parsing Slack payload: 'actions' not a list of length 1")

            (action,) = actions  # we only expect one action in the list
            action_ts = action.get("action_ts")
            if action_ts is None:
                raise ValueError("Error parsing Slack payload: 'action_ts' not found in 'actions'")
            return payload, action_ts

        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Error parsing Slack payload: {str(e)}")

    def handle_dialog(self, request, action: str, title: str) -> None:
        payload, action_ts = self.parse_slack_payload(request)

        integration = self.get_integration_from_request()
        if not integration:
            raise ValueError("integration not found")

        slack_client = SlackSdkClient(integration_id=integration.id)
        loading_modal = self.build_loading_modal(action_ts, title)

        try:
            slack_client.views_open(
                trigger_id=payload["trigger_id"],
                view=loading_modal,
            )
        except SlackApiError:
            logger_params = {
                "integration_id": integration.id,
                "action": action,
            }
            logger.info("slack.control.view.open.failure", extra=logger_params)

    def get_async_region_response(self, regions: Sequence[Region]) -> HttpResponseBase:
        if self.response_url is None:
            return self.get_response_from_control_silo()

        CONTROL_RESPONSE_ACTIONS = {
            "resolve_dialog": lambda request, action: self.handle_dialog(
                request, action, "Resolve Issue"
            ),
            "archive_dialog": lambda request, action: self.handle_dialog(
                request, action, "Archive Issue"
            ),
            # Add more actions here, ie for buttons in modal
        }

        integration = self.get_integration_from_request()

        # if we are able to  send a response to Slack from control itself to beat the 3 second timeout, we should do so
        try:
            if self.action_option in CONTROL_RESPONSE_ACTIONS:
                CONTROL_RESPONSE_ACTIONS[self.action_option](self.request, self.action_option)
        except ValueError:
            logger.exception(
                "slack.control.response.error",
                extra={
                    "integration_id": integration and integration.id,
                    "action": self.action_option,
                },
            )

        convert_to_async_slack_response.apply_async(
            kwargs={
                "region_names": [r.name for r in regions],
                "payload": create_async_request_payload(self.request),
                "response_url": self.response_url,
            }
        )

        # Return a 200 OK response to Slack even if we rendered the modal b/c we are sending an async response
        return HttpResponse(status=status.HTTP_200_OK)

    def get_integration_from_request(self) -> Integration | None:
        if self.view_class in self.webhook_endpoints:
            # We need convert the raw Django request to a Django Rest Framework request
            # since that's the type the SlackRequest expects
            drf_request: Request = SlackDMEndpoint().initialize_request(self.request)
            slack_request = self.view_class.slack_request_class(drf_request)
            try:
                slack_request.authorize()
                slack_request.validate_integration()
            except SlackRequestError as error:
                logger.info(
                    "slack.validation_error", extra={"path": self.request.path, "error": error}
                )
                return None
            self.response_url = slack_request.response_url
            return Integration.objects.filter(id=slack_request.integration.id).first()

        elif self.view_class in self.django_views:
            # Parse the signed params to identify the associated integration
            params = unsign(self.match.kwargs["signed_params"], salt=SALT)
            return Integration.objects.filter(id=params["integration_id"]).first()

        return None

    def filter_organizations_from_request(
        self,
        organizations: list[RpcOrganizationMapping],
    ) -> list[RpcOrganizationMapping]:
        """
        For linking/unlinking teams, we can target specific organizations if the user provides it
        as an additional argument. If not, we'll pick from all the organizations, which might fail.
        """

        drf_request: Request
        if self.view_class == SlackCommandsEndpoint:
            drf_request = SlackDMEndpoint().initialize_request(self.request)
            slack_request = self.view_class.slack_request_class(drf_request)
            cmd_input = slack_request.get_command_input()

            # For both linking/unlinking teams, the organization slug is found in the same place
            link_input = None
            if commands.LINK_TEAM.command_slug.does_match(cmd_input):
                link_input = cmd_input.adjust(commands.LINK_TEAM.command_slug)
            elif commands.UNLINK_TEAM.command_slug.does_match(cmd_input):
                link_input = cmd_input.adjust(commands.UNLINK_TEAM.command_slug)
            if not link_input or not link_input.arg_values:
                return organizations

            linking_organization_slug = link_input.arg_values[0]
            linking_organization = next(
                (org for org in organizations if org.slug == linking_organization_slug), None
            )
            if linking_organization:
                logger.info(
                    "slack.control.routed_to_organization",
                    extra={"view_class": self.view_class},
                )
                return [linking_organization]

        elif self.view_class in [SlackActionEndpoint, SlackOptionsLoadEndpoint]:
            drf_request = SlackDMEndpoint().initialize_request(self.request)
            slack_request = self.view_class.slack_request_class(drf_request)
            if self.view_class == SlackActionEndpoint:
                actions = slack_request.data.get("actions", [])
                action_ids: list[str] = [
                    action["action_id"] for action in actions if action.get("action_id")
                ]
            elif self.view_class == SlackOptionsLoadEndpoint:
                action_ids = [slack_request.data.get("action_id", "")]

            decoded_actions: list[SlackRoutingData] = [
                decode_action_id(action_id) for action_id in action_ids
            ]
            decoded_organization_ids = {
                action.organization_id for action in decoded_actions if action.organization_id
            }
            if len(decoded_organization_ids) > 1:
                # We shouldn't be encoding multiple organizations into the actions within a single
                # message, but if we do -- log it so we can look into it.
                logger.info(
                    "slack.control.multiple_organizations",
                    extra={
                        "integration_id": slack_request.integration.id,
                        "organization_ids": list(decoded_organization_ids),
                        "action_ids": action_ids,
                    },
                )

            action_organization = next(
                (org for org in organizations if org.id in decoded_organization_ids), None
            )
            if action_organization:
                logger.info(
                    "slack.control.routed_to_organization",
                    extra={"view_class": self.view_class},
                )
                return [action_organization]

        logger.info(
            "slack.control.could_not_route",
            extra={"view_class": self.view_class},
        )
        return organizations

    def get_response(self):
        """
        Slack Webhook Requests all require synchronous responses.
        """
        if self.view_class in self.control_classes:
            return self.get_response_from_control_silo()

        # Handle event interactions challenge request
        data = None
        try:
            data = orjson.loads(self.request.body)
        except orjson.JSONDecodeError:
            pass
        if data and is_event_challenge(data):
            return self.get_response_from_control_silo()

        try:
            regions = self.get_regions_from_organizations()
        except Integration.DoesNotExist:
            # Alert, as there may be a misconfiguration issue
            sentry_sdk.capture_exception()
            return self.get_default_missing_integration_response()

        if len(regions) == 0:
            # Swallow this exception, as this is likely due to a user removing
            # their org's slack integration, and slack will continue to retry
            # this request until it succeeds.
            return HttpResponse(status=status.HTTP_202_ACCEPTED)

        if self.view_class == SlackActionEndpoint:
            drf_request: Request = SlackDMEndpoint().initialize_request(self.request)
            slack_request = self.view_class.slack_request_class(drf_request)
            self.response_url = slack_request.response_url
            self.action_option = SlackActionEndpoint.get_action_option(slack_request=slack_request)
            # All actions other than those below are sent to every region
            if self.action_option not in ACTIONS_ENDPOINT_ALL_SILOS_ACTIONS:
                return (
                    self.get_async_region_response(regions=regions)
                    if self.response_url
                    else self.get_response_from_all_regions()
                )

        # Slack webhooks can only receive one synchronous call/response, as there are many
        # places where we post to slack on their webhook request. This would cause multiple
        # calls back to slack for every region we forward to.
        # By convention, we use the first integration organization/region
        return (
            self.get_async_region_response(regions=[regions[0]])
            if self.response_url
            else self.get_response_from_first_region()
        )
