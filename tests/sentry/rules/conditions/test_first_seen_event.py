from sentry.models.rule import Rule
from sentry.rules.conditions.first_seen_event import FirstSeenEventCondition
from sentry.testutils.cases import RuleTestCase
from sentry.testutils.skips import requires_snuba

pytestmark = [requires_snuba]


class FirstSeenEventConditionTest(RuleTestCase):
    rule_cls = FirstSeenEventCondition

    def test_applies_correctly(self) -> None:
        rule = self.get_rule(rule=Rule(environment_id=None))

        self.assertPasses(rule, self.event, is_new=True)

        self.assertDoesNotPass(rule, self.event, is_new=False)

    def test_applies_correctly_with_environment(self) -> None:
        rule = self.get_rule(rule=Rule(environment_id=1))

        self.assertPasses(rule, self.event, is_new=True, is_new_group_environment=True)
        self.assertPasses(rule, self.event, is_new=False, is_new_group_environment=True)

        self.assertDoesNotPass(rule, self.event, is_new=True, is_new_group_environment=False)
        self.assertDoesNotPass(rule, self.event, is_new=False, is_new_group_environment=False)
