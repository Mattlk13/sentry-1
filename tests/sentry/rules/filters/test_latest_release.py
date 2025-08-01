from datetime import UTC, datetime

import pytest

from sentry.models.release import Release
from sentry.models.rule import Rule
from sentry.rules.filters.latest_release import LatestReleaseFilter, get_project_release_cache_key
from sentry.testutils.cases import RuleTestCase
from sentry.testutils.skips import requires_snuba
from sentry.utils.cache import cache

pytestmark = [requires_snuba, pytest.mark.sentry_metrics]


class LatestReleaseFilterTest(RuleTestCase):
    rule_cls = LatestReleaseFilter

    def test_latest_release(self) -> None:
        event = self.get_event()
        oldRelease = Release.objects.create(
            organization_id=self.organization.id,
            version="1",
            date_added=datetime(2020, 9, 1, 3, 8, 24, 880386, tzinfo=UTC),
        )
        oldRelease.add_project(self.project)

        newRelease = Release.objects.create(
            organization_id=self.organization.id,
            version="2",
            date_added=datetime(2020, 9, 2, 3, 8, 24, 880386, tzinfo=UTC),
        )
        newRelease.add_project(self.project)

        event.data["tags"] = (("release", newRelease.version),)
        rule = self.get_rule()
        self.assertPasses(rule, event)

    def test_latest_release_no_match(self) -> None:
        event = self.get_event()
        oldRelease = Release.objects.create(
            organization_id=self.organization.id,
            version="1",
            date_added=datetime(2020, 9, 1, 3, 8, 24, 880386, tzinfo=UTC),
        )
        oldRelease.add_project(self.project)

        newRelease = Release.objects.create(
            organization_id=self.organization.id,
            version="2",
            date_added=datetime(2020, 9, 2, 3, 8, 24, 880386, tzinfo=UTC),
        )
        newRelease.add_project(self.project)

        event.data["tags"] = (("release", oldRelease.version),)
        rule = self.get_rule()
        self.assertDoesNotPass(rule, event)

    def test_caching(self) -> None:
        event = self.get_event()
        oldRelease = Release.objects.create(
            organization_id=self.organization.id,
            version="1",
            date_added=datetime(2020, 9, 1, 3, 8, 24, 880386, tzinfo=UTC),
        )
        oldRelease.add_project(self.project)
        event.data["tags"] = (("release", oldRelease.version),)
        rule = self.get_rule()
        self.assertPasses(rule, event)

        newRelease = Release.objects.create(
            organization_id=self.organization.id,
            version="2",
            date_added=datetime(2020, 9, 2, 3, 8, 24, 880386, tzinfo=UTC),
        )
        newRelease.add_project(self.project)

        # ensure we clear the cache after creating a new release
        cache_key = get_project_release_cache_key(event.group.project_id)
        assert cache.get(cache_key) is None

        self.assertDoesNotPass(rule, event)

        # ensure we clear the cache when a release is deleted
        newRelease.safe_delete()
        cache_key = get_project_release_cache_key(event.group.project_id)
        assert cache.get(cache_key) is None

        # rule should pass again because the latest release is oldRelease
        self.assertPasses(rule, event)

    def test_latest_release_with_environment(self) -> None:
        event = self.get_event()
        self.create_release(
            project=event.group.project,
            version="1",
            date_added=datetime(2020, 9, 1, 3, 8, 24, 880386, tzinfo=UTC),
            environments=[self.environment],
        )

        new_release = self.create_release(
            project=event.group.project,
            version="2",
            date_added=datetime(2020, 9, 2, 3, 8, 24, 880386, tzinfo=UTC),
            environments=[self.environment],
        )

        other_env_release = self.create_release(
            project=event.group.project,
            version="4",
            date_added=datetime(2020, 9, 3, 3, 8, 24, 880386, tzinfo=UTC),
        )

        event.data["tags"] = (("release", new_release.version),)
        environment_rule = self.get_rule(rule=Rule(environment_id=self.environment.id))
        self.assertPasses(environment_rule, event)

        event.data["tags"] = (("release", other_env_release.version),)
        environment_rule = self.get_rule(rule=Rule(environment_id=self.environment.id))
        self.assertDoesNotPass(environment_rule, event)
