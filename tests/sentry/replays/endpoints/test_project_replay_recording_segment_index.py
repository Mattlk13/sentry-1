import datetime
import uuid
import zlib
from collections import namedtuple

from django.urls import reverse

from sentry.replays.lib.storage import FilestoreBlob, RecordingSegmentStorageMeta, StorageBlob
from sentry.replays.testutils import mock_replay
from sentry.replays.usecases.pack import pack
from sentry.testutils.cases import APITestCase, ReplaysSnubaTestCase, TransactionTestCase
from sentry.testutils.helpers.response import close_streaming_response

Message = namedtuple("Message", ["project_id", "replay_id"])


# have to use TransactionTestCase because we're using threadpools
class FilestoreProjectReplayRecordingSegmentIndexTestCase(TransactionTestCase):
    endpoint = "sentry-api-0-project-replay-recording-segment-index"

    def setUp(self) -> None:
        super().setUp()
        self.login_as(self.user)
        self.replay_id = uuid.uuid4().hex
        self.url = reverse(
            self.endpoint,
            args=(self.organization.slug, self.project.slug, self.replay_id),
        )

    def save_recording_segment(
        self, segment_id: int, data: bytes, compressed: bool = True, is_archived: bool = False
    ) -> None:
        metadata = RecordingSegmentStorageMeta(
            project_id=self.project.id,
            replay_id=self.replay_id,
            segment_id=segment_id,
            retention_days=30,
            file_id=None,
        )
        FilestoreBlob().set(metadata, zlib.compress(data) if compressed else data)

    def test_index_download_basic_compressed(self) -> None:
        for i in range(0, 3):
            self.save_recording_segment(i, f'[{{"test":"hello {i}"}}]'.encode())

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download=true")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert (
            b'[[{"test":"hello 0"}],[{"test":"hello 1"}],[{"test":"hello 2"}]]'
            == close_streaming_response(response)
        )

    def test_index_download_basic_compressed_over_chunk_size(self) -> None:
        self.save_recording_segment(1, b"a" * 5000)

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download=true")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert len(close_streaming_response(response)) == 5002

    def test_index_download_basic_not_compressed(self) -> None:
        for i in range(0, 3):
            self.save_recording_segment(i, f'[{{"test":"hello {i}"}}]'.encode(), compressed=False)

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert (
            b'[[{"test":"hello 0"}],[{"test":"hello 1"}],[{"test":"hello 2"}]]'
            == close_streaming_response(response)
        )

    def test_index_download_paginate(self) -> None:
        for i in range(0, 3):
            self.save_recording_segment(i, f'[{{"test":"hello {i}"}}]'.encode())

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download&per_page=1&cursor=0:0:0")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert b'[[{"test":"hello 0"}]]' == close_streaming_response(response)

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download&per_page=1&cursor=1:1:0")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert b'[[{"test":"hello 1"}]]' == close_streaming_response(response)

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download&per_page=2&cursor=1:1:0")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert b'[[{"test":"hello 1"}],[{"test":"hello 2"}]]' == close_streaming_response(response)

    def test_index_download_packed(self) -> None:
        """Test packed segment data is readable."""
        self.save_recording_segment(0, pack(b'[{"test":"hello 0"}]', b"video-bytes"))
        self.save_recording_segment(1, pack(b'[{"test":"hello 1"}]', None))

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download=true")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert b'[[{"test":"hello 0"}],[{"test":"hello 1"}]]' == close_streaming_response(response)


class StorageProjectReplayRecordingSegmentIndexTestCase(
    FilestoreProjectReplayRecordingSegmentIndexTestCase, APITestCase, ReplaysSnubaTestCase
):
    def setUp(self) -> None:
        super().setUp()
        self.features = {"organizations:session-replay": True}

    def save_recording_segment(
        self, segment_id: int, data: bytes, compressed: bool = True, is_archived: bool = False
    ) -> None:
        # Insert the row in clickhouse.
        self.store_replays(
            mock_replay(
                datetime.datetime.now() - datetime.timedelta(seconds=22),
                self.project.id,
                self.replay_id,
                segment_id=segment_id,
                retention_days=30,
                is_archived=is_archived,
            )
        )

        # Insert an empty segment row into ClickHouse (this should not be returned). If the tests
        # do not error it means these empty rows were not retured.
        #
        # TODO: Apparently we can't submit replays with a null segment_id?  This breaks older
        # versions of Clickhouse ingestion.
        #
        # self.store_replays(
        #     mock_replay(
        #         datetime.datetime.now() - datetime.timedelta(seconds=22),
        #         self.project.id,
        #         self.replay_id,
        #         segment_id=None,
        #         retention_days=30,
        #         **metadata,
        #     )
        # )

        # Store the binary blob in the remote storage provider.
        metadata = RecordingSegmentStorageMeta(
            project_id=self.project.id,
            replay_id=self.replay_id,
            segment_id=segment_id,
            retention_days=30,
            file_id=None,
        )
        StorageBlob().set(metadata, zlib.compress(data) if compressed else data)

    def test_archived_segment_metadata_returns_no_results(self) -> None:
        """Assert archived segment metadata returns no results."""
        self.save_recording_segment(0, b"[{}]", compressed=True, is_archived=True)

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download=true")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert close_streaming_response(response) == b"[]"

    def test_delayed_ingestion_returns_empty_lists(self) -> None:
        """Assert archived segment metadata returns no results."""
        self.store_replays(
            mock_replay(
                datetime.datetime.now() - datetime.timedelta(seconds=22),
                self.project.id,
                self.replay_id,
                segment_id=0,
                retention_days=30,
                is_archived=False,
            )
        )
        self.store_replays(
            mock_replay(
                datetime.datetime.now() - datetime.timedelta(seconds=22),
                self.project.id,
                self.replay_id,
                segment_id=1,
                retention_days=30,
                is_archived=False,
            )
        )

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download=true")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert close_streaming_response(response) == b"[[],[]]"

    def test_blob_does_not_exist(self) -> None:
        """Assert missing blobs return default value."""
        self.store_replays(
            mock_replay(
                datetime.datetime.now() - datetime.timedelta(seconds=22),
                self.project.id,
                self.replay_id,
                segment_id=0,
                retention_days=30,
            )
        )

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download=true")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert close_streaming_response(response) == b"[[]]"

    def test_missing_segment_meta(self) -> None:
        """Assert missing segment meta returns no blob data."""
        metadata = RecordingSegmentStorageMeta(
            project_id=self.project.id,
            replay_id=self.replay_id,
            segment_id=0,
            retention_days=30,
            file_id=None,
        )
        StorageBlob().set(metadata, zlib.compress(b"[{}]"))

        with self.feature("organizations:session-replay"):
            response = self.client.get(self.url + "?download=true")

        assert response.status_code == 200
        assert response.get("Content-Type") == "application/json"
        assert close_streaming_response(response) == b"[]"
