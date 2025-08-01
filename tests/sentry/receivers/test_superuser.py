from sentry.api.endpoints.auth_index import PREFILLED_SU_MODAL_KEY
from sentry.auth.superuser import is_active_superuser
from sentry.receivers.superuser import disable_superuser, enable_superuser
from sentry.testutils.cases import TestCase


class SuperuserReceiverTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.superuser = self.create_user(is_superuser=True)
        self.non_superuser = self.create_user(is_superuser=False)

        self.superuser_request = self.make_request(user=self.superuser)
        self.non_superuser_request = self.make_request(user=self.non_superuser)

    def test_enable_superuser_when_self_hosted__superuser(self) -> None:
        with self.settings(
            SENTRY_SELF_HOSTED=True, VALIDATE_SUPERUSER_ACCESS_CATEGORY_AND_REASON=False
        ):
            enable_superuser(request=self.superuser_request, user=self.superuser)
            assert is_active_superuser(self.superuser_request)

    def test_enable_superuser_when_flag_on__superuser(self) -> None:
        with self.settings(
            SENTRY_SELF_HOSTED=False,
            VALIDATE_SUPERUSER_ACCESS_CATEGORY_AND_REASON=False,
            ENABLE_SU_UPON_LOGIN_FOR_LOCAL_DEV=True,
        ):
            enable_superuser(request=self.superuser_request, user=self.superuser)
            assert is_active_superuser(self.superuser_request)

    def test_enable_superuser_saas__superuser(self) -> None:
        with self.settings(
            SENTRY_SELF_HOSTED=False,
        ):
            enable_superuser(request=self.superuser_request, user=self.superuser)
            assert not is_active_superuser(self.superuser_request)

    def test_enable_superuser_when_self_hosted_non__superuser(self) -> None:
        with self.settings(
            SENTRY_SELF_HOSTED=True, VALIDATE_SUPERUSER_ACCESS_CATEGORY_AND_REASON=False
        ):
            enable_superuser(request=self.non_superuser_request, user=self.non_superuser)
            assert not is_active_superuser(self.non_superuser_request)

    def test_enable_superuser_when_flag_on_non__superuser(self) -> None:
        with self.settings(
            SENTRY_SELF_HOSTED=False,
            VALIDATE_SUPERUSER_ACCESS_CATEGORY_AND_REASON=False,
            ENABLE_SU_UPON_LOGIN_FOR_LOCAL_DEV=True,
        ):
            enable_superuser(request=self.non_superuser_request, user=self.non_superuser)
            assert not is_active_superuser(self.non_superuser_request)

    def test_enable_superuser_when_session_has_prefill_key_superuser(self) -> None:

        self.superuser_request.session[PREFILLED_SU_MODAL_KEY] = {
            "superuserAccessCategory": "for_unit_test",
            "superuserReason": "Edit organization settings",
            "isSuperuserModal": True,
        }

        enable_superuser(request=self.superuser_request, user=self.superuser)
        assert is_active_superuser(self.superuser_request)

    def test_enable_superuser_when_session_has_prefill_key_non_superuser(self) -> None:

        self.superuser_request.session[PREFILLED_SU_MODAL_KEY] = {
            "superuserAccessCategory": "for_unit_test",
            "superuserReason": "Edit organization settings",
            "isSuperuserModal": True,
        }

        enable_superuser(request=self.non_superuser_request, user=self.non_superuser)
        assert not is_active_superuser(self.non_superuser_request)

    def test_enable_superuser_saas_non__superuser(self) -> None:
        with self.settings(
            SENTRY_SELF_HOSTED=False,
        ):
            enable_superuser(request=self.non_superuser_request, user=self.non_superuser)
            assert not is_active_superuser(self.superuser_request)

    def test_disable_superuser_active__superuser(self) -> None:
        enable_superuser(request=self.superuser_request, user=self.superuser)
        assert is_active_superuser(self.superuser_request)

        disable_superuser(request=self.superuser_request, user=self.superuser)
        assert not is_active_superuser(self.superuser_request)
