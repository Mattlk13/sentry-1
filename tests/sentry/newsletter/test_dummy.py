from sentry.newsletter.dummy import DummyNewsletter
from sentry.testutils.cases import TestCase
from sentry.testutils.silo import control_silo_test


@control_silo_test
class DummyNewsletterTest(TestCase):
    def setUp(self) -> None:
        self.newsletter = DummyNewsletter()

    def test_defaults(self) -> None:
        assert self.newsletter.DEFAULT_LISTS == self.newsletter.get_default_list_ids()
        assert self.newsletter.DEFAULT_LIST_ID == self.newsletter.get_default_list_id()

    def assert_subscriptions(self, user, count):
        subscriptions = self.newsletter.get_subscriptions(user)
        assert subscriptions.get("subscriptions") is not None
        subscribed = [sub for sub in subscriptions["subscriptions"] if sub.subscribed]
        assert len(subscribed) == count

    def test_update_subscription(self) -> None:
        user = self.create_user("subscriber@example.com")

        self.assert_subscriptions(user, 0)
        self.newsletter.create_or_update_subscription(user)
        self.assert_subscriptions(user, 1)

    def test_update_subscriptions(self) -> None:
        user = self.create_user("subscriber@example.com")

        self.assert_subscriptions(user, 0)
        self.newsletter.create_or_update_subscriptions(user)
        self.assert_subscriptions(user, 1)

    def test_optout_email(self) -> None:
        user = self.create_user("subscriber@example.com")

        self.newsletter.create_or_update_subscriptions(user)
        self.assert_subscriptions(user, 1)

        self.newsletter.optout_email("subscriber@example.com")
        self.assert_subscriptions(user, 0)
