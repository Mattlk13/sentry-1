import time
from typing import cast
from unittest.mock import MagicMock, patch

import orjson
import responses
from urllib3.response import HTTPResponse

from sentry.analytics.events.alert_sent import AlertSentEvent
from sentry.incidents.logic import update_incident_status
from sentry.incidents.models.alert_rule import (
    AlertRuleDetectionType,
    AlertRuleSeasonality,
    AlertRuleSensitivity,
    AlertRuleTriggerAction,
)
from sentry.incidents.models.incident import IncidentStatus, IncidentStatusMethod
from sentry.incidents.typings.metric_detector import AlertContext, MetricIssueContext
from sentry.integrations.messaging.spec import MessagingActionHandler
from sentry.integrations.msteams.card_builder.block import (
    Block,
    ColumnBlock,
    ColumnSetBlock,
    ContainerBlock,
    TextBlock,
)
from sentry.integrations.msteams.spec import MsTeamsMessagingSpec
from sentry.integrations.types import EventLifecycleOutcome
from sentry.seer.anomaly_detection.types import StoreDataResponse
from sentry.silo.base import SiloMode
from sentry.testutils.asserts import assert_slo_metric
from sentry.testutils.helpers.analytics import assert_last_analytics_event
from sentry.testutils.helpers.datetime import freeze_time
from sentry.testutils.helpers.features import with_feature
from sentry.testutils.silo import assume_test_silo_mode
from sentry.utils import json

from . import FireTest


@freeze_time()
class MsTeamsActionHandlerTest(FireTest):
    @responses.activate
    def setUp(self) -> None:
        self.spec = MsTeamsMessagingSpec()
        self.handler = MessagingActionHandler(self.spec)

        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_provider_integration(
                provider="msteams",
                name="Galactic Empire",
                external_id="D4r7h_Pl4gu315_th3_w153",
                metadata={
                    "service_url": "https://smba.trafficmanager.net/amer",
                    "access_token": "d4rk51d3",
                    "expires_at": int(time.time()) + 86400,
                },
            )
            integration.add_organization(self.organization, self.user)

        channel_id = "d_s"
        channel_name = "Death Star"
        channels = [{"id": channel_id, "name": channel_name}]

        responses.add(
            method=responses.GET,
            url="https://smba.trafficmanager.net/amer/v3/teams/D4r7h_Pl4gu315_th3_w153/conversations",
            json={"conversations": channels},
        )

        self.action = self.create_alert_rule_trigger_action(
            target_identifier=channel_name,
            type=AlertRuleTriggerAction.Type.MSTEAMS,
            target_type=AlertRuleTriggerAction.TargetType.SPECIFIC,
            integration=integration,
        )

    @responses.activate
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def run_test(self, incident, method, mock_record):
        from sentry.integrations.msteams.card_builder.incident_attachment import (
            build_incident_attachment,
        )

        responses.add(
            method=responses.POST,
            url="https://smba.trafficmanager.net/amer/v3/conversations/d_s/activities",
            status=200,
            json={},
        )

        metric_value = 1000
        with self.tasks():
            self.handler.fire(
                action=self.action,
                incident=incident,
                project=self.project,
                metric_value=metric_value,
                new_status=IncidentStatus(incident.status),
            )
        data = json.loads(responses.calls[0].request.body)

        assert data["attachments"][0]["content"] == build_incident_attachment(
            alert_context=AlertContext.from_alert_rule_incident(incident.alert_rule),
            metric_issue_context=MetricIssueContext.from_legacy_models(
                incident, IncidentStatus(incident.status), metric_value
            ),
            organization=incident.organization,
            date_started=incident.date_started,
        )

        assert_slo_metric(mock_record)

    @responses.activate
    def test_build_incident_attachment(self) -> None:
        from sentry.integrations.msteams.card_builder.incident_attachment import (
            build_incident_attachment,
        )

        alert_rule = self.create_alert_rule()
        incident = self.create_incident(alert_rule=alert_rule)
        update_incident_status(
            incident, IncidentStatus.CRITICAL, status_method=IncidentStatusMethod.RULE_TRIGGERED
        )
        responses.add(
            method=responses.POST,
            url="https://smba.trafficmanager.net/amer/v3/conversations/d_s/activities",
            status=200,
            json={},
        )
        metric_value = 1000
        data = build_incident_attachment(
            alert_context=AlertContext.from_alert_rule_incident(alert_rule),
            metric_issue_context=MetricIssueContext.from_legacy_models(
                incident, IncidentStatus(incident.status), metric_value
            ),
            organization=incident.organization,
            date_started=incident.date_started,
        )
        body: list[Block] = data["body"]
        column_set_block = cast(ColumnSetBlock, body[0])
        column_blocks: list[ColumnBlock] = column_set_block["columns"]
        column_block: ColumnBlock = column_blocks[1]
        container = cast(ContainerBlock, column_block["items"][0])
        text_block = cast(TextBlock, container["items"][1])
        assert text_block["text"] == "1000 events in the last 10 minutes"
        text_block2 = cast(TextBlock, container["items"][0])
        assert alert_rule.name in text_block2["text"]
        assert (
            f"http://testserver/organizations/baz/alerts/rules/details/{alert_rule.id}/?alert={incident.identifier}&referrer=metric_alert_msteams&detection_type={alert_rule.detection_type}"
            in text_block2["text"]
        )

    @responses.activate
    @with_feature("organizations:anomaly-detection-alerts")
    @patch(
        "sentry.seer.anomaly_detection.store_data.seer_anomaly_detection_connection_pool.urlopen"
    )
    def test_build_incident_attachment_dynamic_alert(self, mock_seer_request: MagicMock) -> None:
        from sentry.integrations.msteams.card_builder.incident_attachment import (
            build_incident_attachment,
        )

        seer_return_value: StoreDataResponse = {"success": True}
        mock_seer_request.return_value = HTTPResponse(orjson.dumps(seer_return_value), status=200)
        alert_rule = self.create_alert_rule(
            detection_type=AlertRuleDetectionType.DYNAMIC,
            time_window=30,
            sensitivity=AlertRuleSensitivity.LOW,
            seasonality=AlertRuleSeasonality.AUTO,
        )
        incident = self.create_incident(alert_rule=alert_rule, status=IncidentStatus.CRITICAL.value)
        self.create_alert_rule_trigger(alert_rule=alert_rule, alert_threshold=0)
        responses.add(
            method=responses.POST,
            url="https://smba.trafficmanager.net/amer/v3/conversations/d_s/activities",
            status=200,
            json={},
        )
        metric_value = 1000
        data = build_incident_attachment(
            alert_context=AlertContext.from_alert_rule_incident(alert_rule),
            metric_issue_context=MetricIssueContext.from_legacy_models(
                incident, IncidentStatus(incident.status), metric_value
            ),
            organization=incident.organization,
            date_started=incident.date_started,
        )
        body: list[Block] = data["body"]
        column_set_block = cast(ColumnSetBlock, body[0])
        column_blocks: list[ColumnBlock] = column_set_block["columns"]
        column_block: ColumnBlock = column_blocks[1]
        container = cast(ContainerBlock, column_block["items"][0])
        text_block = cast(TextBlock, container["items"][1])
        text_block2 = cast(TextBlock, container["items"][0])
        assert (
            text_block["text"]
            == f"1000 events in the last 30 minutes\nThreshold: {alert_rule.detection_type.title()}"
        )
        assert alert_rule.name in text_block2["text"]
        assert (
            f"http://testserver/organizations/baz/alerts/rules/details/{alert_rule.id}/?alert={incident.identifier}&referrer=metric_alert_msteams&detection_type={alert_rule.detection_type}"
            in text_block2["text"]
        )

    def test_fire_metric_alert(self) -> None:
        self.run_fire_test()

    def test_resolve_metric_alert(self) -> None:
        self.run_fire_test("resolve")

    @patch("sentry.analytics.record")
    def test_alert_sent_recorded(self, mock_record: MagicMock) -> None:
        self.run_fire_test()
        assert_last_analytics_event(
            mock_record,
            AlertSentEvent(
                organization_id=self.organization.id,
                project_id=self.project.id,
                provider="msteams",
                alert_id=str(self.alert_rule.id),
                alert_type="metric_alert",
                external_id=str(self.action.target_identifier),
                notification_uuid="",
            ),
        )

    @responses.activate
    def test_rule_snoozed(self) -> None:
        alert_rule = self.create_alert_rule()
        incident = self.create_incident(alert_rule=alert_rule, status=IncidentStatus.CLOSED.value)
        self.snooze_rule(alert_rule=alert_rule)
        responses.add(
            method=responses.POST,
            url="https://smba.trafficmanager.net/amer/v3/conversations/d_s/activities",
            status=200,
            json={},
        )

        metric_value = 1000
        with self.tasks():
            self.handler.fire(
                action=self.action,
                incident=incident,
                project=self.project,
                metric_value=metric_value,
                new_status=IncidentStatus(incident.status),
            )

        assert len(responses.calls) == 0

    @responses.activate
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_fire_metric_alert_failure(self, mock_record: MagicMock) -> None:
        self.alert_rule = self.create_alert_rule()
        incident = self.create_incident(
            alert_rule=self.alert_rule, status=IncidentStatus.CLOSED.value
        )

        responses.add(
            method=responses.POST,
            url="https://smba.trafficmanager.net/amer/v3/conversations/d_s/activities",
            status=500,
            json={},
        )

        metric_value = 1000
        with self.tasks():
            self.handler.fire(
                action=self.action,
                incident=incident,
                project=self.project,
                metric_value=metric_value,
                new_status=IncidentStatus(incident.status),
            )

        assert_slo_metric(mock_record, EventLifecycleOutcome.FAILURE)

    @responses.activate
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_fire_metric_alert_halt(self, mock_record: MagicMock) -> None:
        self.alert_rule = self.create_alert_rule()
        incident = self.create_incident(
            alert_rule=self.alert_rule, status=IncidentStatus.CLOSED.value
        )

        responses.add(
            method=responses.POST,
            url="https://smba.trafficmanager.net/amer/v3/conversations/d_s/activities",
            status=403,
            json={
                "error": {
                    "code": "ConversationBlockedByUser",
                    "message": "User blocked the conversation with the bot.",
                }
            },
        )

        metric_value = 1000
        with self.tasks():
            self.handler.fire(
                action=self.action,
                incident=incident,
                project=self.project,
                metric_value=metric_value,
                new_status=IncidentStatus(incident.status),
            )

        assert_slo_metric(mock_record, EventLifecycleOutcome.HALTED)
