from unittest import mock

import orjson

from sentry.models.activity import Activity
from sentry.notifications.notifications.activity.regression import RegressionActivityNotification
from sentry.testutils.cases import PerformanceIssueTestCase, SlackActivityNotificationTest
from sentry.testutils.helpers.notifications import TEST_ISSUE_OCCURRENCE, TEST_PERF_ISSUE_OCCURRENCE
from sentry.testutils.skips import requires_snuba
from sentry.types.activity import ActivityType

pytestmark = [requires_snuba]


class SlackRegressionNotificationTest(SlackActivityNotificationTest, PerformanceIssueTestCase):
    def create_notification(self, group, data=None):
        return RegressionActivityNotification(
            Activity(
                project=self.project,
                group=group,
                user_id=self.user.id,
                type=ActivityType.SET_REGRESSION,
                data=data or {},
            )
        )

    def test_regression_block(self) -> None:
        """
        Test that a Slack message is sent with the expected payload when an issue regresses
        and block kit is enabled.
        """
        with self.tasks():
            self.create_notification(self.group).send()

        blocks = orjson.loads(self.mock_post.call_args.kwargs["blocks"])
        fallback_text = self.mock_post.call_args.kwargs["text"]
        assert fallback_text == "Issue marked as regression"
        assert blocks[0]["text"]["text"] == fallback_text
        notification_uuid = self.get_notification_uuid(
            blocks[1]["elements"][0]["elements"][-1]["url"]
        )
        emoji = "red_circle"
        url = f"http://testserver/organizations/{self.organization.slug}/issues/{self.group.id}/?referrer=regression_activity-slack&notification_uuid={notification_uuid}"
        text = f"{self.group.title}"
        assert blocks[1]["elements"][0]["elements"][0]["name"] == emoji
        assert blocks[1]["elements"][0]["elements"][-1]["url"] == url
        assert blocks[1]["elements"][0]["elements"][-1]["text"] == text

        assert blocks[3]["elements"][0]["text"] == (
            f"{self.project.slug} | <http://testserver/settings/account/notifications/workflow/?referrer=regression_activity-slack-user&notification_uuid={notification_uuid}&organizationId={self.organization.id}|Notification Settings>"
        )

    def test_regression_with_release_block(self) -> None:
        """
        Test that a Slack message is sent with the expected payload when an issue regresses
        and block kit is enabled.
        """
        with self.tasks():
            self.create_notification(self.group, {"version": "1.0.0"}).send()

        blocks = orjson.loads(self.mock_post.call_args.kwargs["blocks"])
        fallback_text = self.mock_post.call_args.kwargs["text"]
        notification_uuid = self.get_notification_uuid(
            blocks[1]["elements"][0]["elements"][-1]["url"]
        )
        assert (
            fallback_text
            == f"Issue marked as regression in release <http://testserver/organizations/baz/releases/1.0.0/?referrer=regression_activity&notification_uuid={notification_uuid}|1.0.0>"
        )
        assert blocks[0]["text"]["text"] == fallback_text
        emoji = "red_circle"
        url = f"http://testserver/organizations/{self.organization.slug}/issues/{self.group.id}/?referrer=regression_activity-slack&notification_uuid={notification_uuid}"
        text = f"{self.group.title}"
        assert blocks[1]["elements"][0]["elements"][0]["name"] == emoji
        assert blocks[1]["elements"][0]["elements"][-1]["url"] == url
        assert blocks[1]["elements"][0]["elements"][-1]["text"] == text
        assert blocks[3]["elements"][0]["text"] == (
            f"{self.project.slug} | <http://testserver/settings/account/notifications/workflow/?referrer=regression_activity-slack-user&notification_uuid={notification_uuid}&organizationId={self.organization.id}|Notification Settings>"
        )

    @mock.patch(
        "sentry.eventstore.models.GroupEvent.occurrence",
        return_value=TEST_PERF_ISSUE_OCCURRENCE,
        new_callable=mock.PropertyMock,
    )
    def test_regression_performance_issue_block_with_culprit_blocks(
        self, occurrence: mock.MagicMock
    ) -> None:
        """
        Test that a Slack message is sent with the expected payload when a performance issue regresses
        and block kit is enabled.
        """
        event = self.create_performance_issue()
        with self.tasks():
            self.create_notification(event.group).send()

        blocks = orjson.loads(self.mock_post.call_args.kwargs["blocks"])
        fallback_text = self.mock_post.call_args.kwargs["text"]
        assert fallback_text == "Issue marked as regression"
        assert blocks[0]["text"]["text"] == fallback_text
        self.assert_performance_issue_blocks_with_culprit_blocks(
            blocks,
            event.organization,
            event.project.slug,
            event.group,
            "regression_activity-slack",
        )

    @mock.patch(
        "sentry.eventstore.models.GroupEvent.occurrence",
        return_value=TEST_ISSUE_OCCURRENCE,
        new_callable=mock.PropertyMock,
    )
    def test_regression_generic_issue_block_with_culprit_blocks(
        self, occurrence: mock.MagicMock
    ) -> None:
        """
        Test that a Slack message is sent with the expected payload when a generic issue type regresses
        and block kit is enabled.
        """
        event = self.store_event(
            data={
                "message": "Hellboy's world",
                "level": "error",
                "culprit": "raven.tasks.run_a_test",
            },
            project_id=self.project.id,
        )
        group_event = event.for_group(event.groups[0])

        with self.tasks():
            self.create_notification(group_event.group).send()

        blocks = orjson.loads(self.mock_post.call_args.kwargs["blocks"])
        fallback_text = self.mock_post.call_args.kwargs["text"]
        assert fallback_text == "Issue marked as regression"
        assert blocks[0]["text"]["text"] == fallback_text
        self.assert_generic_issue_blocks(
            blocks,
            group_event.organization,
            group_event.project.slug,
            group_event.group,
            "regression_activity-slack",
            with_culprit=True,
        )
