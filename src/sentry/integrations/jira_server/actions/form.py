from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from sentry.integrations.services.integration.service import integration_service
from sentry.integrations.types import IntegrationProviderSlug
from sentry.rules.actions import IntegrationNotifyServiceForm


class JiraServerNotifyServiceForm(IntegrationNotifyServiceForm):
    provider = IntegrationProviderSlug.JIRA_SERVER.value

    def clean(self) -> dict[str, Any] | None:
        cleaned_data = super().clean() or {}

        integration_id = cleaned_data.get("integration")
        integration = integration_service.get_integration(
            integration_id=integration_id, provider=self.provider
        )

        if not integration:
            raise forms.ValidationError(
                _("Jira Server integration is a required field."), code="invalid"
            )
        return cleaned_data
