from base64 import b64encode

from sentry.models.avatars.organization_avatar import OrganizationAvatar
from sentry.testutils.cases import APITestCase


class OrganizationAvatarTestBase(APITestCase):
    endpoint = "sentry-api-0-organization-avatar"

    def setUp(self) -> None:
        super().setUp()
        self.login_as(self.user)


class OrganizationAvatarTest(OrganizationAvatarTestBase):
    def test_get(self) -> None:
        response = self.get_success_response(self.organization.slug)
        assert response.data["id"] == str(self.organization.id)
        assert response.data["avatar"]["avatarType"] == "letter_avatar"
        assert response.data["avatar"]["avatarUuid"] is None
        assert response.data["avatar"]["avatarUrl"] is None


class OrganizationAvatarPutTest(OrganizationAvatarTestBase):
    method = "put"

    def test_upload(self) -> None:
        data = {"avatar_type": "upload", "avatar_photo": b64encode(self.load_fixture("avatar.jpg"))}
        self.get_success_response(self.organization.slug, **data)

        avatar = OrganizationAvatar.objects.get(organization=self.organization)
        assert avatar.get_avatar_type_display() == "upload"
        assert avatar.file_id

    def test_put_bad(self) -> None:
        OrganizationAvatar.objects.create(organization=self.organization)

        self.get_error_response(self.organization.slug, avatar_type="upload", status_code=400)

        avatar = OrganizationAvatar.objects.get(organization=self.organization)
        assert avatar.get_avatar_type_display() == "letter_avatar"

        self.get_error_response(self.organization.slug, avatar_type="foo", status_code=400)

        assert avatar.get_avatar_type_display() == "letter_avatar"

    def test_put_forbidden(self) -> None:
        org = self.create_organization()
        self.get_error_response(org.slug, avatar_type="letter_avatar", status_code=403)
