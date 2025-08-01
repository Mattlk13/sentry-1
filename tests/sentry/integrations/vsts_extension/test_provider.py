from unittest.mock import MagicMock, Mock, patch
from urllib.parse import parse_qs, urlparse

from django.urls import reverse

from fixtures.vsts import VstsIntegrationTestCase
from sentry.integrations.models.integration import Integration
from sentry.integrations.vsts import VstsIntegrationProvider
from sentry.integrations.vsts_extension import (
    VstsExtensionFinishedView,
    VstsExtensionIntegrationProvider,
)
from sentry.testutils.silo import control_silo_test
from tests.sentry.integrations.vsts.test_integration import FULL_SCOPES


@control_silo_test
class VstsExtensionIntegrationProviderTest(VstsIntegrationTestCase):
    provider = VstsExtensionIntegrationProvider()
    provider.pipeline = Mock()
    provider.pipeline.organization.id = 1

    @patch(
        "sentry.integrations.vsts.integration.VstsIntegrationProvider.get_scopes",
        return_value=FULL_SCOPES,
    )
    def test_get_pipeline_views(self, mock_get_scopes: MagicMock) -> None:
        # Should be same as the VSTS integration, but with a different last
        # step.
        views = self.provider.get_pipeline_views()
        vsts_views = VstsIntegrationProvider().get_pipeline_views()

        assert isinstance(views[0], type(vsts_views[0]))
        assert isinstance(views[-1], VstsExtensionFinishedView)

    @patch("sentry.integrations.vsts.integration.get_user_info")
    @patch("sentry.integrations.vsts.integration.VstsIntegrationProvider.create_subscription")
    @patch(
        "sentry.integrations.vsts.integration.VstsIntegrationProvider.get_scopes",
        return_value=FULL_SCOPES,
    )
    def test_build_integration(
        self, mock_get_scopes: MagicMock, create_sub: MagicMock, get_user_info: MagicMock
    ) -> None:
        get_user_info.return_value = {"id": "987"}
        create_sub.return_value = (1, "sharedsecret")

        integration = self.provider.build_integration(
            {
                "vsts": {"accountId": self.vsts_account_id, "accountName": "test"},
                "instance": "https://test.visualstudio.com/",
                "identity": {"data": {"access_token": "123", "expires_in": 3000}},
            }
        )

        assert integration["external_id"] == self.vsts_account_id
        assert integration["name"] == "test"

    def test_builds_integration_with_vsts_key(self) -> None:
        self._stub_vsts()

        # Emulate the request from VSTS to us
        resp = self.make_init_request(
            path=reverse("vsts-extension-configuration"),
            body={
                "targetId": self.vsts_account_id,
                "targetName": self.vsts_account_name,
                "targetUri": self.vsts_account_uri,
            },
        )

        self.assert_vsts_oauth_redirect(urlparse(resp["Location"]))

        # We redirect the user to OAuth with VSTS, so emulate the response from
        # VSTS to us.
        self.make_oauth_redirect_request(
            state=parse_qs(urlparse(resp["Location"]).query)["state"][0]
        )

        # Should have create the Integration using the ``vsts`` key
        assert Integration.objects.filter(provider="vsts").exists()
