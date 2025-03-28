import dataclasses
from collections import defaultdict
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import grpc
import pytest
from django.test import override_settings
from google.protobuf.message import Message
from sentry_protos.taskbroker.v1.taskbroker_pb2 import (
    TASK_ACTIVATION_STATUS_COMPLETE,
    TASK_ACTIVATION_STATUS_RETRY,
    FetchNextTask,
    GetTaskResponse,
    SetTaskStatusResponse,
    TaskActivation,
)

from sentry.taskworker.client import TaskworkerClient
from sentry.testutils.pytest.fixtures import django_db_all


@dataclasses.dataclass
class MockServiceCall:
    response: Any
    metadata: tuple[tuple[str, str | bytes], ...] | None = None


class MockServiceMethod:
    """Stub for grpc service methods"""

    def __init__(
        self,
        path: str,
        responses: list[Any],
        request_serializer: Callable,
        response_deserializer: Callable,
    ):
        self.path = path
        self.request_serializer = request_serializer
        self.response_deserializer = response_deserializer
        self.responses = responses

    def __call__(self, *args, **kwargs):
        """Capture calls and use registered mocks"""
        # move the head to the tail
        res = self.responses[0]
        tail = self.responses[1:]
        self.responses = tail + [res]

        if isinstance(res.response, Exception):
            raise res.response
        return res.response

    def with_call(self, *args, **kwargs):
        res = self.responses[0]
        if res.metadata:
            assert res.metadata == kwargs.get("metadata"), "Metadata mismatch"
        if isinstance(res.response, Exception):
            raise res.response
        return (res.response, None)


class MockChannel:
    def __init__(self):
        self._responses = defaultdict(list)

    def unary_unary(
        self,
        path: str,
        request_serializer: Callable,
        response_deserializer: Callable,
        *args,
        **kwargs,
    ):
        return MockServiceMethod(
            path, self._responses.get(path, []), request_serializer, response_deserializer
        )

    def add_response(
        self,
        path: str,
        resp: Message | Exception,
        metadata: tuple[tuple[str, str | bytes], ...] | None = None,
    ):
        self._responses[path].append(MockServiceCall(response=resp, metadata=metadata))


class MockGrpcError(grpc.RpcError):
    """Grpc error are elusive and this mock simulates the interface in mypy stubs"""

    def __init__(self, code, message):
        self._code = code
        self._message = message

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._message

    def result(self):
        raise self


@django_db_all
def test_get_task_ok():
    channel = MockChannel()
    channel.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/GetTask",
        GetTaskResponse(
            task=TaskActivation(
                id="abc123",
                namespace="testing",
                taskname="do_thing",
                parameters="",
                headers={},
                processing_deadline_duration=10,
            )
        ),
    )
    with patch("sentry.taskworker.client.grpc.insecure_channel") as mock_channel:
        mock_channel.return_value = channel
        client = TaskworkerClient("localhost:50051", 1)
        result = client.get_task()

        assert result
        assert result.id
        assert result.namespace == "testing"


@django_db_all
@override_settings(TASKWORKER_SHARED_SECRET="a long secret value")
def test_get_task_with_interceptor():
    channel = MockChannel()
    channel.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/GetTask",
        GetTaskResponse(
            task=TaskActivation(
                id="abc123",
                namespace="testing",
                taskname="do_thing",
                parameters="",
                headers={},
                processing_deadline_duration=10,
            )
        ),
        metadata=(
            (
                "sentry-signature",
                "3202702605c1b65055c28e7c78a5835e760830cff3e9f995eb7ad5f837130b1f",
            ),
        ),
    )
    with patch("sentry.taskworker.client.grpc.insecure_channel") as mock_channel:
        mock_channel.return_value = channel
        client = TaskworkerClient("localhost:50051", 1)
        result = client.get_task()

        assert result
        assert result.id
        assert result.namespace == "testing"


@django_db_all
def test_get_task_with_namespace():
    channel = MockChannel()
    channel.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/GetTask",
        GetTaskResponse(
            task=TaskActivation(
                id="abc123",
                namespace="testing",
                taskname="do_thing",
                parameters="",
                headers={},
                processing_deadline_duration=10,
            )
        ),
    )
    with patch("sentry.taskworker.client.grpc.insecure_channel") as mock_channel:
        mock_channel.return_value = channel
        client = TaskworkerClient("localhost:50051", 1)
        result = client.get_task(namespace="testing")

        assert result
        assert result.id
        assert result.namespace == "testing"


@django_db_all
def test_get_task_not_found():
    channel = MockChannel()
    channel.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/GetTask",
        MockGrpcError(grpc.StatusCode.NOT_FOUND, "no pending task found"),
    )
    with patch("sentry.taskworker.client.grpc.insecure_channel") as mock_channel:
        mock_channel.return_value = channel
        client = TaskworkerClient("localhost:50051", 1)
        result = client.get_task()

        assert result is None


@django_db_all
def test_get_task_failure():
    channel = MockChannel()
    channel.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/GetTask",
        MockGrpcError(grpc.StatusCode.INTERNAL, "something bad"),
    )
    with patch("sentry.taskworker.client.grpc.insecure_channel") as mock_channel:
        mock_channel.return_value = channel
        client = TaskworkerClient("localhost:50051", 1)
        with pytest.raises(grpc.RpcError):
            client.get_task()


@django_db_all
def test_update_task_ok_with_next():
    channel = MockChannel()
    channel.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/SetTaskStatus",
        SetTaskStatusResponse(
            task=TaskActivation(
                id="abc123",
                namespace="testing",
                taskname="do_thing",
                parameters="",
                headers={},
                processing_deadline_duration=10,
            )
        ),
    )
    with patch("sentry.taskworker.client.grpc.insecure_channel") as mock_channel:
        mock_channel.return_value = channel
        client = TaskworkerClient("localhost:50051", 1)
        client._task_id_to_host = {"abc123": "localhost-0:50051"}
        assert set(client._host_to_stubs.keys()) == {"localhost-0:50051"}
        result = client.update_task(
            "abc123", TASK_ACTIVATION_STATUS_RETRY, FetchNextTask(namespace=None)
        )
        assert result
        assert result.id == "abc123"


@django_db_all
def test_update_task_ok_with_next_namespace():
    channel = MockChannel()
    channel.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/SetTaskStatus",
        SetTaskStatusResponse(
            task=TaskActivation(
                id="abc123",
                namespace="testing",
                taskname="do_thing",
                parameters="",
                headers={},
                processing_deadline_duration=10,
            )
        ),
    )
    with patch("sentry.taskworker.client.grpc.insecure_channel") as mock_channel:
        mock_channel.return_value = channel
        client = TaskworkerClient("localhost:50051", 1)
        client._task_id_to_host = {"abc123": "localhost-0:50051"}
        result = client.update_task(
            "abc123", TASK_ACTIVATION_STATUS_RETRY, FetchNextTask(namespace="testing")
        )
        assert result
        assert result.id == "abc123"
        assert result.namespace == "testing"


@django_db_all
def test_update_task_ok_no_next():
    channel = MockChannel()
    channel.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/SetTaskStatus", SetTaskStatusResponse()
    )
    with patch("sentry.taskworker.client.grpc.insecure_channel") as mock_channel:
        mock_channel.return_value = channel
        client = TaskworkerClient("localhost:50051", 1)
        result = client.update_task(
            "abc123", TASK_ACTIVATION_STATUS_RETRY, FetchNextTask(namespace=None)
        )
        assert result is None


@django_db_all
def test_update_task_not_found():
    channel = MockChannel()
    channel.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/SetTaskStatus",
        MockGrpcError(grpc.StatusCode.NOT_FOUND, "no pending tasks found"),
    )
    with patch("sentry.taskworker.client.grpc.insecure_channel") as mock_channel:
        mock_channel.return_value = channel
        client = TaskworkerClient("localhost:50051", 1)
        client._task_id_to_host = {"abc123": "localhost-0:50051"}
        result = client.update_task(
            "abc123", TASK_ACTIVATION_STATUS_RETRY, FetchNextTask(namespace=None)
        )
        assert result is None


@django_db_all
def test_client_loadbalance():
    channel_0 = MockChannel()
    channel_0.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/GetTask",
        GetTaskResponse(
            task=TaskActivation(
                id="0",
                namespace="testing",
                taskname="do_thing",
                parameters="",
                headers={},
                processing_deadline_duration=10,
            )
        ),
    )
    channel_0.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/SetTaskStatus",
        SetTaskStatusResponse(task=None),
    )
    channel_1 = MockChannel()
    channel_1.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/GetTask",
        GetTaskResponse(
            task=TaskActivation(
                id="1",
                namespace="testing",
                taskname="do_thing",
                parameters="",
                headers={},
                processing_deadline_duration=10,
            )
        ),
    )
    channel_1.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/SetTaskStatus",
        SetTaskStatusResponse(task=None),
    )
    channel_2 = MockChannel()
    channel_2.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/GetTask",
        GetTaskResponse(
            task=TaskActivation(
                id="2",
                namespace="testing",
                taskname="do_thing",
                parameters="",
                headers={},
                processing_deadline_duration=10,
            )
        ),
    )
    channel_2.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/SetTaskStatus",
        SetTaskStatusResponse(task=None),
    )
    channel_3 = MockChannel()
    channel_3.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/GetTask",
        GetTaskResponse(
            task=TaskActivation(
                id="3",
                namespace="testing",
                taskname="do_thing",
                parameters="",
                headers={},
                processing_deadline_duration=10,
            )
        ),
    )
    channel_3.add_response(
        "/sentry_protos.taskbroker.v1.ConsumerService/SetTaskStatus",
        SetTaskStatusResponse(task=None),
    )
    with patch("sentry.taskworker.client.grpc.insecure_channel") as mock_channel:
        mock_channel.side_effect = [channel_0, channel_1, channel_2, channel_3]
        with patch("sentry.taskworker.client.random.choice") as mock_randchoice:
            mock_randchoice.side_effect = [
                "localhost-0:50051",
                "localhost-1:50051",
                "localhost-2:50051",
                "localhost-3:50051",
            ]
            client = TaskworkerClient(
                "localhost:50051", num_brokers=4, max_tasks_before_rebalance=1
            )

            task_0 = client.get_task()
            assert task_0 is not None and task_0.id == "0"
            task_1 = client.get_task()
            assert task_1 is not None and task_1.id == "1"
            task_2 = client.get_task()
            assert task_2 is not None and task_2.id == "2"
            task_3 = client.get_task()
            assert task_3 is not None and task_3.id == "3"

            assert client._task_id_to_host == {
                "0": "localhost-0:50051",
                "1": "localhost-1:50051",
                "2": "localhost-2:50051",
                "3": "localhost-3:50051",
            }

            client.update_task(task_0.id, TASK_ACTIVATION_STATUS_COMPLETE, None)
            assert client._task_id_to_host == {
                "1": "localhost-1:50051",
                "2": "localhost-2:50051",
                "3": "localhost-3:50051",
            }

            client.update_task(task_1.id, TASK_ACTIVATION_STATUS_COMPLETE, None)
            assert client._task_id_to_host == {
                "2": "localhost-2:50051",
                "3": "localhost-3:50051",
            }

            client.update_task(task_2.id, TASK_ACTIVATION_STATUS_COMPLETE, None)
            assert client._task_id_to_host == {
                "3": "localhost-3:50051",
            }

            client.update_task(task_3.id, TASK_ACTIVATION_STATUS_COMPLETE, None)
            assert client._task_id_to_host == {}
