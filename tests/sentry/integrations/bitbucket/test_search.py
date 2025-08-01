from unittest.mock import MagicMock, patch

import responses
from django.urls import reverse

from sentry.integrations.source_code_management.metrics import SourceCodeSearchEndpointHaltReason
from sentry.integrations.types import EventLifecycleOutcome
from sentry.testutils.asserts import assert_halt_metric, assert_middleware_metrics
from sentry.testutils.cases import APITestCase
from sentry.testutils.silo import control_silo_test


@control_silo_test
class BitbucketSearchEndpointTest(APITestCase):
    def setUp(self) -> None:
        self.base_url = "https://api.bitbucket.org"
        self.shared_secret = "234567890"
        self.subject = "connect:1234567"
        self.integration, _ = self.create_provider_integration_for(
            self.organization,
            self.user,
            provider="bitbucket",
            external_id=self.subject,
            name="meredithanya",
            metadata={
                "base_url": self.base_url,
                "shared_secret": self.shared_secret,
                "subject": self.subject,
            },
        )

        self.login_as(self.user)
        self.path = reverse(
            "sentry-extensions-bitbucket-search", args=[self.organization.slug, self.integration.id]
        )

    @responses.activate
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_search_issues(self, mock_record: MagicMock) -> None:
        responses.add(
            responses.GET,
            "https://api.bitbucket.org/2.0/repositories/meredithanya/apples/issues",
            json={
                "values": [
                    {"id": "123", "title": "Issue Title 123"},
                    {"id": "456", "title": "Issue Title 456"},
                ]
            },
        )
        resp = self.client.get(
            self.path,
            data={"field": "externalIssue", "query": "issue", "repo": "meredithanya/apples"},
        )

        assert resp.status_code == 200
        assert resp.data == [
            {"label": "#123 Issue Title 123", "value": "123"},
            {"label": "#456 Issue Title 456", "value": "456"},
        ]

        assert len(mock_record.mock_calls) == 8

        # first 2 are middleware calls to ensure control silo, then the next one and the last one are also middleware calls for get_response_from_control_silo
        middleware_calls = mock_record.mock_calls[:3] + mock_record.mock_calls[-1:]
        assert_middleware_metrics(middleware_calls)

        product_calls = mock_record.mock_calls[3:-1]
        start1, start2, halt1, halt2 = product_calls
        assert start1.args[0] == EventLifecycleOutcome.STARTED
        assert start2.args[0] == EventLifecycleOutcome.STARTED
        assert halt1.args[0] == EventLifecycleOutcome.SUCCESS
        assert halt2.args[0] == EventLifecycleOutcome.SUCCESS

    @responses.activate
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_search_repositories(self, mock_record: MagicMock) -> None:
        responses.add(
            responses.GET,
            "https://api.bitbucket.org/2.0/repositories/meredithanya",
            json={"values": [{"full_name": "meredithanya/apples"}]},
        )
        resp = self.client.get(self.path, data={"field": "repo", "query": "apple"})

        assert resp.status_code == 200
        assert resp.data == [{"label": "meredithanya/apples", "value": "meredithanya/apples"}]

        middleware_calls = mock_record.mock_calls[:3] + mock_record.mock_calls[-1:]
        assert_middleware_metrics(middleware_calls)

        product_calls = mock_record.mock_calls[3:-1]
        start1, start2, halt1, halt2 = (
            product_calls  # calls get, which calls handle_search_repositories
        )
        assert start1.args[0] == EventLifecycleOutcome.STARTED
        assert start2.args[0] == EventLifecycleOutcome.STARTED
        assert halt1.args[0] == EventLifecycleOutcome.SUCCESS
        assert halt2.args[0] == EventLifecycleOutcome.SUCCESS

    @responses.activate
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_search_repositories_no_issue_tracker(self, mock_record: MagicMock) -> None:
        responses.add(
            responses.GET,
            "https://api.bitbucket.org/2.0/repositories/meredithanya/apples/issues",
            json={"type": "error", "error": {"message": "Repository has no issue tracker."}},
            status=404,
        )
        resp = self.client.get(
            self.path,
            data={"field": "externalIssue", "query": "issue", "repo": "meredithanya/apples"},
        )
        assert resp.status_code == 400
        assert resp.data == {"detail": "Bitbucket Repository has no issue tracker."}

        middleware_calls = mock_record.mock_calls[:3] + mock_record.mock_calls[-1:]
        assert_middleware_metrics(middleware_calls)

        product_calls = mock_record.mock_calls[3:-1]

        start1, start2, halt1, halt2 = product_calls  # calls get, which calls handle_search_issues
        assert start1.args[0] == EventLifecycleOutcome.STARTED
        assert start2.args[0] == EventLifecycleOutcome.STARTED
        assert halt1.args[0] == EventLifecycleOutcome.HALTED
        assert_halt_metric(mock_record, SourceCodeSearchEndpointHaltReason.NO_ISSUE_TRACKER.value)
        # NOTE: handle_search_issues returns without raising an API error, so for the
        # purposes of logging the GET request completes successfully
        assert halt2.args[0] == EventLifecycleOutcome.SUCCESS
