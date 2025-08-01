from rest_framework import status

from sentry.testutils.asserts import assert_status_code
from sentry.testutils.cases import APITestCase
from sentry.testutils.silo import all_silo_test


@all_silo_test
class CatchallTestCase(APITestCase):
    def setUp(self) -> None:
        super().setUp()

    def test_simple(self) -> None:
        response = self.client.get("/api/0/bad_url/")
        assert_status_code(response, status.HTTP_404_NOT_FOUND)

        assert response.content == b""

    def test_trailing_slash_help(self) -> None:
        response = self.client.get("/api/0/bad_url")
        assert_status_code(response, status.HTTP_404_NOT_FOUND)

        assert (
            b"Route not found, did you forget a trailing slash?\n\n"
            + b"try: /api/0/bad_url/\n"
            + b"                   ^\n"
            in response.content
        )

    def test_trailing_slash_help_json(self) -> None:
        response = self.client.get("/api/0/bad_url", content_type="application/json")
        assert_status_code(response, status.HTTP_404_NOT_FOUND)

        assert response.json() == {
            "info": "Route not found, did you forget a trailing slash? try: /api/0/bad_url/"
        }

    def test_missing_route_response_includes_cors(self) -> None:
        res = self.client.get("/api/0/bad_url/")
        assert res.status_code == 404
        assert "x-frame-options" in res
        assert "access-control-allow-methods" in res
        assert "access-control-allow-headers" in res
        assert "access-control-expose-headers" in res
        assert "access-control-allow-origin" in res
