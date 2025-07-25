from datetime import timedelta

from django.utils import timezone

from sentry.models.environment import Environment
from sentry.models.grouprelease import GroupRelease
from sentry.models.release import Release
from sentry.testutils.cases import TestCase


class GetOrCreateTest(TestCase):
    def test_simple(self) -> None:
        project = self.create_project()
        group = self.create_group(project=project)
        release = Release.objects.create(version="abc", organization_id=project.organization_id)
        release.add_project(project)
        env = Environment.objects.create(organization_id=project.organization_id, name="prod")
        datetime = timezone.now()

        grouprelease = GroupRelease.get_or_create(
            group=group, release=release, environment=env, datetime=datetime
        )

        assert grouprelease.project_id == project.id
        assert grouprelease.group_id == group.id
        assert grouprelease.release_id == release.id
        assert grouprelease.environment == "prod"
        assert grouprelease.first_seen == datetime
        assert grouprelease.last_seen == datetime

        datetime_new = timezone.now() + timedelta(days=1)

        grouprelease = GroupRelease.get_or_create(
            group=group, release=release, environment=env, datetime=datetime_new
        )

        assert grouprelease.first_seen == datetime
        assert grouprelease.last_seen == datetime_new

        datetime_new2 = datetime_new + timedelta(seconds=1)

        # this should not update immediately as the window is too close
        grouprelease = GroupRelease.get_or_create(
            group=group, release=release, environment=env, datetime=datetime_new2
        )

        assert grouprelease.first_seen == datetime
        assert grouprelease.last_seen == datetime_new
