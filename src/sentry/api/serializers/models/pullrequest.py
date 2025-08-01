from datetime import datetime
from typing import TypedDict

from sentry.api.serializers import Serializer, register, serialize
from sentry.api.serializers.models.release import Author, get_users_for_authors
from sentry.api.serializers.models.repository import RepositorySerializerResponse
from sentry.models.commitauthor import CommitAuthor
from sentry.models.pullrequest import PullRequest
from sentry.models.repository import Repository


class PullRequestSerializerResponse(TypedDict):
    id: str
    title: str | None
    message: str | None
    dateCreated: datetime
    repository: RepositorySerializerResponse
    author: Author
    externalUrl: str


def get_users_for_pull_requests(item_list, user=None):
    authors = list(
        CommitAuthor.objects.filter(id__in=[i.author_id for i in item_list if i.author_id])
    )

    if authors:
        org_ids = {item.organization_id for item in item_list}
        if len(org_ids) == 1:
            return get_users_for_authors(organization_id=org_ids.pop(), authors=authors, user=user)
    return {}


@register(PullRequest)
class PullRequestSerializer(Serializer):
    def get_attrs(self, item_list, user, **kwargs):
        users_by_author = get_users_for_pull_requests(item_list, user)
        repositories = list(Repository.objects.filter(id__in=[c.repository_id for c in item_list]))
        repository_map = {repository.id: repository for repository in repositories}
        serialized_repos = {r["id"]: r for r in serialize(repositories, user)}

        result = {}
        for item in item_list:
            repository_id = str(item.repository_id)
            external_url = ""
            if item.repository_id in repository_map:
                external_url = item.get_external_url()
            result[item] = {
                "repository": serialized_repos.get(repository_id, {}),
                "external_url": external_url,
                "user": users_by_author.get(str(item.author_id), {}) if item.author_id else {},
            }

        return result

    def serialize(self, obj: PullRequest, attrs, user, **kwargs) -> PullRequestSerializerResponse:
        return {
            "id": obj.key,
            "title": obj.title,
            "message": obj.message,
            "dateCreated": obj.date_added,
            "repository": attrs["repository"],
            "author": attrs["user"],
            "externalUrl": attrs["external_url"],
        }
