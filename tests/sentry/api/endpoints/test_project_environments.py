from django.urls import reverse

from sentry.models.environment import Environment, EnvironmentProject
from sentry.testutils.cases import APITestCase


class ProjectEnvironmentsTest(APITestCase):
    def test_simple(self) -> None:
        project = self.create_project()

        env1 = Environment.objects.create(
            organization_id=project.organization_id, name="production"
        )
        env1.add_project(project)

        env2 = Environment.objects.create(organization_id=project.organization_id, name="staging")
        env2.add_project(project)

        self.login_as(user=self.user)

        url = reverse(
            "sentry-api-0-project-environments",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
            },
        )
        response = self.client.get(url, format="json")
        assert response.status_code == 200, response.content
        assert len(response.data) == 2
        assert response.data[0]["name"] == "production"
        assert response.data[1]["name"] == "staging"

    def test_visibility_filtering(self) -> None:
        project = self.create_project()

        env1 = Environment.objects.create(
            organization_id=project.organization_id, name="production"
        )

        EnvironmentProject.objects.create(project=project, environment=env1, is_hidden=False)

        env2 = Environment.objects.create(organization_id=project.organization_id, name="staging")

        EnvironmentProject.objects.create(project=project, environment=env2, is_hidden=True)

        self.login_as(user=self.user)

        url = reverse(
            "sentry-api-0-project-environments",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
            },
        )
        response = self.client.get(url, format="json")
        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert response.data[0]["name"] == "production"

        response = self.client.get(url + "?visibility=all", format="json")
        assert response.status_code == 200, response.content
        assert len(response.data) == 2
        assert response.data[0]["name"] == "production"
        assert response.data[1]["name"] == "staging"

        response = self.client.get(url + "?visibility=hidden", format="json")
        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert response.data[0]["name"] == "staging"
