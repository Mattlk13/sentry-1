from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.db import models
from django.db.models import QuerySet
from django.utils import timezone

from sentry.backup.scopes import RelocationScope
from sentry.constants import ObjectStatus
from sentry.db.models import FlexibleForeignKey, JSONField, Model, region_silo_model, sane_repr
from sentry.db.models.fields.hybrid_cloud_foreign_key import HybridCloudForeignKey
from sentry.db.models.manager.base import BaseManager
from sentry.eventstore.models import GroupEvent

if TYPE_CHECKING:
    from sentry.integrations.models.integration import Integration
    from sentry.integrations.services.integration import RpcIntegration


class ExternalIssueManager(BaseManager["ExternalIssue"]):
    def get_for_integration(
        self, integration: Integration | RpcIntegration, external_issue_key: str | None = None
    ) -> QuerySet[ExternalIssue]:
        from sentry.integrations.services.integration import integration_service

        org_integrations = integration_service.get_organization_integrations(
            integration_id=integration.id
        )

        kwargs = dict(
            integration_id=integration.id,
            organization_id__in=[oi.organization_id for oi in org_integrations],
        )

        if external_issue_key is not None:
            kwargs["key"] = external_issue_key

        return self.filter(**kwargs)

    def get_linked_issues(
        self, event: GroupEvent, integration: RpcIntegration
    ) -> QuerySet[ExternalIssue]:
        from sentry.models.grouplink import GroupLink

        assert event.group is not None
        return self.filter(
            id__in=GroupLink.objects.filter(
                project_id=event.group.project_id,
                group_id=event.group.id,
                linked_type=GroupLink.LinkedType.issue,
            ).values_list("linked_id", flat=True),
            integration_id=integration.id,
        )

    def has_linked_issue(self, event: GroupEvent, integration: RpcIntegration) -> bool:
        return self.get_linked_issues(event, integration).exists()


@region_silo_model
class ExternalIssue(Model):
    __relocation_scope__ = RelocationScope.Excluded

    # The foreign key here is an `int`, not `bigint`.
    organization = FlexibleForeignKey("sentry.Organization", db_constraint=False)

    integration_id = HybridCloudForeignKey("sentry.Integration", on_delete="CASCADE")

    key = models.CharField(max_length=256)  # example APP-123 in jira
    date_added = models.DateTimeField(default=timezone.now)
    title = models.TextField(null=True)
    description = models.TextField(null=True)
    metadata = JSONField(null=True)

    objects: ClassVar[ExternalIssueManager] = ExternalIssueManager()

    class Meta:
        app_label = "sentry"
        db_table = "sentry_externalissue"
        unique_together = (("organization", "integration_id", "key"),)

    __repr__ = sane_repr("organization_id", "integration_id", "key")

    def get_installation(self) -> Any:
        from sentry.integrations.services.integration import integration_service

        integration = integration_service.get_integration(
            integration_id=self.integration_id, status=ObjectStatus.ACTIVE
        )

        assert integration, "Integration is required to get an installation"
        return integration.get_installation(organization_id=self.organization_id)
