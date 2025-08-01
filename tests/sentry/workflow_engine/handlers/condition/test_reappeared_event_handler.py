from dataclasses import replace

import pytest
from jsonschema import ValidationError

from sentry.rules.conditions.reappeared_event import ReappearedEventCondition
from sentry.workflow_engine.models.data_condition import Condition
from sentry.workflow_engine.types import WorkflowEventData
from tests.sentry.workflow_engine.handlers.condition.test_base import ConditionTestCase


class TestReappearedEventCondition(ConditionTestCase):
    condition = Condition.REAPPEARED_EVENT
    payload = {"id": ReappearedEventCondition.id}

    def test_dual_write(self) -> None:
        dcg = self.create_data_condition_group()
        dc = self.translate_to_data_condition(self.payload, dcg)

        assert dc.type == self.condition
        assert dc.comparison is True
        assert dc.condition_result is True
        assert dc.condition_group == dcg

    def test_json_schema(self) -> None:
        dc = self.create_data_condition(
            type=self.condition,
            comparison=True,
            condition_result=True,
        )

        dc.comparison = False
        dc.save()

        dc.comparison = {"time": "asdf"}
        with pytest.raises(ValidationError):
            dc.save()

        dc.comparison = "hello"
        with pytest.raises(ValidationError):
            dc.save()

    def test(self) -> None:
        job = WorkflowEventData(
            event=self.group_event,
            group=self.group_event.group,
            has_reappeared=False,
            has_escalated=True,
        )
        dc = self.create_data_condition(
            type=self.condition,
            comparison=True,
            condition_result=True,
        )

        self.assert_passes(dc, job)

        job = replace(job, has_escalated=False)
        self.assert_does_not_pass(dc, job)
