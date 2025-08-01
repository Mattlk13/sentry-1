from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import sentry_sdk
from django.db import connection
from django.db.models import Value
from django.db.models.functions import StrIndex
from django.utils import timezone as django_timezone
from snuba_sdk import (
    BooleanCondition,
    BooleanOp,
    Column,
    Condition,
    Direction,
    Entity,
    Function,
    Op,
    OrderBy,
    Query,
)
from snuba_sdk import Request as SnubaRequest

from sentry import analytics
from sentry.analytics.events.open_pr_comment import OpenPRCommentCreatedEvent
from sentry.auth.exceptions import IdentityNotValid
from sentry.integrations.gitlab.constants import GITLAB_CLOUD_BASE_URL
from sentry.integrations.models.repository_project_path_config import RepositoryProjectPathConfig
from sentry.integrations.source_code_management.constants import STACKFRAME_COUNT
from sentry.integrations.source_code_management.language_parsers import (
    get_patch_parsers_for_organization,
)
from sentry.integrations.source_code_management.metrics import (
    CommitContextHaltReason,
    CommitContextIntegrationInteractionEvent,
    SCMIntegrationInteractionType,
)
from sentry.integrations.types import ExternalProviderEnum
from sentry.locks import locks
from sentry.models.commit import Commit
from sentry.models.group import Group, GroupStatus
from sentry.models.groupowner import GroupOwner
from sentry.models.options.organization_option import OrganizationOption
from sentry.models.organization import Organization
from sentry.models.project import Project
from sentry.models.pullrequest import (
    CommentType,
    PullRequest,
    PullRequestComment,
    PullRequestCommit,
)
from sentry.models.repository import Repository
from sentry.shared_integrations.exceptions import (
    ApiError,
    ApiHostError,
    ApiInvalidRequestError,
    ApiRateLimitedError,
    ApiRetryError,
)
from sentry.snuba.dataset import Dataset
from sentry.snuba.referrer import Referrer
from sentry.users.models.identity import Identity
from sentry.utils import metrics
from sentry.utils.cache import cache
from sentry.utils.snuba import raw_snql_query

logger = logging.getLogger(__name__)


def _debounce_pr_comment_cache_key(pullrequest_id: int) -> str:
    return f"pr-comment-{pullrequest_id}"


def _debounce_pr_comment_lock_key(pullrequest_id: int) -> str:
    return f"queue_comment_task:{pullrequest_id}"


def _pr_comment_log(integration_name: str, suffix: str) -> str:
    return f"{integration_name}.pr_comment.{suffix}"


def _open_pr_comment_log(integration_name: str, suffix: str) -> str:
    return f"{integration_name}.open_pr_comment.{suffix}"


PR_COMMENT_TASK_TTL = timedelta(minutes=5).total_seconds()
PR_COMMENT_WINDOW = 14  # days

MERGED_PR_METRICS_BASE = "{integration}.pr_comment.{key}"
OPEN_PR_METRICS_BASE = "{integration}.open_pr_comment.{key}"
MAX_SUSPECT_COMMITS = 1000

OPEN_PR_MAX_RECENT_ISSUES = 5000
# Caps the number of files that can be modified in a PR to leave a comment
OPEN_PR_MAX_FILES_CHANGED = 7
# Caps the number of lines that can be modified in a PR to leave a comment
OPEN_PR_MAX_LINES_CHANGED = 500


@dataclass
class SourceLineInfo:
    lineno: int | None
    path: str
    ref: str
    repo: Repository
    code_mapping: RepositoryProjectPathConfig


@dataclass
class CommitInfo:
    commitId: str
    committedDate: datetime
    commitMessage: str | None
    commitAuthorName: str | None
    commitAuthorEmail: str | None


@dataclass
class FileBlameInfo(SourceLineInfo):
    commit: CommitInfo


@dataclass
class PullRequestIssue:
    title: str
    subtitle: str | None
    url: str
    affected_users: int | None = None
    event_count: int | None = None
    function_name: str | None = None


@dataclass
class PullRequestFile:
    filename: str
    patch: str


ISSUE_TITLE_MAX_LENGTH = 50
MERGED_PR_SINGLE_ISSUE_TEMPLATE = "* ‼️ [**{title}**]({url}){environment}\n"


class CommitContextIntegration(ABC):
    """
    Base class for integrations that include commit context features: suspect commits, suspect PR comments
    """

    @property
    @abstractmethod
    def integration_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_client(self) -> CommitContextClient:
        raise NotImplementedError

    def get_blame_for_files(
        self, files: Sequence[SourceLineInfo], extra: dict[str, Any]
    ) -> list[FileBlameInfo]:
        """
        Calls the client's `get_blame_for_files` method to fetch blame for a list of files.

        files: list of FileBlameInfo objects
        """
        with CommitContextIntegrationInteractionEvent(
            interaction_type=SCMIntegrationInteractionType.GET_BLAME_FOR_FILES,
            provider_key=self.integration_name,
        ).capture() as lifecycle:
            try:
                client = self.get_client()
            except Identity.DoesNotExist as e:
                lifecycle.record_failure(e)
                sentry_sdk.capture_exception(e)
                return []

            try:
                response = client.get_blame_for_files(files, extra)
            except IdentityNotValid as e:
                lifecycle.record_failure(e)
                sentry_sdk.capture_exception(e)
                return []
            # Swallow rate limited errors so we don't log them as exceptions
            except ApiRateLimitedError as e:
                sentry_sdk.capture_exception(e)
                lifecycle.record_halt(e)
                return []
            except ApiInvalidRequestError as e:
                # Ignore invalid request errors for GitLab
                # TODO(ecosystem): Remove this once we have a better way to handle this
                if self.integration_name == ExternalProviderEnum.GITLAB.value:
                    lifecycle.record_halt(e)
                    return []
                else:
                    raise
            except (ApiRetryError, ApiHostError) as e:
                # Ignore retry errors for GitLab
                # Ignore host error errors for GitLab
                # TODO(ecosystem): Remove this once we have a better way to handle this
                if (
                    self.integration_name == ExternalProviderEnum.GITLAB.value
                    and client.base_url != GITLAB_CLOUD_BASE_URL
                ):
                    lifecycle.record_halt(e)
                    return []
                else:
                    raise
            return response

    def get_commit_context_all_frames(
        self, files: Sequence[SourceLineInfo], extra: dict[str, Any]
    ) -> list[FileBlameInfo]:
        """
        Given a list of source files and line numbers,returns the commit info for the most recent commit.
        """
        return self.get_blame_for_files(files, extra)

    def queue_pr_comment_task_if_needed(
        self,
        project: Project,
        commit: Commit,
        group_owner: GroupOwner,
        group_id: int,
    ) -> None:
        try:
            # TODO(jianyuan): Remove this try/except once we have implemented the abstract method for all integrations
            pr_comment_workflow = self.get_pr_comment_workflow()
        except NotImplementedError:
            return

        if not OrganizationOption.objects.get_value(
            organization=project.organization,
            key=pr_comment_workflow.organization_option_key,
            default=True,
        ):
            return

        repo_query = Repository.objects.filter(id=commit.repository_id).order_by("-date_added")
        group = Group.objects.get_from_cache(id=group_id)
        if not (
            group.level is not logging.INFO and repo_query.exists()
        ):  # Don't comment on info level issues
            return

        with CommitContextIntegrationInteractionEvent(
            interaction_type=SCMIntegrationInteractionType.QUEUE_COMMENT_TASK,
            provider_key=self.integration_name,
            organization=project.organization,
            project=project,
            commit=commit,
        ).capture() as lifecycle:
            repo: Repository = repo_query.get()
            lifecycle.add_extras(
                {
                    "repository_id": repo.id,
                    "group_id": group_id,
                }
            )

            logger.info(
                _pr_comment_log(
                    integration_name=self.integration_name, suffix="queue_comment_check"
                ),
                extra={"organization_id": commit.organization_id, "merge_commit_sha": commit.key},
            )
            scope = sentry_sdk.get_isolation_scope()
            scope.set_tag("queue_comment_check.merge_commit_sha", commit.key)
            scope.set_tag("queue_comment_check.organization_id", commit.organization_id)

            # client will raise an Exception if the request is not successful
            try:
                client = self.get_client()
                merge_commit_sha = client.get_merge_commit_sha_from_commit(
                    repo=repo, sha=commit.key
                )
            except Exception as e:
                sentry_sdk.capture_exception(e)
                lifecycle.record_halt(e)
                return

            if merge_commit_sha is None:
                lifecycle.add_extra("commit_sha", commit.key)
                lifecycle.record_halt(CommitContextHaltReason.COMMIT_NOT_IN_DEFAULT_BRANCH)
                return

            lifecycle.add_extra("merge_commit_sha", merge_commit_sha)

            pr_query = PullRequest.objects.filter(
                organization_id=commit.organization_id,
                repository_id=commit.repository_id,
                merge_commit_sha=merge_commit_sha,
            )
            if not pr_query.exists():
                lifecycle.record_halt(CommitContextHaltReason.MISSING_PR)
                return

            pr = pr_query.first()
            lifecycle.add_extra("pull_request_id", pr.id if pr else None)
            assert pr is not None
            # need to query explicitly for merged PR comments since we can have multiple comments per PR
            merged_pr_comment_query = PullRequestComment.objects.filter(
                pull_request_id=pr.id, comment_type=CommentType.MERGED_PR
            )
            if pr.date_added >= datetime.now(tz=timezone.utc) - timedelta(
                days=PR_COMMENT_WINDOW
            ) and (
                not merged_pr_comment_query.exists()
                or group_owner.group_id not in merged_pr_comment_query[0].group_ids
            ):
                lock = locks.get(
                    _debounce_pr_comment_lock_key(pr.id), duration=10, name="queue_comment_task"
                )
                with lock.acquire():
                    cache_key = _debounce_pr_comment_cache_key(pullrequest_id=pr.id)
                    if cache.get(cache_key) is not None:
                        lifecycle.record_halt(CommitContextHaltReason.ALREADY_QUEUED)
                        return

                    # create PR commit row for suspect commit and PR
                    PullRequestCommit.objects.get_or_create(commit=commit, pull_request=pr)

                    logger.info(
                        _pr_comment_log(
                            integration_name=self.integration_name, suffix="queue_comment_workflow"
                        ),
                        extra={"pullrequest_id": pr.id, "project_id": group_owner.project_id},
                    )

                    cache.set(cache_key, True, PR_COMMENT_TASK_TTL)

                    pr_comment_workflow.queue_task(pr=pr, project_id=group_owner.project_id)

    def queue_open_pr_comment_task_if_needed(
        self, pr: PullRequest, organization: Organization
    ) -> None:
        try:
            open_pr_comment_workflow = self.get_open_pr_comment_workflow()
        except NotImplementedError:
            return

        if not OrganizationOption.objects.get_value(
            organization=organization,
            key=open_pr_comment_workflow.organization_option_key,
            default=True,
        ):
            logger.info(
                _open_pr_comment_log(
                    integration_name=self.integration_name, suffix="option_missing"
                ),
                extra={"organization_id": organization.id},
            )
            return

        metrics.incr(
            OPEN_PR_METRICS_BASE.format(integration=self.integration_name, key="queue_task")
        )
        logger.info(
            _open_pr_comment_log(integration_name=self.integration_name, suffix="queue_task"),
            extra={"pr_id": pr.id},
        )
        open_pr_comment_workflow.queue_task(pr=pr)

    def create_or_update_comment(
        self,
        repo: Repository,
        pr: PullRequest,
        comment_data: dict[str, Any],
        issue_list: list[int],
        metrics_base: str,
        comment_type: int = CommentType.MERGED_PR,
        language: str | None = None,
    ):
        client = self.get_client()

        pr_comment = PullRequestComment.objects.filter(
            pull_request__id=pr.id, comment_type=comment_type
        ).first()

        interaction_type = (
            SCMIntegrationInteractionType.CREATE_COMMENT
            if not pr_comment
            else SCMIntegrationInteractionType.UPDATE_COMMENT
        )

        with CommitContextIntegrationInteractionEvent(
            interaction_type=interaction_type,
            provider_key=self.integration_name,
            repository=repo,
            pull_request_id=pr.id,
        ).capture():
            if pr_comment is None:
                resp = client.create_pr_comment(repo=repo, pr=pr, data=comment_data)

                current_time = django_timezone.now()
                comment = PullRequestComment.objects.create(
                    external_id=resp.body["id"],
                    pull_request_id=pr.id,
                    created_at=current_time,
                    updated_at=current_time,
                    group_ids=issue_list,
                    comment_type=comment_type,
                )
                metrics.incr(
                    metrics_base.format(integration=self.integration_name, key="comment_created")
                )

                if comment_type == CommentType.OPEN_PR:
                    analytics.record(
                        OpenPRCommentCreatedEvent(
                            comment_id=comment.id,
                            org_id=repo.organization_id,
                            pr_id=pr.id,
                            language=(language or "not found"),
                        )
                    )
            else:
                resp = client.update_pr_comment(
                    repo=repo,
                    pr=pr,
                    pr_comment=pr_comment,
                    data=comment_data,
                )
                metrics.incr(
                    metrics_base.format(integration=self.integration_name, key="comment_updated")
                )
                pr_comment.updated_at = django_timezone.now()
                pr_comment.group_ids = issue_list
                pr_comment.save()

            logger_event = metrics_base.format(
                integration=self.integration_name, key="create_or_update_comment"
            )
            logger.info(
                logger_event,
                extra={"new_comment": pr_comment is None, "pr_key": pr.key, "repo": repo.name},
            )

    @abstractmethod
    def on_create_or_update_comment_error(self, api_error: ApiError, metrics_base: str) -> bool:
        """
        Handle errors from the create_or_update_comment method.

        Returns True if the error was handled, False otherwise.
        """
        raise NotImplementedError

    # TODO(jianyuan): Make this an abstract method
    def get_pr_comment_workflow(self) -> PRCommentWorkflow:
        raise NotImplementedError

    def get_open_pr_comment_workflow(self) -> OpenPRCommentWorkflow:
        raise NotImplementedError


class CommitContextClient(ABC):
    base_url: str

    @abstractmethod
    def get_blame_for_files(
        self, files: Sequence[SourceLineInfo], extra: dict[str, Any]
    ) -> list[FileBlameInfo]:
        """Get the blame for a list of files. This method should include custom metrics for the specific integration implementation."""
        raise NotImplementedError

    @abstractmethod
    def create_comment(self, repo: str, issue_id: str, data: dict[str, Any]) -> Any:
        raise NotImplementedError

    @abstractmethod
    def update_comment(
        self, repo: str, issue_id: str, comment_id: str, data: dict[str, Any]
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def create_pr_comment(self, repo: Repository, pr: PullRequest, data: dict[str, Any]) -> Any:
        raise NotImplementedError

    @abstractmethod
    def update_pr_comment(
        self,
        repo: Repository,
        pr: PullRequest,
        pr_comment: PullRequestComment,
        data: dict[str, Any],
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def get_merge_commit_sha_from_commit(self, repo: Repository, sha: str) -> str | None:
        raise NotImplementedError


class PRCommentWorkflow(ABC):
    def __init__(self, integration: CommitContextIntegration):
        self.integration = integration

    @property
    @abstractmethod
    def organization_option_key(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def referrer(self) -> Referrer:
        raise NotImplementedError

    @property
    @abstractmethod
    def referrer_id(self) -> str:
        raise NotImplementedError

    def queue_task(self, pr: PullRequest, project_id: int) -> None:
        from sentry.integrations.source_code_management.tasks import pr_comment_workflow

        pr_comment_workflow.delay(pr_id=pr.id, project_id=project_id)

    @abstractmethod
    def get_comment_body(self, issue_ids: list[int]) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_comment_data(
        self,
        organization: Organization,
        repo: Repository,
        pr: PullRequest,
        comment_body: str,
        issue_ids: list[int],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def get_issue_ids_from_pr(self, pr: PullRequest, limit: int = MAX_SUSPECT_COMMITS) -> list[int]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT go.group_id issue_id
                FROM sentry_groupowner go
                JOIN sentry_pullrequest_commit c ON c.commit_id = (go.context::jsonb->>'commitId')::bigint
                JOIN sentry_pull_request pr ON c.pull_request_id = pr.id
                WHERE go.type=0
                AND pr.id=%s
                ORDER BY go.date_added
                LIMIT %s
                """,
                params=[pr.id, limit],
            )
            return [issue_id for (issue_id,) in cursor.fetchall()]

    def get_top_5_issues_by_count(
        self, issue_ids: list[int], project: Project
    ) -> list[dict[str, Any]]:
        """Given a list of issue group ids, return a sublist of the top 5 ordered by event count"""
        request = SnubaRequest(
            dataset=Dataset.Events.value,
            app_id="default",
            tenant_ids={"organization_id": project.organization_id},
            query=(
                Query(Entity("events"))
                .set_select([Column("group_id"), Function("count", [], "event_count")])
                .set_groupby([Column("group_id")])
                .set_where(
                    [
                        Condition(Column("project_id"), Op.EQ, project.id),
                        Condition(Column("group_id"), Op.IN, issue_ids),
                        Condition(Column("timestamp"), Op.GTE, datetime.now() - timedelta(days=30)),
                        Condition(Column("timestamp"), Op.LT, datetime.now()),
                        Condition(Column("level"), Op.NEQ, "info"),
                    ]
                )
                .set_orderby([OrderBy(Column("event_count"), Direction.DESC)])
                .set_limit(5)
            ),
        )
        return raw_snql_query(request, referrer=self.referrer.value)["data"]

    @staticmethod
    def _truncate_title(title: str, max_length: int = ISSUE_TITLE_MAX_LENGTH) -> str:
        """Truncate title if it's too long and add ellipsis."""
        if len(title) <= max_length:
            return title
        return title[:max_length].rstrip() + "..."

    def get_environment_info(self, issue: Group) -> str:
        try:
            recommended_event = issue.get_recommended_event()
            if recommended_event:
                environment = recommended_event.get_environment()
                if environment and environment.name:
                    return f" in `{environment.name}`"
        except Exception as e:
            # If anything goes wrong, just continue without environment info
            logger.info(
                "get_environment_info.no-environment",
                extra={"issue_id": issue.id, "error": e},
            )
        return ""

    @staticmethod
    def get_merged_pr_single_issue_template(title: str, url: str, environment: str) -> str:
        truncated_title = PRCommentWorkflow._truncate_title(title)
        return MERGED_PR_SINGLE_ISSUE_TEMPLATE.format(
            title=truncated_title,
            url=url,
            environment=environment,
        )


class OpenPRCommentWorkflow(ABC):
    def __init__(self, integration: CommitContextIntegration):
        self.integration = integration

    @property
    @abstractmethod
    def organization_option_key(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def referrer(self) -> Referrer:
        raise NotImplementedError

    @property
    @abstractmethod
    def referrer_id(self) -> str:
        raise NotImplementedError

    def queue_task(self, pr: PullRequest) -> None:
        from sentry.integrations.source_code_management.tasks import open_pr_comment_workflow

        open_pr_comment_workflow.delay(pr_id=pr.id)

    @abstractmethod
    def get_pr_files_safe_for_comment(
        self, repo: Repository, pr: PullRequest
    ) -> list[PullRequestFile]:
        raise NotImplementedError

    @abstractmethod
    def get_comment_data(self, comment_body: str) -> dict[str, Any]:
        raise NotImplementedError

    def get_projects_and_filenames_from_source_file(
        self,
        organization: Organization,
        repo: Repository,
        pr_filename: str,
    ) -> tuple[set[Project], set[str]]:
        # fetch the code mappings in which the source_root is a substring at the start of pr_filename
        code_mappings = (
            RepositoryProjectPathConfig.objects.filter(
                organization_id=organization.id,
                repository_id=repo.id,
            )
            .annotate(substring_match=StrIndex(Value(pr_filename), "source_root"))
            .filter(substring_match=1)
        )

        project_list: set[Project] = set()
        sentry_filenames = set()

        if len(code_mappings):
            for code_mapping in code_mappings:
                project_list.add(code_mapping.project)
                sentry_filenames.add(
                    pr_filename.replace(code_mapping.source_root, code_mapping.stack_root, 1)
                )
        return project_list, sentry_filenames

    def get_top_5_issues_by_count_for_file(
        self, projects: list[Project], sentry_filenames: list[str], function_names: list[str]
    ) -> list[dict[str, Any]]:
        """
        Given a list of projects, filenames reverse-codemapped into filenames in Sentry,
        and function names representing the list of functions changed in a PR file, return a
        sublist of the top 5 recent unhandled issues ordered by event count.
        """
        if not len(projects):
            logger.info(
                "open_pr_comment.no_projects",
                extra={"sentry_filenames": sentry_filenames},
            )
            return []

        patch_parsers = get_patch_parsers_for_organization(projects[0].organization)

        # fetches the appropriate parser for formatting the snuba query given the file extension
        # the extension is never replaced in reverse codemapping
        language_parser = patch_parsers.get(sentry_filenames[0].split(".")[-1], None)

        if not language_parser:
            logger.info(
                "open_pr_comment.no_language_parser",
                extra={"sentry_filenames": sentry_filenames},
            )
            return []

        group_ids = list(
            Group.objects.filter(
                first_seen__gte=datetime.now(UTC) - timedelta(days=90),
                last_seen__gte=datetime.now(UTC) - timedelta(days=14),
                status=GroupStatus.UNRESOLVED,
                project__in=projects,
            )
            .order_by("-times_seen")
            .values_list("id", flat=True)
        )[:OPEN_PR_MAX_RECENT_ISSUES]

        if projects[0].organization_id == 1:
            logger.info(
                "open_pr_comment.length_of_group_ids",
                extra={"group_ids_length": len(group_ids)},
            )

        project_ids = [p.id for p in projects]

        multi_if = language_parser.generate_multi_if(function_names)

        # fetch the count of events for each group_id
        subquery = (
            Query(Entity("events"))
            .set_select(
                [
                    Column("title"),
                    Column("culprit"),
                    Column("group_id"),
                    Function("count", [], "event_count"),
                    Function(
                        "multiIf",
                        multi_if,
                        "function_name",
                    ),
                ]
            )
            .set_groupby(
                [
                    Column("title"),
                    Column("culprit"),
                    Column("group_id"),
                    Column("exception_frames.function"),
                ]
            )
            .set_where(
                [
                    Condition(Column("project_id"), Op.IN, project_ids),
                    Condition(Column("group_id"), Op.IN, group_ids),
                    Condition(Column("timestamp"), Op.GTE, datetime.now() - timedelta(days=14)),
                    Condition(Column("timestamp"), Op.LT, datetime.now()),
                    # NOTE: ideally this would follow suspect commit logic
                    BooleanCondition(
                        BooleanOp.OR,
                        [
                            BooleanCondition(
                                BooleanOp.AND,
                                [
                                    Condition(
                                        Function(
                                            "arrayElement",
                                            (Column("exception_frames.filename"), i),
                                        ),
                                        Op.IN,
                                        sentry_filenames,
                                    ),
                                    language_parser.generate_function_name_conditions(
                                        function_names, i
                                    ),
                                ],
                            )
                            for i in range(-STACKFRAME_COUNT, 0)  # first n frames
                        ],
                    ),
                    Condition(Function("notHandled", []), Op.EQ, 1),
                ]
            )
            .set_orderby([OrderBy(Column("event_count"), Direction.DESC)])
        )

        # filter on the subquery to squash group_ids with the same title and culprit
        # return the group_id with the greatest count of events
        query = (
            Query(subquery)
            .set_select(
                [
                    Column("function_name"),
                    Function(
                        "arrayElement",
                        (Function("groupArray", [Column("group_id")]), 1),
                        "group_id",
                    ),
                    Function(
                        "arrayElement",
                        (Function("groupArray", [Column("event_count")]), 1),
                        "event_count",
                    ),
                ]
            )
            .set_groupby(
                [
                    Column("title"),
                    Column("culprit"),
                    Column("function_name"),
                ]
            )
            .set_orderby([OrderBy(Column("event_count"), Direction.DESC)])
            .set_limit(5)
        )

        request = SnubaRequest(
            dataset=Dataset.Events.value,
            app_id="default",
            tenant_ids={"organization_id": projects[0].organization_id},
            query=query,
        )

        if projects[0].organization_id == 1:
            logger.info(
                "open_pr_comment.snuba_query",
                extra={"query": request.to_dict()["query"]},
            )

        try:
            return raw_snql_query(request, referrer=self.referrer.value)["data"]
        except Exception:
            logger.exception(
                "github.open_pr_comment.snuba_query_error",
                extra={"query": request.to_dict()["query"]},
            )
            return []

    @abstractmethod
    def format_open_pr_comment(self, issue_tables: list[str]) -> str:
        """
        Given a list of issue tables, return a string that can be used to format an open PR comment.
        """
        raise NotImplementedError

    @abstractmethod
    def format_issue_table(
        self,
        diff_filename: str,
        issues: list[PullRequestIssue],
        patch_parsers: dict[str, Any],
        toggle: bool,
    ) -> str:
        """
        Given a list of issues, return a string that can be used to format an issue table.
        """
        raise NotImplementedError

    @staticmethod
    def get_issue_table_contents(issue_list: list[dict[str, Any]]) -> list[PullRequestIssue]:
        """
        Given a list of issue group ids, return a list of PullRequestIssue objects sorted by event count.
        """
        group_id_to_info = {}
        for issue in issue_list:
            group_id = issue["group_id"]
            group_id_to_info[group_id] = dict(filter(lambda k: k[0] != "group_id", issue.items()))

        issues = Group.objects.filter(id__in=list(group_id_to_info.keys())).all()

        pull_request_issues = [
            PullRequestIssue(
                title=issue.title,
                subtitle=issue.culprit,
                url=issue.get_absolute_url(),
                affected_users=issue.count_users_seen(
                    referrer=Referrer.TAGSTORE_GET_GROUPS_USER_COUNTS_OPEN_PR_COMMENT.value
                ),
                event_count=group_id_to_info[issue.id]["event_count"],
                function_name=group_id_to_info[issue.id]["function_name"],
            )
            for issue in issues
        ]
        pull_request_issues.sort(key=lambda k: k.event_count or 0, reverse=True)

        return pull_request_issues
