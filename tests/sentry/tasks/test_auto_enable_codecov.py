from unittest.mock import MagicMock, patch

import responses

from sentry import audit_log
from sentry.models.auditlogentry import AuditLogEntry
from sentry.models.organization import Organization
from sentry.tasks.auto_enable_codecov import enable_for_org
from sentry.testutils.cases import TestCase
from sentry.testutils.helpers import with_feature
from sentry.testutils.outbox import outbox_runner
from sentry.testutils.silo import assume_test_silo_mode_of


@with_feature("organizations:auto-enable-codecov")
class AutoEnableCodecovTest(TestCase):
    def setUp(self) -> None:
        self.organization = self.create_organization()
        self.integration = self.create_integration(
            organization=self.organization,
            provider="github",
            external_id="id",
        )

        responses.add(
            responses.GET,
            "https://api.codecov.io/api/v2/github/testgit",
            status=200,
        )

        responses.add(
            responses.GET,
            "https://api.codecov.io/api/v2/github/fakegit",
            status=404,
        )

    @responses.activate
    @patch(
        "sentry.integrations.github.client.GitHubApiClient.get_repos",
        return_value=[{"name": "abc", "full_name": "testgit/abc"}],
    )
    @with_feature("organizations:codecov-integration")
    def test_has_codecov_integration(self, mock_get_repositories: MagicMock) -> None:
        with assume_test_silo_mode_of(AuditLogEntry):
            AuditLogEntry.objects.all().delete()
        assert not self.organization.flags.codecov_access.is_set
        with outbox_runner():
            enable_for_org(self.organization.id)

        assert mock_get_repositories.call_count == 1

        org = Organization.objects.get(id=self.organization.id)
        assert org.flags.codecov_access

        with assume_test_silo_mode_of(AuditLogEntry):
            audit = AuditLogEntry.objects.filter(
                organization_id=org.id, event=audit_log.get_event_id("ORG_EDIT")
            )
            assert audit.exists()

    @responses.activate
    @patch(
        "sentry.integrations.github.client.GitHubApiClient.get_repos",
        return_value={"repositories": [{"full_name": "fakegit/abc"}]},
    )
    @with_feature("organizations:codecov-integration")
    def test_no_codecov_integration(self, mock_get_repositories: MagicMock) -> None:
        assert not self.organization.flags.codecov_access.is_set
        with outbox_runner():
            enable_for_org(self.organization.id)

        assert mock_get_repositories.call_count == 1

        org = Organization.objects.get(id=self.organization.id)
        assert not org.flags.codecov_access

    @responses.activate
    def test_disables_codecov(self) -> None:
        with assume_test_silo_mode_of(AuditLogEntry):
            AuditLogEntry.objects.all().delete()
        self.organization.flags.codecov_access = True
        self.organization.save()

        with outbox_runner():
            enable_for_org(self.organization.id)

        org = Organization.objects.get(id=self.organization.id)
        assert not org.flags.codecov_access
        with assume_test_silo_mode_of(AuditLogEntry):
            audit_log = AuditLogEntry.objects.get(organization_id=org.id)
            assert audit_log.data == {"codecov_access": "to False"}
