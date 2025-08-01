import logging
from datetime import datetime

import pytest
from django.conf import settings

from sentry.constants import DEFAULT_LOGGER_NAME, MAX_CULPRIT_LENGTH
from sentry.event_manager import EventManager


def make_event(**kwargs):
    result = {
        "event_id": "a" * 32,
        "message": "foo",
        "timestamp": int(datetime.now().strftime("%s")),
        "level": logging.ERROR,
        "logger": "default",
        "tags": [],
    }
    result.update(kwargs)
    return result


def test_tags_as_list() -> None:
    manager = EventManager(make_event(tags=[("foo", "bar")]))
    manager.normalize()
    data = manager.get_data()

    assert data["tags"] == [["foo", "bar"]]


def test_tags_as_dict() -> None:
    manager = EventManager(make_event(tags={"foo": "bar"}))
    manager.normalize()
    data = manager.get_data()

    assert data["tags"] == [["foo", "bar"]]


def test_interface_is_relabeled() -> None:
    manager = EventManager(make_event(**{"sentry.interfaces.User": {"id": "1"}}))
    manager.normalize()
    data = manager.get_data()

    assert data["user"] == {"id": "1", "sentry_user": "id:1"}


@pytest.mark.parametrize("user", ["missing", None, {}, {"ip_address": None}])
def test_does_default_ip_address_to_user(user) -> None:
    event = {
        "request": {"url": "http://example.com", "env": {"REMOTE_ADDR": "127.0.0.1"}},
        "platform": "javascript",
    }
    if user != "missing":
        event["user"] = user

    manager = EventManager(make_event(**event))
    manager.normalize()
    data = manager.get_data()

    assert data["user"]["ip_address"] == "127.0.0.1"


def test_does_default_ip_address_if_present() -> None:
    manager = EventManager(
        make_event(
            **{
                "request": {"url": "http://example.com", "env": {"REMOTE_ADDR": "127.0.0.1"}},
                "user": {"ip_address": "192.168.0.1"},
            }
        )
    )
    manager.normalize()
    data = manager.get_data()
    assert data["user"]["ip_address"] == "192.168.0.1"


def test_long_culprit() -> None:
    manager = EventManager(make_event(culprit="x" * (MAX_CULPRIT_LENGTH + 1)))
    manager.normalize()
    data = manager.get_data()
    assert len(data["culprit"]) == MAX_CULPRIT_LENGTH


def test_long_transaction() -> None:
    manager = EventManager(make_event(transaction="x" * (MAX_CULPRIT_LENGTH + 1)))
    manager.normalize()
    data = manager.get_data()
    assert len(data["transaction"]) == MAX_CULPRIT_LENGTH


def test_long_message() -> None:
    allowance = 200
    manager = EventManager(
        make_event(message="x" * (settings.SENTRY_MAX_MESSAGE_LENGTH + 1 + allowance))
    )
    manager.normalize()
    data = manager.get_data()
    assert len(data["logentry"]["formatted"]) == settings.SENTRY_MAX_MESSAGE_LENGTH


def test_empty_message() -> None:
    manager = EventManager(make_event(message=""))
    manager.normalize()
    data = manager.get_data()
    assert "logentry" not in data


def test_default_version() -> None:
    manager = EventManager(make_event())
    manager.normalize()
    data = manager.get_data()
    assert data["version"] == "5"


def test_explicit_version() -> None:
    manager = EventManager(make_event(), "6")
    manager.normalize()
    data = manager.get_data()
    assert data["version"] == "6"


def test_logger() -> None:
    manager = EventManager(make_event(logger="foo\nbar"))
    manager.normalize()
    data = manager.get_data()
    assert data["logger"] == DEFAULT_LOGGER_NAME

    manager = EventManager(make_event(logger=""))
    manager.normalize()
    data = manager.get_data()
    assert data["logger"] == DEFAULT_LOGGER_NAME


def test_moves_stacktrace_to_exception() -> None:
    manager = EventManager(
        make_event(
            exception={"type": "MyException"},
            stacktrace={
                "frames": [{"lineno": 1, "filename": "foo.py"}, {"lineno": 1, "filename": "bar.py"}]
            },
        )
    )
    manager.normalize()
    data = manager.get_data()

    frames = data["exception"]["values"][0]["stacktrace"]["frames"]
    assert frames[0]["lineno"] == 1
    assert frames[0]["filename"] == "foo.py"
    assert frames[1]["lineno"] == 1
    assert frames[1]["filename"] == "bar.py"
    assert "stacktrace" not in data


def test_bad_interfaces_no_exception() -> None:
    manager = EventManager(
        make_event(**{"user": None, "request": None, "sdk": "A string for sdk is not valid"}),
        client_ip="1.2.3.4",
    )
    manager.normalize()

    manager = EventManager(make_event(**{"errors": {}, "request": {}}))
    manager.normalize()


def test_event_pii() -> None:
    manager = EventManager(
        make_event(user={"id": None}, _meta={"user": {"id": {"": {"err": ["invalid"]}}}})
    )
    manager.normalize()
    data = manager.get_data()
    assert data["_meta"]["user"]["id"] == {"": {"err": ["invalid"]}}


def test_event_id_lowercase() -> None:
    manager = EventManager(make_event(event_id="1234ABCD" * 4))
    manager.normalize()
    data = manager.get_data()

    assert data["event_id"] == "1234abcd" * 4

    manager = EventManager(make_event(event_id="1234ABCD" * 4))
    manager.normalize()
    data = manager.get_data()

    assert data["event_id"] == "1234abcd" * 4


@pytest.mark.parametrize("key", ["applecrashreport", "device", "repos", "query"])
def test_deprecated_attrs(key) -> None:
    event = make_event()
    event[key] = "some value"

    manager = EventManager(event)
    manager.normalize()
    data = manager.get_data()

    assert key not in data
    assert not data.get("errors")


@pytest.mark.parametrize("environment", ["", None, "production"])
def test_environment_tag_removed(environment) -> None:
    event = make_event()
    event["environment"] = environment
    event["tags"] = {"environment": "production"}

    manager = EventManager(event)
    manager.normalize()
    data = manager.get_data()
    assert "environment" not in dict(data.get("tags") or ())
    assert data["environment"] == "production"
