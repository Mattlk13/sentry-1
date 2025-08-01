from sentry.newsletter.base import Newsletter
from sentry.testutils.cases import TestCase
from sentry.testutils.silo import control_silo_test

newsletter = Newsletter()


@control_silo_test
class BaseNewsletterTest(TestCase):
    def test_defaults(self) -> None:
        assert newsletter.DEFAULT_LISTS == newsletter.get_default_list_ids()
        assert newsletter.DEFAULT_LIST_ID == newsletter.get_default_list_id()

    def test_update_subscription(self) -> None:
        user = self.create_user("subscriber@example.com")
        newsletter.update_subscription(user)

        assert newsletter.get_subscriptions(user) is None
        assert newsletter.create_or_update_subscription(user) is None
        assert newsletter.create_or_update_subscriptions(user) is None

    def test_update_subscriptions(self) -> None:
        user = self.create_user("subscriber@example.com")
        newsletter.update_subscriptions(user)

        assert newsletter.get_subscriptions(user) is None
        assert newsletter.create_or_update_subscription(user) is None
        assert newsletter.create_or_update_subscriptions(user) is None
