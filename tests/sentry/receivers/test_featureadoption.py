from django.utils import timezone

from sentry.models.featureadoption import FeatureAdoption
from sentry.models.groupassignee import GroupAssignee
from sentry.models.grouptombstone import GroupTombstone
from sentry.models.rule import Rule
from sentry.plugins.bases.issue2 import IssueTrackingPlugin2
from sentry.plugins.bases.notify import NotificationPlugin
from sentry.receivers.rules import DEFAULT_RULE_DATA
from sentry.signals import (
    advanced_search,
    alert_rule_created,
    data_scrubber_enabled,
    event_processed,
    first_event_received,
    inbound_filter_toggled,
    issue_assigned,
    issue_resolved,
    member_joined,
    plugin_enabled,
    project_created,
    save_search_created,
    sso_enabled,
    user_feedback_received,
)
from sentry.testutils.cases import SnubaTestCase, TestCase


class FeatureAdoptionTest(TestCase, SnubaTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.now = timezone.now()
        self.owner = self.create_user()
        self.organization = self.create_organization(owner=self.owner)
        self.team = self.create_team(organization=self.organization)
        self.project = self.create_project(teams=[self.team])

    def test_bad_feature_slug(self) -> None:
        FeatureAdoption.objects.record(self.organization.id, "xxx")
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="first_event"
        )
        assert feature_complete is None

    def test_all_passed_feature_slugs_are_complete(self) -> None:
        event1 = self.store_event(
            data={"tags": {"environment": "prod"}}, project_id=self.project.id
        )
        event2 = self.store_event(
            data={"tags": {"environment": "prod"}}, project_id=self.project.id
        )

        event_processed.send(project=self.project, event=event1, sender=type(self.project))
        event_processed.send(project=self.project, event=event2, sender=type(self.project))

        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="environment_tracking"
        )
        assert feature_complete.complete

    def test_first_event(self) -> None:
        event = self.store_event(
            data={"platform": "javascript", "message": "javascript error message"},
            project_id=self.project.id,
        )
        first_event_received.send(project=self.project, event=event, sender=type(self.project))

        first_event = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="first_event"
        )
        assert first_event.complete

    def test_javascript(self) -> None:
        event = self.store_event(data={"platform": "javascript"}, project_id=self.project.id)
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        js = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="javascript")
        assert js.complete

    def test_python(self) -> None:
        event = self.store_event(
            data={"platform": "python", "message": "python error message"},
            project_id=self.project.id,
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        python = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="python")
        assert python.complete

    def test_node(self) -> None:
        event = self.store_event(
            data={"platform": "node", "message": "node error message"}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        node = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="node")
        assert node.complete

    def test_ruby(self) -> None:
        event = self.store_event(
            data={"platform": "ruby", "message": "ruby error message"}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        ruby = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="ruby")
        assert ruby.complete

    def test_java(self) -> None:
        event = self.store_event(
            data={"platform": "java", "message": "java error message"}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        java = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="java")
        assert java.complete

    def test_cocoa(self) -> None:
        event = self.store_event(
            data={"platform": "cocoa", "message": "cocoa error message"}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        cocoa = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="cocoa")
        assert cocoa.complete

    def test_objc(self) -> None:
        event = self.store_event(
            data={"platform": "objc", "message": "objc error message"}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        objc = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="objc")
        assert objc.complete

    def test_php(self) -> None:
        event = self.store_event(
            data={"platform": "php", "message": "php error message"}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        php = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="php")
        assert php.complete

    def test_go(self) -> None:
        event = self.store_event(
            data={"platform": "go", "message": "go error message"}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        go = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="go")
        assert go.complete

    def test_csharp(self) -> None:
        event = self.store_event(
            data={"platform": "csharp", "message": "csharp error message"},
            project_id=self.project.id,
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        csharp = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="csharp")
        assert csharp.complete

    def test_perl(self) -> None:
        event = self.store_event(
            data={"platform": "perl", "message": "perl error message"}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        perl = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="perl")
        assert perl.complete

    def test_elixir(self) -> None:
        event = self.store_event(
            data={"platform": "elixir", "message": "elixir error message"},
            project_id=self.project.id,
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        elixir = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="elixir")
        assert elixir.complete

    def test_cfml(self) -> None:
        event = self.store_event(
            data={"platform": "cfml", "message": "cfml error message"}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        cfml = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="cfml")
        assert cfml.complete

    def test_groovy(self) -> None:
        event = self.store_event(
            data={"platform": "groovy", "message": "groovy error message"},
            project_id=self.project.id,
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        groovy = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="groovy")
        assert groovy.complete

    def test_release_tracking(self) -> None:
        event = self.store_event(data={"tags": {"sentry:release": "1"}}, project_id=self.project.id)
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        release_tracking = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="release_tracking"
        )
        assert release_tracking

    def test_environment_tracking(self) -> None:
        event = self.store_event(data={"environment": "prod"}, project_id=self.project.id)
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        environment_tracking = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="environment_tracking"
        )
        assert environment_tracking

    def test_bulk_create(self) -> None:
        event = self.store_event(
            data={
                "platform": "javascript",
                "environment": "prod",
                "tags": {"sentry:release": "abc"},
                "user": {"id": "123"},
            },
            project_id=self.project.id,
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        javascript = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="javascript"
        )
        assert javascript

        environment_tracking = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="environment_tracking"
        )
        assert environment_tracking

        release_tracking = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="release_tracking"
        )
        assert release_tracking

        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="user_tracking"
        )
        assert feature_complete

    def test_user_tracking(self) -> None:
        event = self.store_event(data={"user": {"id": "123"}}, project_id=self.project.id)
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="user_tracking"
        )
        assert feature_complete

    def test_no_user_tracking_for_ip_address_only(self) -> None:
        """test to see if just sending ip address doesn't check the user tracking box"""
        userless_event = self.store_event(
            data={"user": {"ip_address": "0.0.0.0"}}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=userless_event, sender=type(self.project))

        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="user_tracking"
        )
        assert feature_complete is None

    def test_no_env_tracking(self) -> None:
        envless_event = self.store_event(
            data={"platform": "javascript"}, project_id=self.project.id
        )
        event_processed.send(project=self.project, event=envless_event, sender=type(self.project))

        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="environment_tracking"
        )
        assert feature_complete is None

    def test_custom_tags(self) -> None:
        event = self.store_event(data={}, project_id=self.project.id)
        event.data["tags"].append(("foo", "bar"))
        assert event.get_tag("foo") == "bar"
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        custom_tags = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="custom_tags"
        )
        assert custom_tags

    def test_source_maps(self) -> None:
        event = self.store_event(
            data={
                "platform": "javascript",
                "exception": {
                    "values": [
                        {
                            "stacktrace": {
                                "frames": [
                                    {
                                        "data": {
                                            "sourcemap": "https://media.sentry.io/_static/29e365f8b0d923bc123e8afa38d890c3/sentry/dist/vendor.js.map"
                                        }
                                    }
                                ]
                            },
                            "type": "TypeError",
                        }
                    ]
                },
            },
            project_id=self.project.id,
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        source_maps = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="source_maps"
        )
        assert source_maps

    def test_breadcrumbs(self) -> None:
        event = self.store_event(
            data={
                "breadcrumbs": {
                    "values": [
                        {
                            "category": "xhr",
                            "timestamp": 1496395011.63,
                            "type": "http",
                            "data": {
                                "url": "/api/path/here",
                                "status_code": "500",
                                "method": "POST",
                            },
                        }
                    ]
                }
            },
            project_id=self.project.id,
        )
        event_processed.send(project=self.project, event=event, sender=type(self.project))

        breadcrumbs = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="breadcrumbs"
        )
        assert breadcrumbs

    def test_multiple_events(self) -> None:
        simple_event = self.store_event(
            data={"message": "javascript error message", "platform": "javascript"},
            project_id=self.project.id,
        )
        first_event_received.send(
            project=self.project, event=simple_event, sender=type(self.project)
        )
        event_processed.send(project=self.project, event=simple_event, sender=type(self.project))

        first_event = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="first_event"
        )

        assert first_event.complete

        js = FeatureAdoption.objects.get_by_slug(organization=self.organization, slug="javascript")
        assert js.complete

        full_event = self.store_event(
            data={
                "message": "javascript error message",
                "platform": "javascript",
                "environment": "prod",
                "tags": {"sentry:release": "abc"},
                "user": {"id": "123"},
                "exception": {
                    "values": [
                        {
                            "stacktrace": {
                                "frames": [
                                    {
                                        "data": {
                                            "sourcemap": "https://media.sentry.io/_static/29e365f8b0d923bc123e8afa38d890c3/sentry/dist/vendor.js.map"
                                        }
                                    }
                                ]
                            },
                            "type": "TypeError",
                        }
                    ]
                },
                "breadcrumbs": {
                    "values": [
                        {
                            "category": "xhr",
                            "timestamp": 1496395011.63,
                            "type": "http",
                            "data": {
                                "url": "/api/path/here",
                                "status_code": "500",
                                "method": "POST",
                            },
                        }
                    ]
                },
            },
            project_id=self.project.id,
        )

        event_processed.send(project=self.project, event=full_event, sender=type(self.project))

        release_tracking = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="release_tracking"
        )
        assert release_tracking

        environment_tracking = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="environment_tracking"
        )
        assert environment_tracking

        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="user_tracking"
        )
        assert feature_complete

        source_maps = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="source_maps"
        )
        assert source_maps

        breadcrumbs = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="breadcrumbs"
        )
        assert breadcrumbs

    def test_user_feedback(self) -> None:
        user_feedback_received.send(project=self.project, sender=type(self.project))

        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="user_feedback"
        )
        assert feature_complete

    def test_project_created(self) -> None:
        project_created.send(project=self.project, user=self.owner, sender=type(self.project))
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="first_project"
        )
        assert feature_complete

    def test_member_joined(self) -> None:
        member = self.create_member(
            organization=self.organization, teams=[self.team], user=self.create_user()
        )
        member_joined.send(
            organization_member_id=member.id,
            organization_id=self.organization.id,
            user_id=member.user_id,
            sender=type(self.project),
        )
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="invite_team"
        )
        assert feature_complete

    def test_assignment(self) -> None:
        GroupAssignee.objects.create(
            group_id=self.group.id, user_id=self.user.id, project_id=self.project.id
        )

        issue_assigned.send(
            project=self.project, group=self.group, user=self.user, sender="something"
        )
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="assignment"
        )
        assert feature_complete

    def test_resolved_in_release(self) -> None:
        issue_resolved.send(
            organization_id=self.organization.id,
            project=self.project,
            group=self.group,
            user=self.user,
            resolution_type="in_next_release",
            sender=type(self.project),
        )
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="resolved_in_release"
        )
        assert feature_complete

    def test_resolved_manually(self) -> None:
        issue_resolved.send(
            organization_id=self.organization.id,
            project=self.project,
            group=self.group,
            user=self.user,
            resolution_type="now",
            sender=type(self.project),
        )
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="resolved_in_release"
        )
        assert not feature_complete

    def test_advanced_search(self) -> None:
        advanced_search.send(project=self.project, sender=type(self.project))
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="advanced_search"
        )
        assert feature_complete

    def test_save_search(self) -> None:
        save_search_created.send(project=self.project, user=self.user, sender=type(self.project))
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="saved_search"
        )
        assert feature_complete

    def test_inbound_filters(self) -> None:
        inbound_filter_toggled.send(project=self.project, sender=type(self.project))
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="inbound_filters"
        )
        assert feature_complete

    def test_alert_rules(self) -> None:
        rule = Rule.objects.create(
            project=self.project, label="Trivially modified rule", data=DEFAULT_RULE_DATA
        )

        alert_rule_created.send(
            user=self.owner,
            project=self.project,
            rule_id=rule.id,
            rule_type="issue",
            sender=type(self.project),
            is_api_token=False,
        )
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="alert_rules"
        )
        assert feature_complete

    def test_issue_tracker_plugin(self) -> None:
        plugin_enabled.send(
            plugin=IssueTrackingPlugin2(),
            project=self.project,
            user=self.owner,
            sender=type(self.project),
        )
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="issue_tracker_integration"
        )
        assert feature_complete

    def test_notification_plugin(self) -> None:
        plugin_enabled.send(
            plugin=NotificationPlugin(),
            project=self.project,
            user=self.owner,
            sender=type(self.project),
        )
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="notification_integration"
        )
        assert feature_complete

    def test_sso(self) -> None:
        sso_enabled.send(
            organization_id=self.organization.id,
            user_id=self.user.id,
            provider="google",
            sender=type(self.organization),
        )
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="sso"
        )
        assert feature_complete

    def test_data_scrubber(self) -> None:
        data_scrubber_enabled.send(organization=self.organization, sender=type(self.organization))
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="data_scrubbers"
        )
        assert feature_complete

    def test_delete_and_discard(self) -> None:
        GroupTombstone.objects.create(previous_group_id=self.group.id, project=self.project)
        feature_complete = FeatureAdoption.objects.get_by_slug(
            organization=self.organization, slug="delete_and_discard"
        )
        assert feature_complete
