from __future__ import annotations

import mimetypes
import os
import posixpath
from collections.abc import Callable
from tempfile import SpooledTemporaryFile

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str, smart_str
from google.api_core.exceptions import GatewayTimeout, ServiceUnavailable
from google.auth.exceptions import RefreshError, TransportError
from google.cloud.exceptions import NotFound
from google.cloud.storage.blob import Blob
from google.cloud.storage.bucket import Bucket
from google.cloud.storage.client import Client
from google.resumable_media.common import DataCorruption
from requests.exceptions import RequestException

from sentry.net.http import TimeoutAdapter
from sentry.utils import metrics
from sentry.utils.retries import ConditionalRetryPolicy, sigmoid_delay

# how many times do we want to try if stuff goes wrong
GCS_RETRIES = 5
REPLAY_GCS_RETRIES = 125


# Which errors are eligible for retry.
GCS_RETRYABLE_ERRORS = (
    DataCorruption,
    TransportError,
    RefreshError,
    RequestException,
    ServiceUnavailable,
    GatewayTimeout,
)

# how long are we willing to wait?
GCS_TIMEOUT = 6.0


# _client cache is a 3-tuple of project_id, credentials, Client
# this is so if any information changes under it, it invalidates
# the cache. This scenario is possible since `options` are dynamic
_client: tuple[None, None, None] | tuple[int, object, Client] = None, None, None


def try_repeated(func):
    """
    Runs a function a few times ignoring errors we see from GCS
    due to what appears to be network issues.  This is a temporary workaround
    until we can find the root cause.
    """
    if hasattr(func, "__name__"):
        func_name = func.__name__
    elif hasattr(func, "func"):
        # Partials
        func_name = getattr(func.func, "__name__", "__unknown__")
    else:
        func_name = "__unknown__"

    metrics_key = "filestore.gcs.retry"
    metrics_tags = {"function": func_name}
    idx = 0
    while True:
        try:
            result = func()
            metrics_tags.update({"success": "1"})
            metrics.distribution(metrics_key, idx, tags=metrics_tags)
            return result
        except GCS_RETRYABLE_ERRORS as e:
            if idx >= GCS_RETRIES:
                metrics_tags.update({"success": "0", "exception_class": e.__class__.__name__})
                metrics.distribution(metrics_key, idx, tags=metrics_tags)
                raise
        idx += 1


def get_client(project_id, credentials):
    global _client
    if _client[2] is None or (project_id, credentials) != (_client[0], _client[1]):
        client = Client(project=project_id, credentials=credentials)
        session = client._http
        adapter = TimeoutAdapter(timeout=GCS_TIMEOUT)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _client = (project_id, credentials, client)
    return _client[2]


def clean_name(name):
    """
    Cleans the name so that Windows style paths work
    """
    # Normalize Windows style paths
    clean_name = posixpath.normpath(name).replace("\\", "/")

    # os.path.normpath() can strip trailing slashes so we implement
    # a workaround here.
    if name.endswith("/") and not clean_name.endswith("/"):
        # Add a trailing slash as it was stripped.
        clean_name = clean_name + "/"

    # Given an empty string, os.path.normpath() will return ., which we don't want
    if clean_name == ".":
        clean_name = ""

    return clean_name


def safe_join(base, *paths):
    """
    A version of django.utils._os.safe_join for S3 paths.
    Joins one or more path components to the base path component
    intelligently. Returns a normalized version of the final path.
    The final path must be located inside of the base path component
    (otherwise a ValueError is raised).
    Paths outside the base path indicate a possible security
    sensitive operation.
    """
    base_path = force_str(base)
    base_path = base_path.rstrip("/")
    paths = tuple(force_str(p) for p in paths)

    final_path = base_path + "/"
    for path in paths:
        _final_path = posixpath.normpath(posixpath.join(final_path, path))
        # posixpath.normpath() strips the trailing /. Add it back.
        if path.endswith("/") or _final_path + "/" == final_path:
            _final_path += "/"
        final_path = _final_path
    if final_path == base_path:
        final_path += "/"

    # Ensure final_path starts with base_path and that the next character after
    # the base path is /.
    base_path_len = len(base_path)
    if not final_path.startswith(base_path) or final_path[base_path_len] != "/":
        raise ValueError("the joined path is located outside of the base path" " component")

    return final_path.lstrip("/")


class FancyBlob(Blob):
    def __init__(self, download_url, *args, **kwargs):
        self.download_url = download_url
        super().__init__(*args, **kwargs)

    def _get_download_url(self, *args, **kwargs):
        # media_link is for public objects; we completely ignore it.
        download_url = f"{self.download_url}/download/storage/v1{self.path}?alt=media"
        if self.generation is not None:
            download_url += f"&generation={self.generation:d}"
        return download_url


class GoogleCloudFile(File):
    def __init__(self, name, mode, storage):
        self.name = name
        self.mime_type = mimetypes.guess_type(name)[0]
        self._mode = mode
        self._storage = storage
        # NOTE(mattrobenolt): This is the same change in behavior as in
        # the s3 backend. We're opting now to load the file
        # or metadata at this step. This means we won't actually
        # know a file doesn't exist until we try to read it.
        self.blob = FancyBlob(storage.download_url, self.name, storage.bucket)
        self._file = None
        self._is_dirty = False

    @property
    def size(self):
        return self.blob.size

    @property
    def file(self):
        def _try_download():
            assert self._file is not None
            self.blob.download_to_file(self._file)
            self._file.seek(0)

        if self._file is None:
            with metrics.timer("filestore.read", instance="gcs"):
                self._file = SpooledTemporaryFile(
                    max_size=self._storage.max_memory_size, suffix=".GSStorageFile", dir=None
                )
                if "r" in self._mode:
                    self._is_dirty = False
                    self._storage.try_get(_try_download)
        return self._file

    @file.setter
    def file(self, value):
        self._file = value

    def read(self, num_bytes=None):
        if "r" not in self._mode:
            raise AttributeError("File was not opened in read mode.")

        if num_bytes is None:
            num_bytes = -1

        return super().read(num_bytes)

    def write(self, content):
        if "w" not in self._mode:
            raise AttributeError("File was not opened in write mode.")
        self._is_dirty = True
        return super().write(force_bytes(content))

    def close(self):
        def _try_upload():
            self.file.seek(0)
            self.blob.upload_from_file(self.file, content_type=self.mime_type)

        if self._file is not None:
            if self._is_dirty:
                self._storage.try_set(_try_upload)
            self._file.close()
            self._file = None


class GoogleCloudStorage(Storage):
    def __init__(
        self,
        project_id=None,
        credentials=None,
        bucket_name=None,
        file_name_charset="utf-8",
        file_overwrite=True,
        download_url="https://www.googleapis.com",
        # The max amount of memory a returned file can take up before being
        # rolled over into a temporary file on disk. Default is 0: Do not roll over.
        max_memory_size=0,
    ):
        self.project_id = project_id
        self.credentials = credentials
        self.bucket_name = bucket_name
        self.file_name_charset = file_name_charset
        self.file_overwrite = file_overwrite
        self.download_url = download_url
        self.max_memory_size = max_memory_size

        self._bucket = None
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_client(self.project_id, self.credentials)
        return self._client

    @property
    def bucket(self):
        if self._bucket is None:
            self._bucket = Bucket(self.client, name=self.bucket_name)
        return self._bucket

    def _normalize_name(self, name):
        """
        Normalizes the name so that paths like /path/to/ignored/../something.txt
        and ./file.txt work.  Note that clean_name adds ./ to some paths so
        they need to be fixed here.
        """
        return safe_join("", name)

    def _encode_name(self, name):
        return smart_str(name, encoding=self.file_name_charset)

    def _open(self, name, mode="rb"):
        name = self._normalize_name(clean_name(name))
        return GoogleCloudFile(name, mode, self)

    def _save(self, name, content):
        def _try_upload():
            content.seek(0, os.SEEK_SET)
            file.blob.upload_from_file(content, size=content.size, content_type=file.mime_type)

        with metrics.timer("filestore.save", instance="gcs"):
            cleaned_name = clean_name(name)
            name = self._normalize_name(cleaned_name)

            content.name = cleaned_name
            encoded_name = self._encode_name(name)
            file = GoogleCloudFile(encoded_name, "w", self)
            self.try_set(_try_upload)
        return cleaned_name

    def delete(self, name):
        def _try_delete():
            normalized_name = self._normalize_name(clean_name(name))
            self.bucket.delete_blob(self._encode_name(normalized_name))

        try:
            self.try_del(_try_delete)
        except NotFound:
            pass

    def exists(self, name):
        if not name:  # root element aka the bucket
            try:
                self.bucket
                return True
            except ImproperlyConfigured:
                return False

        name = self._normalize_name(clean_name(name))
        return bool(self.bucket.get_blob(self._encode_name(name)))

    def listdir(self, name):
        name = self._normalize_name(clean_name(name))
        # for the bucket.list and logic below name needs to end in /
        # But for the root path "" we leave it as an empty string
        if name and not name.endswith("/"):
            name += "/"

        files_list = list(self.bucket.list_blobs(prefix=self._encode_name(name)))
        files = []
        dirs = set()

        base_parts = name.split("/")[:-1]
        for item in files_list:
            parts = item.name.split("/")
            parts = parts[len(base_parts) :]
            if len(parts) == 1 and parts[0]:
                # File
                files.append(parts[0])
            elif len(parts) > 1 and parts[0]:
                # Directory
                dirs.add(parts[0])
        return list(dirs), files

    def _get_blob(self, name):
        # Wrap google.cloud.storage's blob to raise if the file doesn't exist
        blob = self.bucket.get_blob(name)

        if blob is None:
            raise NotFound(f"File does not exist: {name}")

        return blob

    def size(self, name):
        name = self._normalize_name(clean_name(name))
        blob = self._get_blob(self._encode_name(name))
        return blob.size

    def modified_time(self, name):
        name = self._normalize_name(clean_name(name))
        blob = self._get_blob(self._encode_name(name))
        return timezone.make_naive(blob.updated)

    def get_modified_time(self, name):
        name = self._normalize_name(clean_name(name))
        blob = self._get_blob(self._encode_name(name))
        updated = blob.updated
        return updated if settings.USE_TZ else timezone.make_naive(updated)

    def url(self, name):
        # Preserve the trailing slash after normalizing the path.
        name = self._normalize_name(clean_name(name))
        blob = self._get_blob(self._encode_name(name))
        return blob.public_url

    def get_available_name(self, name, max_length=None):
        if self.file_overwrite:
            name = clean_name(name)
            return name
        return super().get_available_name(name, max_length)

    def try_del(self, callable: Callable[[], None]) -> None:
        self._try(callable)

    def try_get(self, callable: Callable[[], None]) -> None:
        self._try(callable)

    def try_set(self, callable: Callable[[], None]) -> None:
        self._try(callable)

    def _try(self, callable: Callable[[], None]) -> None:
        # The default policy since 2018 has been to retry five times in a loop with no backoff
        # for gets, sets, and deletes. This behavior has been preserved here.
        #
        # To implement a custom retry policy see `src/sentry/utils/retries.py` and the
        # `GoogleCloudStorageWithReplayUploadPolicy` class.
        try_repeated(callable)


class GoogleCloudStorageWithReplayUploadPolicy(GoogleCloudStorage):
    """Google cloud storage class with replay upload policy."""

    # "try_get" inherits the default behavior. We don't want to exponentially wait in that
    # context. We're maintaining the status-quo for now but in the future we can add policies for
    # these methods or use no policy at all and implement retries at a higher, more contextual
    # level.
    #
    # def try_get(self, callable: Callable[[], None]) -> None:

    def create_retry_policy(self):
        """Retry an action with sigmoid delay for a maximum of five attempts."""

        def should_retry(attempt: int, e: Exception) -> bool:
            """Retry gateway timeout exceptions up to the limit."""
            return attempt <= REPLAY_GCS_RETRIES and isinstance(e, GCS_RETRYABLE_ERRORS)

        # Retry cadence: After a brief period of fast retries the function will retry once
        # per second for two minutes.
        return ConditionalRetryPolicy(should_retry, sigmoid_delay())

    def try_set(self, callable: Callable[[], None]) -> None:
        policy = self.create_retry_policy()
        policy(callable)

    def try_del(self, callable: Callable[[], None]) -> None:
        policy = self.create_retry_policy()
        policy(callable)
