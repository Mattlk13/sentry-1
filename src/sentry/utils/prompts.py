from sentry.models.promptsactivity import PromptsActivity
from sentry.utils.request_cache import request_cache

DEFAULT_PROMPTS = {
    "releases": {"required_fields": ["organization_id", "project_id"]},
    "suspect_commits": {"required_fields": ["organization_id", "project_id"]},
    "profiling_onboarding": {"required_fields": ["organization_id"]},
    "alert_stream": {"required_fields": ["organization_id"]},
    "sdk_updates": {"required_fields": ["organization_id"]},
    "suggest_mobile_project": {"required_fields": ["organization_id"]},
    "stacktrace_link": {"required_fields": ["organization_id", "project_id"]},
    "distributed_tracing": {"required_fields": ["organization_id", "project_id"]},
    "quick_trace_missing": {"required_fields": ["organization_id", "project_id"]},
    "code_owners": {"required_fields": ["organization_id", "project_id"]},
    "vitals_alert": {"required_fields": ["organization_id"]},
    "github_missing_members": {"required_fields": ["organization_id"]},
    "metric_alert_ignore_archived_issues": {"required_fields": ["organization_id", "project_id"]},
    "issue_priority": {"required_fields": ["organization_id"]},
    "data_consent_banner": {"required_fields": ["organization_id"]},
    "data_consent_priority": {"required_fields": ["organization_id"]},
    "issue_replay_inline_onboarding": {"required_fields": ["organization_id", "project_id"]},
    "issue_feature_flags_inline_onboarding": {"required_fields": ["organization_id", "project_id"]},
    "issue_feedback_hidden": {"required_fields": ["organization_id", "project_id"]},
    "issue_views_add_view_banner": {"required_fields": ["organization_id"]},
    "stacked_navigation_banner": {"required_fields": ["organization_id"]},
    "stacked_navigation_help_menu": {"required_fields": ["organization_id"]},
}


class PromptsConfig:
    """
    Used to configure available 'prompts' (frontend modals or UI that may be
    dismissed or have some other action recorded about it). This config
    declares what prompts are available And what fields may be required.

    required_fields available: [organization_id, project_id]
    """

    def __init__(self, prompts):
        self.prompts = prompts

    def add(self, name, config):
        if self.has(name):
            raise Exception(f"Prompt key {name} is already in use")
        if "required_fields" not in config:
            raise Exception("'required_fields' must be present in the config dict")

        self.prompts[name] = config

    def has(self, name):
        return name in self.prompts

    def get(self, name):
        return self.prompts[name]

    def required_fields(self, name):
        return self.prompts[name]["required_fields"]


prompt_config = PromptsConfig(DEFAULT_PROMPTS)


@request_cache
def get_prompt_activities_for_user(organization_ids, user_id, features):
    return PromptsActivity.objects.filter(
        organization_id__in=organization_ids, feature__in=features, user_id=user_id
    )
