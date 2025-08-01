import pytest

from sentry import eventstore
from sentry.event_manager import EventManager
from sentry.testutils.pytest.fixtures import django_db_all


@pytest.fixture
def make_single_exception_snapshot(insta_snapshot):
    def inner(data):
        mgr = EventManager(data={"exception": {"values": [data]}})
        mgr.normalize()
        evt = eventstore.backend.create_event(project_id=1, data=mgr.get_data())

        excs = evt.interfaces["exception"].values
        if excs:
            to_json = excs[0].to_json()
        else:
            to_json = None

        insta_snapshot({"to_json": to_json, "errors": evt.data.get("errors")})

    return inner


@django_db_all
def test_basic(make_single_exception_snapshot) -> None:
    make_single_exception_snapshot(dict(type="ValueError", value="hello world", module="foo.bar"))


def test_requires_only_type_or_value(make_single_exception_snapshot) -> None:
    make_single_exception_snapshot(dict(type="ValueError"))


def test_requires_only_type_or_value2(make_single_exception_snapshot) -> None:
    make_single_exception_snapshot(dict(value="ValueError"))


def test_coerces_object_value_to_string(make_single_exception_snapshot) -> None:
    make_single_exception_snapshot({"type": "ValueError", "value": {"unauthorized": True}})


@django_db_all
def test_handles_type_in_value(make_single_exception_snapshot) -> None:
    make_single_exception_snapshot(dict(value="ValueError: unauthorized"))


def test_handles_type_in_value2(make_single_exception_snapshot) -> None:
    make_single_exception_snapshot(dict(value="ValueError:unauthorized"))


def test_value_serialization_idempotent(make_single_exception_snapshot) -> None:
    make_single_exception_snapshot({"type": None, "value": {"unauthorized": True}})


def test_value_serialization_idempotent2(make_single_exception_snapshot) -> None:
    # Don't re-split a json-serialized value on the colon
    make_single_exception_snapshot({"type": None, "value": '{"unauthorized":true}'})
