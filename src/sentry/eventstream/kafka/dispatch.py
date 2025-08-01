import logging
import random
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from typing import Any

from arroyo.backends.kafka.consumer import KafkaPayload
from arroyo.types import Message

from sentry import options
from sentry.eventstream.base import GroupStates
from sentry.eventstream.kafka.protocol import (
    get_task_kwargs_for_message,
    get_task_kwargs_for_message_from_headers,
)
from sentry.post_process_forwarder.post_process_forwarder import PostProcessForwarderStrategyFactory
from sentry.tasks.post_process import post_process_group
from sentry.utils import metrics
from sentry.utils.cache import cache_key_for_event

_DURATION_METRIC = "eventstream.duration"

logger = logging.getLogger(__name__)


@contextmanager
def _sampled_eventstream_timer(instance: str) -> Generator[None]:
    record_metric = random.random() < 0.1
    if record_metric is True:
        with metrics.timer(_DURATION_METRIC, instance=instance):
            yield
    else:
        yield


def dispatch_post_process_group_task(
    event_id: str,
    project_id: int,
    group_id: int | None,
    is_new: bool,
    is_regression: bool | None,
    is_new_group_environment: bool,
    primary_hash: str | None,
    queue: str,
    skip_consume: bool = False,
    group_states: GroupStates | None = None,
    occurrence_id: str | None = None,
    eventstream_type: str | None = None,
) -> None:
    if skip_consume:
        logger.info("post_process.skip.raw_event", extra={"event_id": event_id})
    else:
        cache_key = cache_key_for_event({"project": project_id, "event_id": event_id})
        post_process_group.apply_async(
            kwargs={
                "is_new": is_new,
                "is_regression": is_regression,
                "is_new_group_environment": is_new_group_environment,
                "primary_hash": primary_hash,
                "cache_key": cache_key,
                "group_id": group_id,
                "group_states": group_states,
                "occurrence_id": occurrence_id,
                "project_id": project_id,
                "eventstream_type": eventstream_type,
            },
            queue=queue,
        )


def _get_task_kwargs(message: Message[KafkaPayload]) -> Mapping[str, Any] | None:
    use_kafka_headers = options.get("post-process-forwarder:kafka-headers")

    if use_kafka_headers:
        try:
            with _sampled_eventstream_timer(instance="get_task_kwargs_for_message_from_headers"):
                return get_task_kwargs_for_message_from_headers(message.payload.headers)
        except Exception as error:
            logger.warning("Could not forward message: %s", error, exc_info=True)
            with metrics.timer(_DURATION_METRIC, instance="get_task_kwargs_for_message"):
                return get_task_kwargs_for_message(message.payload.value)
    else:
        with metrics.timer(_DURATION_METRIC, instance="get_task_kwargs_for_message"):
            return get_task_kwargs_for_message(message.payload.value)


def _get_task_kwargs_and_dispatch(
    message: Message[KafkaPayload], eventstream_type: str | None = None
) -> None:
    task_kwargs = _get_task_kwargs(message)
    if not task_kwargs:
        return None

    dispatch_post_process_group_task(**task_kwargs, eventstream_type=eventstream_type)


class EventPostProcessForwarderStrategyFactory(PostProcessForwarderStrategyFactory):
    @staticmethod
    def _dispatch_function(
        message: Message[KafkaPayload], eventstream_type: str | None = None
    ) -> None:
        with _sampled_eventstream_timer(instance="_get_task_kwargs_and_dispatch"):
            return _get_task_kwargs_and_dispatch(message, eventstream_type)
