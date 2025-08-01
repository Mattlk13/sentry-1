import pytest

from sentry import eventstore
from sentry.event_manager import EventManager
from sentry.testutils.pytest.fixtures import django_db_all


@pytest.fixture
def make_breadcrumbs_snapshot(insta_snapshot):
    def inner(data):
        mgr = EventManager(data={"breadcrumbs": data})
        mgr.normalize()
        evt = eventstore.backend.create_event(project_id=1, data=mgr.get_data())
        breadcrumbs = evt.interfaces.get("breadcrumbs")

        insta_snapshot(
            {"errors": evt.data.get("errors"), "to_json": breadcrumbs and breadcrumbs.to_json()}
        )

    return inner


def test_simple(make_breadcrumbs_snapshot) -> None:
    make_breadcrumbs_snapshot(
        dict(
            values=[
                {
                    "type": "message",
                    "timestamp": 1458857193.973275,
                    "data": {"message": "Whats up dawg?"},
                }
            ]
        )
    )


@django_db_all
@pytest.mark.parametrize(
    "input",
    [
        {},
        {"values": []},
        # TODO(markus): The following cases should eventually generate {"values": [None]}
        {"values": [{}]},
        {"values": [{"type": None}]},
        {"values": [None]},
    ],
)
def test_null_values(make_breadcrumbs_snapshot, input) -> None:
    make_breadcrumbs_snapshot(input)


@django_db_all
def test_non_string_keys(make_breadcrumbs_snapshot) -> None:
    make_breadcrumbs_snapshot(
        dict(
            values=[
                {
                    "type": "message",
                    "timestamp": 1458857193.973275,
                    "data": {"extra": {"foo": "bar"}},
                }
            ]
        )
    )


def test_string_data(make_breadcrumbs_snapshot) -> None:
    make_breadcrumbs_snapshot(
        dict(
            values=[
                {"type": "message", "timestamp": 1458857193.973275, "data": "must be a mapping"}
            ]
        )
    )
