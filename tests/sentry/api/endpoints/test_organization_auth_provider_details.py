from django.urls import reverse

from sentry.testutils.cases import APITestCase, PermissionTestCase, SCIMTestCase


class OrganizationAuthProviderPermissionTest(PermissionTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.path = reverse(
            "sentry-api-0-organization-auth-provider", args=[self.organization.slug]
        )

    def test_member_can_get(self) -> None:
        with self.feature("organizations:sso-basic"):
            self.assert_member_can_access(self.path)


class OrganizationAuthProviderTest(SCIMTestCase, APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.login_as(self.user)
        self.path = reverse(
            "sentry-api-0-organization-auth-provider", args=[self.organization.slug]
        )

    def test_no_auth_provider(self) -> None:
        with self.feature("organizations:sso-basic"):
            user = self.create_user()
            organization = self.create_organization(owner=user)
            self.login_as(user)

            response = self.client.get(
                reverse("sentry-api-0-organization-auth-provider", args=[organization.slug])
            )
            assert response.status_code == 204
            assert response.data is None

    def test_with_auth_provider(self) -> None:
        with self.feature("organizations:sso-basic"):
            response = self.client.get(self.path)
            assert response.status_code == 200
            assert response.data == {
                "id": str(self.auth_provider_inst.id),
                "provider_name": "dummy",
                "pending_links_count": 1,
                "login_url": f"http://testserver/organizations/{self.organization.slug}/issues/",
                "default_role": "member",
                "require_link": True,
                "scim_enabled": True,
            }

    def test_with_auth_provider_and_customer_domain(self) -> None:
        with self.feature(["organizations:sso-basic", "system:multi-region"]):
            response = self.client.get(self.path)
            assert response.status_code == 200
            assert response.data == {
                "id": str(self.auth_provider_inst.id),
                "provider_name": "dummy",
                "pending_links_count": 1,
                "login_url": f"http://{self.organization.slug}.testserver/issues/",
                "default_role": "member",
                "require_link": True,
                "scim_enabled": True,
            }
