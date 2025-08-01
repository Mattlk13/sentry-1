import zipfile
from io import BytesIO
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from sentry.models.debugfile import ProjectDebugFile
from sentry.models.files.file import File
from sentry.models.release import Release
from sentry.models.releasefile import ReleaseFile
from sentry.testutils.cases import APITestCase
from sentry.testutils.helpers.response import close_streaming_response

# This is obviously a freely generated UUID and not the checksum UUID.
# This is permissible if users want to send different UUIDs
PROGUARD_UUID = "6dc7fdb0-d2fb-4c8e-9d6b-bb1aa98929b1"
PROGUARD_SOURCE = b"""\
org.slf4j.helpers.Util$ClassContextSecurityManager -> org.a.b.g$a:
65:65:void <init>() -> <init>
67:67:java.lang.Class[] getClassContext() -> getClassContext
65:65:void <init>(org.slf4j.helpers.Util$1) -> <init>
"""


class DebugFilesTestCases(APITestCase):
    def setUp(self) -> None:
        self.url = reverse(
            "sentry-api-0-dsym-files",
            kwargs={
                "organization_id_or_slug": self.organization.slug,
                "project_id_or_slug": self.project.slug,
            },
        )
        self.login_as(user=self.user)

    def _upload_proguard(self, url, uuid):
        out = BytesIO()
        f = zipfile.ZipFile(out, "w")
        f.writestr("proguard/%s.txt" % uuid, PROGUARD_SOURCE)
        f.close()

        return self.client.post(
            url,
            {
                "file": SimpleUploadedFile(
                    "symbols.zip", out.getvalue(), content_type="application/zip"
                )
            },
            format="multipart",
        )


class DebugFilesTest(DebugFilesTestCases):
    def test_simple_proguard_upload(self) -> None:
        response = self._upload_proguard(self.url, PROGUARD_UUID)
        assert response.status_code == 201, response.content
        assert len(response.data) == 1
        assert response.data[0]["headers"] == {"Content-Type": "text/x-proguard+plain"}
        assert response.data[0]["sha1"] == "e6d3c5185dac63eddfdc1a5edfffa32d46103b44"
        assert response.data[0]["uuid"] == PROGUARD_UUID
        assert response.data[0]["objectName"] == "proguard-mapping"
        assert response.data[0]["cpuName"] == "any"
        assert response.data[0]["symbolType"] == "proguard"

    def test_dsyms_search(self) -> None:
        for i in range(25):
            last_uuid = str(uuid4())
            self._upload_proguard(self.url, last_uuid)

        # Test max 20 per page
        response = self.client.get(self.url)
        assert response.status_code == 200, response.content
        dsyms = response.data
        assert len(dsyms) == 20

        # Test should return last
        response = self.client.get(self.url + "?query=" + last_uuid)
        assert response.status_code == 200, response.content
        dsyms = response.data
        assert len(dsyms) == 1

        response = self.client.get(self.url + "?query=proguard")
        assert response.status_code == 200, response.content
        dsyms = response.data
        assert len(dsyms) == 20

    def test_dsyms_debugid_codeid_full_match(self) -> None:
        self._do_test_dsyms_by_debugid_and_codeid(
            ("dfb8e43a-f242-3d73-a453-aeb6a777ef75", "ae0459704fc7256"),
            [(True, "dfb8e43a-f242-3d73-a453-aeb6a777ef75", "ae0459704fc7256")],
        )

    def test_dsyms_debugid_codeid_full_match_and_partials(self) -> None:
        self._do_test_dsyms_by_debugid_and_codeid(
            ("dfb8e43a-f242-3d73-a453-aeb6a777ef75", "ae0459704fc7256"),
            [
                (True, "dfb8e43a-f242-3d73-a453-aeb6a777ef75", "ae0459704fc7256"),
                (False, "00000000-000000000-0000-000000000000", "ae0459704fc7256"),
                (True, "dfb8e43a-f242-3d73-a453-aeb6a777ef75", "000000000000000"),
            ],
        )

    def test_dsyms_debugid_codeid_only_codeid(self) -> None:
        self._do_test_dsyms_by_debugid_and_codeid(
            ("22222222-000000000-0000-000000000000", "ae0459704fc7256"),
            [
                (True, "10000000-000000000-0000-000000000000", "ae0459704fc7256"),
                (True, "00000000-000000000-0000-000000000000", "ae0459704fc7256"),
                (False, "dfb8e43a-f242-3d73-a453-aeb6a777ef75", "000000000000000"),
            ],
        )

    def _do_test_dsyms_by_debugid_and_codeid(self, query, files):
        for _, debug_id, code_id in files:
            self.create_dif_file(debug_id=debug_id, code_id=code_id)

        response = self.client.get(f"{self.url}?debug_id={query[0]}&code_id={query[1]}")
        assert response.status_code == 200, response.content

        actual = sorted((dsym["debugId"], dsym["codeId"]) for dsym in response.data)
        assert actual == sorted((debug_id, code_id) for (exp, debug_id, code_id) in files if exp)

    def test_access_control(self) -> None:
        # create a debug files such as proguard:
        response = self._upload_proguard(self.url, PROGUARD_UUID)
        assert response.status_code == 201, response.content
        assert len(response.data) == 1

        response = self.client.get(self.url)
        assert response.status_code == 200, response.content

        (dsym,) = response.data
        download_id = dsym["id"]

        # `self.user` has access to these files
        response = self.client.get(f"{self.url}?id={download_id}")
        assert response.status_code == 200, response.content
        assert PROGUARD_SOURCE == close_streaming_response(response)

        # with another user on a different org
        other_user = self.create_user()
        other_org = self.create_organization(name="other-org", owner=other_user)
        other_project = self.create_project(organization=other_org)
        url = reverse(
            "sentry-api-0-dsym-files",
            kwargs={
                "organization_id_or_slug": other_org.slug,
                "project_id_or_slug": other_project.slug,
            },
        )
        self.login_as(user=other_user)

        # accessing foreign files should not work
        response = self.client.get(f"{url}?id={download_id}")
        assert response.status_code == 404

    def test_dsyms_requests(self) -> None:
        response = self._upload_proguard(self.url, PROGUARD_UUID)
        assert response.status_code == 201, response.content
        assert len(response.data) == 1

        response = self.client.get(self.url)
        assert response.status_code == 200, response.content

        (dsym,) = response.data
        assert dsym["cpuName"] == "any"
        assert dsym["headers"] == {"Content-Type": "text/x-proguard+plain"}
        assert dsym["objectName"] == "proguard-mapping"
        assert dsym["sha1"] == "e6d3c5185dac63eddfdc1a5edfffa32d46103b44"
        assert dsym["symbolType"] == "proguard"
        assert dsym["uuid"] == "6dc7fdb0-d2fb-4c8e-9d6b-bb1aa98929b1"
        download_id = dsym["id"]

        # Download as a user with sufficient role
        self.organization.update_option("sentry:debug_files_role", "admin")
        response = self.client.get(self.url + "?id=" + download_id)
        assert response.status_code == 200, response.content
        assert (
            response.get("Content-Disposition")
            == 'attachment; filename="' + PROGUARD_UUID + '.txt"'
        )
        assert response.get("Content-Length") == str(len(PROGUARD_SOURCE))
        assert response.get("Content-Type") == "application/octet-stream"
        assert PROGUARD_SOURCE == close_streaming_response(response)

        # Download as a superuser
        superuser = self.create_user(is_superuser=True)
        self.login_as(user=superuser, superuser=True)
        response = self.client.get(self.url + "?id=" + download_id)
        assert response.get("Content-Type") == "application/octet-stream"
        close_streaming_response(response)

        # Download as a user without sufficient role
        self.organization.update_option("sentry:debug_files_role", "owner")
        member_user = self.create_user("bar@localhost")
        self.create_member(user=member_user, organization=self.organization, role="member")
        self.login_as(user=member_user)
        response = self.client.get(self.url + "?id=" + download_id)
        assert response.status_code == 403, response.content

        # Download as a user with no permissions
        user_no_permission = self.create_user("baz@localhost", username="baz")
        self.login_as(user=user_no_permission)
        response = self.client.get(self.url + "?id=" + download_id)
        assert response.status_code == 403, response.content

        # Try to delete with no permissions
        response = self.client.delete(self.url + "?id=" + download_id)
        assert response.status_code == 403, response.content

        # Login again with permissions
        self.login_as(user=self.user)

        response = self.client.delete(self.url + "?id=888")
        assert response.status_code == 404, response.content
        assert ProjectDebugFile.objects.count() == 1

        response = self.client.delete(self.url + "?id=" + download_id)
        assert response.status_code == 204, response.content
        assert ProjectDebugFile.objects.count() == 0

    def test_dsyms_as_team_admin(self) -> None:
        response = self._upload_proguard(self.url, PROGUARD_UUID)
        assert response.status_code == 201
        assert len(response.data) == 1

        response = self.client.post(
            self.url,
            {
                "checksums": ["e6d3c5185dac63eddfdc1a5edfffa32d46103b44"],
                "platform": "android",
                "name": "MyApp",
                "appId": "com.example.myapp",
                "version": "1.0",
                "build": "1",
            },
            format="json",
        )

        response = self.client.get(self.url)
        download_id = response.data[0]["id"]

        assert response.status_code == 200

        team_admin = self.create_user()
        team_admin_without_access = self.create_user()

        self.create_member(
            user=team_admin,
            organization=self.organization,
            role="member",
        )
        self.create_member(
            user=team_admin_without_access,
            organization=self.organization,
            role="member",
        )
        self.create_team_membership(user=team_admin, team=self.team, role="admin")
        self.create_team_membership(
            user=team_admin_without_access, team=self.create_team(), role="admin"
        )

        self.login_as(team_admin_without_access)
        # Team admin without project access can't download
        response = self.client.get(self.url + "?id=" + download_id)
        assert response.status_code == 403, response.content

        # Team admin without project access can't delete
        response = self.client.delete(self.url + "?id=" + download_id)
        assert response.status_code == 404, response.content
        assert ProjectDebugFile.objects.count() == 1

        self.login_as(team_admin)
        # Team admin with project access can download
        response = self.client.get(self.url + "?id=" + download_id)
        assert response.status_code == 200, response.content
        assert response.get("Content-Type") == "application/octet-stream"
        close_streaming_response(response)

        # Team admin with project access can delete
        response = self.client.delete(self.url + "?id=" + download_id)
        assert response.status_code == 204, response.content
        assert ProjectDebugFile.objects.count() == 0


class AssociateDebugFilesTest(DebugFilesTestCases):
    def setUp(self) -> None:
        super().setUp()
        self.associate_url = reverse(
            "sentry-api-0-associate-dsym-files",
            kwargs={
                "organization_id_or_slug": self.organization.slug,
                "project_id_or_slug": self.project.slug,
            },
        )

    def test_associate_proguard_dsym(self) -> None:
        response = self._upload_proguard(self.url, PROGUARD_UUID)
        assert response.status_code == 201, response.content
        assert len(response.data) == 1
        assert response.data[0]["headers"] == {"Content-Type": "text/x-proguard+plain"}
        assert response.data[0]["sha1"] == "e6d3c5185dac63eddfdc1a5edfffa32d46103b44"
        assert response.data[0]["uuid"] == PROGUARD_UUID
        assert response.data[0]["objectName"] == "proguard-mapping"
        assert response.data[0]["cpuName"] == "any"
        assert response.data[0]["symbolType"] == "proguard"

        response = self.client.post(
            self.associate_url,
            {
                "checksums": ["e6d3c5185dac63eddfdc1a5edfffa32d46103b44"],
                "platform": "android",
                "name": "MyApp",
                "appId": "com.example.myapp",
                "version": "1.0",
                "build": "1",
            },
            format="json",
        )

        assert response.status_code == 200, response.content
        assert "associatedDsymFiles" in response.data
        assert response.data["associatedDsymFiles"] == []

    def test_associate_proguard_dsym_no_build(self) -> None:
        response = self._upload_proguard(self.url, PROGUARD_UUID)
        assert response.status_code == 201, response.content
        assert len(response.data) == 1
        assert response.data[0]["headers"] == {"Content-Type": "text/x-proguard+plain"}
        assert response.data[0]["sha1"] == "e6d3c5185dac63eddfdc1a5edfffa32d46103b44"
        assert response.data[0]["uuid"] == PROGUARD_UUID
        assert response.data[0]["objectName"] == "proguard-mapping"
        assert response.data[0]["cpuName"] == "any"
        assert response.data[0]["symbolType"] == "proguard"

        response = self.client.post(
            self.associate_url,
            {
                "checksums": ["e6d3c5185dac63eddfdc1a5edfffa32d46103b44"],
                "platform": "android",
                "name": "MyApp",
                "appId": "com.example.myapp",
                "version": "1.0",
            },
            format="json",
        )

        assert response.status_code == 200, response.content
        assert "associatedDsymFiles" in response.data
        assert response.data["associatedDsymFiles"] == []


class SourceMapsEndpointTest(APITestCase):
    def setUp(self) -> None:
        self.url = reverse(
            "sentry-api-0-source-maps",
            kwargs={
                "organization_id_or_slug": self.organization.slug,
                "project_id_or_slug": self.project.slug,
            },
        )
        self.login_as(user=self.user)

    def test_source_maps(self) -> None:
        release = Release.objects.create(organization_id=self.project.organization_id, version="1")
        release2 = Release.objects.create(organization_id=self.project.organization_id, version="2")
        release3 = Release.objects.create(organization_id=self.project.organization_id, version="3")
        release.add_project(self.project)
        release2.add_project(self.project)
        release3.add_project(self.project)

        ReleaseFile.objects.create(
            organization_id=self.project.organization_id,
            release_id=release.id,
            file=File.objects.create(name="application.js", type="release.file"),
            name="http://example.com/application.js",
        )
        ReleaseFile.objects.create(
            organization_id=self.project.organization_id,
            release_id=release.id,
            file=File.objects.create(name="application2.js", type="release.file"),
            name="http://example.com/application2.js",
        )
        ReleaseFile.objects.create(
            organization_id=self.project.organization_id,
            release_id=release2.id,
            file=File.objects.create(name="application3.js", type="release.file"),
            name="http://example.com/application2.js",
            artifact_count=0,
        )

        response = self.client.get(self.url)

        assert response.status_code == 200, response.content
        assert len(response.data) == 3
        # No ReleaseFile.
        assert response.data[0]["name"] == str(release3.version)
        assert response.data[0]["fileCount"] == -1
        # ReleaseFile with zero artifacts.
        assert response.data[1]["name"] == str(release2.version)
        assert response.data[1]["fileCount"] == 0
        # ReleaseFile with multiple artifacts.
        assert response.data[2]["name"] == str(release.version)
        assert response.data[2]["fileCount"] == 2

    def test_source_maps_sorting(self) -> None:
        release = Release.objects.create(organization_id=self.project.organization_id, version="1")
        release2 = Release.objects.create(organization_id=self.project.organization_id, version="2")
        release.add_project(self.project)
        release2.add_project(self.project)

        ReleaseFile.objects.create(
            organization_id=self.project.organization_id,
            release_id=release.id,
            file=File.objects.create(name="application.js", type="release.file"),
            name="http://example.com/application.js",
        )
        ReleaseFile.objects.create(
            organization_id=self.project.organization_id,
            release_id=release.id,
            file=File.objects.create(name="application2.js", type="release.file"),
            name="http://example.com/application2.js",
        )

        release_ids = [release.id, release2.id]

        response = self.client.get(self.url + "?sortBy=date_added")
        assert response.status_code == 200, response.content
        assert list(map(lambda value: value["id"], response.data)) == release_ids

        response = self.client.get(self.url + "?sortBy=-date_added")
        assert response.status_code == 200, response.content
        assert list(map(lambda value: value["id"], response.data)) == release_ids[::-1]

        response = self.client.get(self.url + "?sortBy=invalid")
        assert response.status_code == 400
        assert response.data["error"] == "You can either sort via 'date_added' or '-date_added'"

    def test_source_maps_delete_archive(self) -> None:
        release = Release.objects.create(
            organization_id=self.project.organization_id, version="1", id=1
        )
        release.add_project(self.project)

        ReleaseFile.objects.create(
            organization_id=self.project.organization_id,
            release_id=release.id,
            file=File.objects.create(name="application.js", type="release.file"),
            name="http://example.com/application.js",
        )

        response = self.client.delete(self.url + "?name=1")
        assert response.status_code == 204
        assert not ReleaseFile.objects.filter(release_id=release.id).exists()

    def test_source_maps_release_archive(self) -> None:
        release = Release.objects.create(organization_id=self.project.organization_id, version="1")
        release.add_project(self.project)

        self.create_release_archive(release=release.version)

        response = self.client.get(self.url)

        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert response.data[0]["name"] == str(release.version)
        assert response.data[0]["fileCount"] == 2
