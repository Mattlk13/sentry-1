from collections.abc import Mapping
from typing import Any

from sentry.constants import ObjectStatus, SentryAppStatus
from sentry.incidents.endpoints.organization_alert_rule_available_action_index import (
    build_action_response,
)
from sentry.incidents.models.alert_rule import AlertRuleTriggerAction
from sentry.integrations.models.organization_integration import OrganizationIntegration
from sentry.integrations.pagerduty.utils import add_service
from sentry.integrations.services.integration.serial import serialize_integration
from sentry.sentry_apps.models.sentry_app_component import SentryAppComponent
from sentry.sentry_apps.models.sentry_app_installation import SentryAppInstallation
from sentry.sentry_apps.services.app.serial import serialize_sentry_app_installation
from sentry.silo.base import SiloMode
from sentry.testutils.cases import APITestCase
from sentry.testutils.silo import assume_test_silo_mode

SERVICES = [
    {
        "type": "service",
        "integration_key": "PND4F9",
        "service_id": "123",
        "service_name": "hellboi",
    }
]

METADATA = {
    "api_key": "1234-ABCD",
    "base_url": "https://api.opsgenie.com/",
    "domain_name": "test-app.app.opsgenie.com",
}


class OrganizationAlertRuleAvailableActionIndexEndpointTest(APITestCase):
    endpoint = "sentry-api-0-organization-alert-rule-available-actions"
    email = AlertRuleTriggerAction.get_registered_factory(AlertRuleTriggerAction.Type.EMAIL)
    slack = AlertRuleTriggerAction.get_registered_factory(AlertRuleTriggerAction.Type.SLACK)
    sentry_app = AlertRuleTriggerAction.get_registered_factory(
        AlertRuleTriggerAction.Type.SENTRY_APP
    )
    pagerduty = AlertRuleTriggerAction.get_registered_factory(AlertRuleTriggerAction.Type.PAGERDUTY)
    opsgenie = AlertRuleTriggerAction.get_registered_factory(AlertRuleTriggerAction.Type.OPSGENIE)

    def setUp(self) -> None:
        super().setUp()
        self.login_as(self.user)

    def install_new_sentry_app(self, name, **kwargs) -> SentryAppInstallation:
        kwargs.update(
            name=name, organization=self.organization, is_alertable=True, verify_install=False
        )
        sentry_app = self.create_sentry_app(**kwargs)
        installation = self.create_sentry_app_installation(
            slug=sentry_app.slug, organization=self.organization, user=self.user
        )
        return installation

    def test_build_action_response_email(self) -> None:
        data = build_action_response(self.email)

        assert data["type"] == "email"
        assert sorted(data["allowedTargetTypes"]) == ["team", "user"]

    def test_build_action_response_slack(self) -> None:
        data = build_action_response(self.slack)

        assert data["type"] == "slack"
        assert data["allowedTargetTypes"] == ["specific"]

    def test_build_action_response_opsgenie(self) -> None:
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_provider_integration(
                provider="opsgenie", name="test-app", external_id="test-app", metadata=METADATA
            )
            integration.add_organization(self.organization, self.user)
            org_integration = OrganizationIntegration.objects.get(
                organization_id=self.organization.id, integration_id=integration.id
            )
            org_integration.config = {
                "team_table": [
                    {"id": "123-id", "team": "cool-team", "integration_key": "1234-5678"}
                ]
            }
            org_integration.save()
        data = build_action_response(
            self.opsgenie,
            integration=serialize_integration(integration),
            organization=self.organization,
        )

        assert data["type"] == "opsgenie"
        assert data["allowedTargetTypes"] == ["specific"]
        assert data["options"] == [{"value": "123-id", "label": "cool-team"}]

    def test_build_action_response_pagerduty(self) -> None:
        service_name = SERVICES[0]["service_name"]
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_provider_integration(
                provider="pagerduty",
                name="Example PagerDuty",
                external_id="example-pagerduty",
                metadata={"services": SERVICES},
            )
            org_integration = integration.add_organization(self.organization, self.user)
            assert org_integration is not None
            service = add_service(
                org_integration,
                service_name=service_name,
                integration_key=SERVICES[0]["integration_key"],
            )

        data = build_action_response(
            self.pagerduty,
            integration=serialize_integration(integration),
            organization=self.organization,
        )

        assert data["type"] == "pagerduty"
        assert data["allowedTargetTypes"] == ["specific"]
        assert data["options"] == [{"value": service["id"], "label": service_name}]

    def test_build_action_response_sentry_app(self) -> None:
        installation = self.install_new_sentry_app("foo")

        data = build_action_response(
            self.sentry_app, sentry_app_installation=serialize_sentry_app_installation(installation)
        )

        assert data["type"] == "sentry_app"
        assert data["allowedTargetTypes"] == ["sentry_app"]
        assert data["status"] == SentryAppStatus.UNPUBLISHED_STR

    def test_build_action_response_sentry_app_with_component(self) -> None:
        installation = self.install_new_sentry_app("foo")
        test_settings: Mapping[str, Any] = {"test-settings": []}
        with assume_test_silo_mode(SiloMode.CONTROL):
            SentryAppComponent.objects.create(
                sentry_app=installation.sentry_app,
                type="alert-rule-action",
                schema={"settings": test_settings},
            )

        data = build_action_response(
            self.sentry_app, sentry_app_installation=serialize_sentry_app_installation(installation)
        )

        assert data["settings"] == test_settings

    def test_no_integrations(self) -> None:
        with self.feature("organizations:incidents"):
            response = self.get_success_response(self.organization.slug)

        assert response.data == [build_action_response(self.email)]

    def test_simple(self) -> None:
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_provider_integration(external_id="1", provider="slack")
            integration.add_organization(self.organization)

        with self.feature("organizations:incidents"):
            response = self.get_success_response(self.organization.slug)

        assert len(response.data) == 2
        assert build_action_response(self.email) in response.data
        assert (
            build_action_response(
                self.slack,
                integration=serialize_integration(integration),
                organization=self.organization,
            )
            in response.data
        )

    def test_duplicate_integrations(self) -> None:
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_provider_integration(
                external_id="1", provider="slack", name="slack 1"
            )
            integration.add_organization(self.organization)
            other_integration = self.create_provider_integration(
                external_id="2", provider="slack", name="slack 2"
            )
            other_integration.add_organization(self.organization)

        with self.feature("organizations:incidents"):
            response = self.get_success_response(self.organization.slug)

        assert len(response.data) == 3
        assert build_action_response(self.email) in response.data
        assert (
            build_action_response(
                self.slack,
                integration=serialize_integration(integration),
                organization=self.organization,
            )
            in response.data
        )
        assert (
            build_action_response(
                self.slack,
                integration=serialize_integration(other_integration),
                organization=self.organization,
            )
            in response.data
        )

    def test_no_feature(self) -> None:
        self.create_team(organization=self.organization, members=[self.user])
        self.get_error_response(self.organization.slug, status_code=404)

    def test_sentry_apps(self) -> None:
        installation = self.install_new_sentry_app("foo")

        with self.feature("organizations:incidents"):
            response = self.get_success_response(self.organization.slug)

        assert len(response.data) == 2
        assert build_action_response(self.email) in response.data
        assert (
            build_action_response(
                self.sentry_app,
                sentry_app_installation=serialize_sentry_app_installation(installation),
            )
            in response.data
        )

    def test_published_sentry_apps(self) -> None:
        # Should show up in available actions.
        installation = self.install_new_sentry_app("published", published=True)

        with self.feature("organizations:incidents"):
            response = self.get_success_response(self.organization.slug)

        assert len(response.data) == 2
        assert (
            build_action_response(
                self.sentry_app,
                sentry_app_installation=serialize_sentry_app_installation(installation),
            )
            in response.data
        )

    def test_no_ticket_actions(self) -> None:
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_provider_integration(external_id="1", provider="jira")
            integration.add_organization(self.organization)

        with self.feature(["organizations:incidents", "organizations:integrations-ticket-rules"]):
            response = self.get_success_response(self.organization.slug)

        # There should be no ticket actions for Metric Alerts.
        assert len(response.data) == 1
        assert build_action_response(self.email) in response.data

    def test_integration_disabled(self) -> None:
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_provider_integration(
                external_id="1", provider="slack", status=ObjectStatus.DISABLED
            )
            integration.add_organization(self.organization)

        with self.feature("organizations:incidents"):
            response = self.get_success_response(self.organization.slug)

        assert len(response.data) == 1
        assert build_action_response(self.email) in response.data

    def test_org_integration_disabled(self) -> None:
        integration, org_integration = self.create_provider_integration_for(
            self.organization, user=None, external_id="1", provider="slack"
        )
        with assume_test_silo_mode(SiloMode.CONTROL):
            org_integration.update(status=ObjectStatus.DISABLED)

        with self.feature("organizations:incidents"):
            response = self.get_success_response(self.organization.slug)

        assert len(response.data) == 1
        assert build_action_response(self.email) in response.data
