from sentry.integrations.models.external_actor import ExternalActor
from sentry.testutils.cases import APITestCase


class ExternalTeamDetailsTest(APITestCase):
    endpoint = "sentry-api-0-external-team-details"
    method = "put"

    def setUp(self) -> None:
        super().setUp()
        self.login_as(self.user)

        self.external_team = self.create_external_team(
            self.team, external_name="@getsentry/ecosystem"
        )

    def test_basic_delete(self) -> None:
        self.get_success_response(
            self.organization.slug, self.team.slug, self.external_team.id, method="delete"
        )
        assert not ExternalActor.objects.filter(id=str(self.external_team.id)).exists()

    def test_basic_update(self) -> None:
        with self.feature({"organizations:integrations-codeowners": True}):
            data = {"externalName": "@getsentry/growth"}
            response = self.get_success_response(
                self.organization.slug, self.team.slug, self.external_team.id, **data
            )

        assert response.data["id"] == str(self.external_team.id)
        assert response.data["externalName"] == "@getsentry/growth"

    def test_ignore_camelcase_teamid(self) -> None:
        other_team = self.create_team(organization=self.organization)
        data = {
            "externalName": "@getsentry/growth",
            "teamId": other_team.id,
        }
        with self.feature({"organizations:integrations-codeowners": True}):
            self.get_success_response(
                self.organization.slug, self.team.slug, self.external_team.id, **data
            )
        assert not ExternalActor.objects.filter(team_id=other_team.id).exists()

    def test_invalid_provider_update(self) -> None:
        data = {"provider": "git"}
        with self.feature({"organizations:integrations-codeowners": True}):
            response = self.get_error_response(
                self.organization.slug,
                self.team.slug,
                self.external_team.id,
                status_code=400,
                **data,
            )
        assert response.data == {"provider": ['"git" is not a valid choice.']}

    def test_delete_another_orgs_external_team(self) -> None:
        invalid_user = self.create_user()
        invalid_organization = self.create_organization(owner=invalid_user)
        self.login_as(user=invalid_user)
        resp = self.get_error_response(
            invalid_organization.slug, self.team.slug, self.external_team.id, method="delete"
        )
        assert resp.status_code == 404
