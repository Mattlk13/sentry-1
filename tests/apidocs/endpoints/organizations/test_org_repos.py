from django.test.client import RequestFactory
from django.urls import reverse

from fixtures.apidocs_test_case import APIDocsTestCase


class OrganizationReposDocs(APIDocsTestCase):
    def setUp(self):
        organization = self.create_organization(owner=self.user, name="Rowdy Tiger")
        project = self.create_project(name="foo", organization=organization, teams=[])
        self.create_repo(project=project, name="getsentry/sentry")

        self.url = reverse(
            "sentry-api-0-organization-repositories",
            kwargs={"organization_id_or_slug": organization.slug},
        )

        self.login_as(user=self.user)

    def test_get(self) -> None:
        response = self.client.get(self.url)
        request = RequestFactory().get(self.url)

        self.validate_schema(request, response)
