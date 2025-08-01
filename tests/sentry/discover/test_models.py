import pytest
from django.db import IntegrityError, router, transaction

from sentry.discover.models import DiscoverSavedQuery, DiscoverSavedQueryProject
from sentry.testutils.cases import TestCase
from sentry.testutils.silo import assume_test_silo_mode_of
from sentry.users.models.user import User


class DiscoverSavedQueryTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org = self.create_organization()
        with assume_test_silo_mode_of(User):
            self.user = User.objects.create(email="test@sentry.io")
        self.project_ids = [
            self.create_project(organization=self.org).id,
            self.create_project(organization=self.org).id,
        ]
        self.query = {"fields": ["test"], "conditions": [], "limit": 10}

    def test_create(self) -> None:
        model = DiscoverSavedQuery.objects.create(
            organization=self.org, name="Test query", query=self.query
        )

        model.set_projects(self.project_ids)

        assert DiscoverSavedQuery.objects.get(id=model.id).query == self.query
        assert (
            sorted(DiscoverSavedQueryProject.objects.all().values_list("project_id", flat=True))
            == self.project_ids
        )

    def test_update_projects(self) -> None:
        model = DiscoverSavedQuery.objects.create(
            organization=self.org, name="Test query", query=self.query
        )

        model.set_projects(self.project_ids)

        model.set_projects([])

        assert (
            sorted(DiscoverSavedQueryProject.objects.all().values_list("project_id", flat=True))
            == []
        )

        model.set_projects([self.project_ids[0]])
        assert sorted(
            DiscoverSavedQueryProject.objects.all().values_list("project_id", flat=True)
        ) == [self.project_ids[0]]

    def test_can_only_create_single_homepage_query_for_user(self) -> None:
        DiscoverSavedQuery.objects.create(
            organization=self.org,
            name="Test query",
            query=self.query,
            created_by_id=self.user.id,
            is_homepage=True,
        )

        with pytest.raises(IntegrityError):
            DiscoverSavedQuery.objects.create(
                organization=self.org,
                name="Test query 2",
                query=self.query,
                created_by_id=self.user.id,
                is_homepage=True,
            )

    def test_can_only_have_single_homepage_query_for_user_on_update(self) -> None:
        DiscoverSavedQuery.objects.create(
            organization=self.org,
            name="Test query",
            query=self.query,
            created_by_id=self.user.id,
            is_homepage=True,
        )
        new_query = DiscoverSavedQuery.objects.create(
            organization=self.org,
            name="Test query 2",
            query=self.query,
            created_by_id=self.user.id,
        )

        with (
            pytest.raises(IntegrityError),
            transaction.atomic(router.db_for_write(DiscoverSavedQueryProject)),
        ):
            new_query.update(is_homepage=True)

        with (
            pytest.raises(IntegrityError),
            transaction.atomic(router.db_for_write(DiscoverSavedQueryProject)),
        ):
            new_query.is_homepage = True
            new_query.save()

        with (
            pytest.raises(IntegrityError),
            transaction.atomic(router.db_for_write(DiscoverSavedQueryProject)),
        ):
            DiscoverSavedQuery.objects.filter(id=new_query.id).update(is_homepage=True)

    def test_user_can_have_homepage_query_in_multiple_orgs(self) -> None:
        other_org = self.create_organization()
        DiscoverSavedQuery.objects.create(
            organization=self.org,
            name="Test query",
            query=self.query,
            created_by_id=self.user.id,
            is_homepage=True,
        )
        new_query = DiscoverSavedQuery.objects.create(
            organization=other_org,
            name="Test query 2",
            query=self.query,
            created_by_id=self.user.id,
        )

        # Does not error since the query is in another org
        new_query.update(is_homepage=True)
