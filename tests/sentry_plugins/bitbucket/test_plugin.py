from functools import cached_property

import pytest
import responses
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from sentry.exceptions import PluginError
from sentry.testutils.cases import PluginTestCase
from sentry_plugins.bitbucket.plugin import BitbucketPlugin


def test_conf_key() -> None:
    assert BitbucketPlugin().conf_key == "bitbucket"


class BitbucketPluginTest(PluginTestCase):
    @cached_property
    def plugin(self):
        return BitbucketPlugin()

    @cached_property
    def request(self):
        return RequestFactory()

    def test_get_issue_label(self) -> None:
        group = self.create_group(message="Hello world", culprit="foo.bar")
        assert self.plugin.get_issue_label(group, 1) == "Bitbucket-1"

    def test_get_issue_url(self) -> None:
        self.plugin.set_option("repo", "maxbittker/newsdiffs", self.project)
        group = self.create_group(message="Hello world", culprit="foo.bar")
        assert (
            self.plugin.get_issue_url(group, 1)
            == "https://bitbucket.org/maxbittker/newsdiffs/issue/1/"
        )

    def test_is_configured(self) -> None:
        assert self.plugin.is_configured(self.project) is False
        self.plugin.set_option("repo", "maxbittker/newsdiffs", self.project)
        assert self.plugin.is_configured(self.project) is True

    @responses.activate
    def test_create_issue(self) -> None:
        responses.add(
            responses.POST,
            "https://api.bitbucket.org/1.0/repositories/maxbittker/newsdiffs/issues",
            json={"local_id": 1, "title": "Hello world"},
        )

        self.plugin.set_option("repo", "maxbittker/newsdiffs", self.project)
        group = self.create_group(message="Hello world", culprit="foo.bar")

        request = self.request.get("/")
        request.user = AnonymousUser()
        form_data = {
            "title": "Hello",
            "description": "Fix this.",
            "issue_type": "bug",
            "priority": "trivial",
        }
        with pytest.raises(PluginError):
            self.plugin.create_issue(request, group, form_data)

        request.user = self.user
        self.login_as(self.user)
        self.create_usersocialauth(
            user=self.user,
            provider=self.plugin.auth_provider,
            extra_data={
                "access_token": (
                    "oauth_token=123456789abcdefghi&"
                    "oauth_token_secret="
                    "123456789123456789abcdefghijklmn"
                )
            },
        )

        assert self.plugin.create_issue(request, group, form_data) == 1

        request = responses.calls[-1].request
        assert request.headers["Authorization"].startswith("OAuth ")

    @responses.activate
    def test_link_issue(self) -> None:
        responses.add(
            responses.GET,
            "https://api.bitbucket.org/1.0/repositories/maxbittker/newsdiffs/issues/1",
            json={"local_id": 1, "title": "Hello world"},
        )
        responses.add(
            responses.POST,
            "https://api.bitbucket.org/1.0/repositories/maxbittker/newsdiffs/issues/1/comments",
            json={"body": "Hello"},
        )

        self.plugin.set_option("repo", "maxbittker/newsdiffs", self.project)
        group = self.create_group(message="Hello world", culprit="foo.bar")

        request = self.request.get("/")
        request.user = AnonymousUser()
        form_data = {"comment": "Hello", "issue_id": "1"}
        with pytest.raises(PluginError):
            self.plugin.link_issue(request, group, form_data)

        request.user = self.user
        self.login_as(self.user)
        self.create_usersocialauth(
            user=self.user,
            provider=self.plugin.auth_provider,
            extra_data={
                "access_token": (
                    "oauth_token=123456789abcdefghi&oauth_token_secret="
                    "123456789123456789abcdefghijklmn"
                )
            },
        )

        assert self.plugin.link_issue(request, group, form_data) == {"title": "Hello world"}
