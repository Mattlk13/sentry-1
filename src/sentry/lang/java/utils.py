from __future__ import annotations

from typing import Any

import orjson
import sentry_sdk

from sentry.attachments import CachedAttachment, attachment_cache
from sentry.ingest.consumer.processors import CACHE_TIMEOUT
from sentry.models.project import Project
from sentry.stacktraces.processing import StacktraceInfo
from sentry.utils.cache import cache_key_for_event
from sentry.utils.safe import get_path

# Platform values that should mark an event
# or frame as being Java for the purposes
# of symbolication.
#
# Strictly speaking, this should probably include
# "android" too—at least we use it in profiling.
JAVA_PLATFORMS = ("java",)


def is_valid_proguard_image(image):
    return bool(image) and image.get("type") == "proguard" and image.get("uuid") is not None


def is_valid_jvm_image(image):
    return bool(image) and image.get("type") == "jvm" and image.get("debug_id") is not None


def has_proguard_file(data):
    """
    Checks whether an event contains a proguard file
    """
    images = get_path(data, "debug_meta", "images", filter=True, default=())
    return any(map(is_valid_proguard_image, images))


def get_proguard_images(event: dict[str, Any]) -> set[str]:
    images = set()
    for image in get_path(
        event, "debug_meta", "images", filter=is_valid_proguard_image, default=()
    ):
        images.add(str(image["uuid"]).lower())
    return images


def get_jvm_images(event: dict[str, Any]) -> set[str]:
    images = set()
    for image in get_path(event, "debug_meta", "images", filter=is_valid_jvm_image, default=()):
        images.add(str(image["debug_id"]).lower())
    return images


@sentry_sdk.trace
def deobfuscation_template(data, map_type, deobfuscation_fn):
    """
    Template for operations involved in deobfuscating view hierarchies.

    The provided deobfuscation function is expected to modify the view hierarchy dict in-place.
    """
    project = Project.objects.get_from_cache(id=data["project"])

    cache_key = cache_key_for_event(data)
    attachments = [*attachment_cache.get(cache_key)]

    if not any(attachment.type == "event.view_hierarchy" for attachment in attachments):
        return

    new_attachments = []
    for attachment in attachments:
        if attachment.type == "event.view_hierarchy":
            view_hierarchy = orjson.loads(attachment_cache.get_data(attachment))
            deobfuscation_fn(data, project, view_hierarchy)

            # Reupload to cache as a unchunked data
            new_attachments.append(
                CachedAttachment(
                    type=attachment.type,
                    id=attachment.id,
                    name=attachment.name,
                    content_type=attachment.content_type,
                    data=orjson.dumps(view_hierarchy),
                    chunks=None,
                )
            )
        else:
            new_attachments.append(attachment)

    attachment_cache.set(cache_key, attachments=new_attachments, timeout=CACHE_TIMEOUT)


def is_jvm_event(data: Any, stacktraces: list[StacktraceInfo]) -> bool:
    """Returns whether `data` is a JVM event, based on its platform,
    the supplied stacktraces, and its images."""

    platform = data.get("platform")

    if platform in JAVA_PLATFORMS:
        return True

    for stacktrace in stacktraces:
        # The platforms of a stacktrace are exactly the platforms of its frames
        # so this is tantamount to checking if any frame has a Java platform.
        if any(x in JAVA_PLATFORMS for x in stacktrace.platforms):
            return True

    # check if there are any JVM or Proguard images
    # we *do* hit this code path, likely for events that don't have platform
    # `"java"` but contain Java view hierarchies.
    images = get_path(
        data,
        "debug_meta",
        "images",
        filter=lambda x: is_valid_jvm_image(x) or is_valid_proguard_image(x),
        default=(),
    )

    if images:
        return True

    return False
