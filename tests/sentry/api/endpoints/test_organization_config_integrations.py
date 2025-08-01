from sentry.testutils.cases import APITestCase


class OrganizationConfigIntegrationsTest(APITestCase):
    endpoint = "sentry-api-0-organization-config-integrations"

    def setUp(self) -> None:
        super().setUp()
        self.login_as(self.user)

    def test_simple(self) -> None:
        response = self.get_success_response(self.organization.slug)
        assert len(response.data["providers"]) > 0
        providers = [r for r in response.data["providers"] if r["key"] == "example"]
        assert len(providers) == 1
        provider = providers[0]
        assert provider["name"] == "Example"
        assert provider["setupDialog"]["url"]

    def test_provider_key(self) -> None:
        response = self.get_success_response(
            self.organization.slug, qs_params={"provider_key": "example_server"}
        )
        assert len(response.data["providers"]) == 1
        assert response.data["providers"][0]["name"] == "Example Server"

        response = self.get_success_response(
            self.organization.slug, qs_params={"providerKey": "example_server"}
        )
        assert len(response.data["providers"]) == 1
        assert response.data["providers"][0]["name"] == "Example Server"

    def test_feature_flag_integration(self) -> None:
        response = self.get_success_response(self.organization.slug)
        provider = [r for r in response.data["providers"] if r["key"] == "feature_flag_integration"]
        assert len(provider) == 0

        with self.feature("organizations:integrations-feature-flag-integration"):
            response = self.get_success_response(self.organization.slug)
            provider = [
                r for r in response.data["providers"] if r["key"] == "feature_flag_integration"
            ]
            assert len(provider) == 1
