from unittest.mock import patch

import httpx
from httpx import Response

from sentry.llm.providers.openai import get_openai_client
from sentry.llm.usecases import LLMUseCase, complete_prompt


def test_complete_prompt(set_sentry_option) -> None:
    with (
        set_sentry_option(
            "llm.provider.options",
            {"openai": {"models": ["gpt-4-turbo-1.0"], "options": {"api_key": "fake_api_key"}}},
        ),
        set_sentry_option(
            "llm.usecases.options",
            {"example": {"provider": "openai", "options": {"model": "gpt-4-turbo-1.0"}}},
        ),
        patch("httpx.Client.send") as mock_send,
    ):
        # Prepare the mock response object
        mock_response = Response(
            status_code=200,
            json={"choices": [{"message": {"content": ""}}]},
        )
        # Create a request instance to associate with the response
        mock_request = httpx.Request(method="POST", url="https://api.openai.com")
        mock_response._request = mock_request
        mock_send.return_value = mock_response

        # Clear this function's cache to prevent interference from patching in other tests
        get_openai_client.cache_clear()

        res = complete_prompt(
            usecase=LLMUseCase.EXAMPLE,
            prompt="prompt here",
            message="message here",
            temperature=0.0,
            max_output_tokens=1024,
        )
    assert res == ""
