from collections.abc import Mapping
from time import time
from typing import Any

import responses

from sentry.integrations.models.integration import Integration
from sentry.integrations.vsts.tasks.kickoff_subscription_check import (
    kickoff_vsts_subscription_check,
)
from sentry.testutils.cases import TestCase
from sentry.testutils.silo import control_silo_test
from sentry.users.models.identity import Identity

PROVIDER = "vsts"


def _get_subscription_data(external_id: str) -> Mapping[str, Any]:
    integration = Integration.objects.get(provider=PROVIDER, external_id=external_id)
    return integration.metadata["subscription"]


def assert_no_subscription(external_id: str, subscription_id: str) -> None:
    subscription_data = _get_subscription_data(external_id)

    assert subscription_data["id"] == subscription_id
    assert "check" not in subscription_data
    assert "secret" not in subscription_data


def assert_subscription(
    external_id: str, subscription_id: str, check_time: float | None = None
) -> None:
    subscription_data = _get_subscription_data(external_id)

    assert subscription_data["id"] == subscription_id
    assert subscription_data["check"]
    assert subscription_data["secret"]

    if check_time:
        assert check_time == subscription_data["check"]


@control_silo_test
class VstsSubscriptionCheckTest(TestCase):
    def setUp(self) -> None:
        responses.add(
            responses.GET,
            "https://vsts1.visualstudio.com/_apis/hooks/subscriptions/subscription1",
            json={"status": "disabledBySystem"},
        )
        responses.add(
            responses.DELETE,
            "https://vsts1.visualstudio.com/_apis/hooks/subscriptions/subscription1",
            json={},
        )
        responses.add(
            responses.POST,
            "https://vsts1.visualstudio.com/_apis/hooks/subscriptions",
            json={"id": "subscription1_new_id"},
        )
        responses.add(
            responses.GET,
            "https://vsts1.visualstudio.com/_apis/hooks/subscriptions/subscription3",
            json={"status": "enabled"},
        )
        self.identity = Identity.objects.create(
            idp=self.create_identity_provider(type="vsts"),
            user=self.user,
            external_id="user_identity",
            data={"access_token": "vsts-access-token", "expires": time() + 50000},
        )

    @responses.activate
    def test_kickoff_subscription(self) -> None:
        integration3_check_time = time()
        integration1 = self.create_provider_integration(
            provider=PROVIDER,
            name="vsts1",
            external_id="vsts1",
            metadata={
                "domain_name": "https://vsts1.visualstudio.com/",
                "subscription": {"id": "subscription1"},
            },
        )
        integration2 = self.create_provider_integration(
            provider=PROVIDER, name="vsts2", external_id="vsts2", metadata={}
        )
        integration3 = self.create_provider_integration(
            provider=PROVIDER,
            name="vsts3",
            external_id="vsts3",
            metadata={
                "subscription": {
                    "id": "subscription3",
                    "check": integration3_check_time,
                    "secret": "1234567890",
                }
            },
        )

        integration1.add_organization(self.organization, default_auth_id=self.identity.id)
        integration2.add_organization(self.organization, default_auth_id=self.identity.id)
        integration3.add_organization(self.organization, default_auth_id=self.identity.id)

        with self.tasks():
            kickoff_vsts_subscription_check()

        assert_subscription("vsts1", "subscription1_new_id")
        assert_subscription("vsts3", "subscription3", check_time=integration3_check_time)

    @responses.activate
    def test_kickoff_subscription_no_default_identity(self) -> None:
        integration = self.create_provider_integration(
            provider=PROVIDER,
            name="vsts1",
            external_id="vsts1",
            metadata={
                "domain_name": "https://vsts1.visualstudio.com/",
                "subscription": {"id": "subscription1"},
            },
        )
        integration.add_organization(self.organization, default_auth_id=None)

        with self.tasks():
            kickoff_vsts_subscription_check()

        assert_no_subscription("vsts1", "subscription1")
