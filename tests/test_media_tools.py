"""Tests for video downloader and asset storage.

Verifies:
1. VideoDownloader: mock mode, platform detection, download/transcribe pipeline
2. AssetStorage: store/get/list/delete with real filesystem and mock mode
3. Edge cases: empty uploads, disallowed extensions, missing files
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tools.asset_storage import AssetStorage
from src.tools.video_downloader import TranscribeSegment, VideoDownloader, VideoMetadata

# ==============================================================================
# VideoDownloader Tests
# ==============================================================================


class TestVideoDownloaderInit:
    """Initialization in various environments."""

    def test_init_default_output_dir(self, tmp_path):
        """Should create client with default output dir."""
        # Use mock mode - just verify init works
        dl = VideoDownloader(output_dir=tmp_path)
        assert dl.output_dir == tmp_path
        assert dl.output_dir.exists()

    def test_platform_detection(self):
        """Should detect platform from URL."""
        dl = VideoDownloader()
        assert dl._detect_platform("https://www.tiktok.com/@user/video/123") == "tiktok"
        assert dl._detect_platform("https://www.douyin.com/video/456") == "douyin"
        assert dl._detect_platform("https://www.xiaohongshu.com/explore/789") == "xiaohongshu"
        assert dl._detect_platform("https://youtu.be/abc123") == "youtube"
        assert dl._detect_platform("https://example.com/video") == "unknown"

    def test_xhslink_detection(self):
        """Should detect xiaohongshu via xhslink short URLs."""
        dl = VideoDownloader()
        assert dl._detect_platform("https://xhslink.com/abc123") == "xiaohongshu"


class TestVideoDownloaderMockMode:
    """Mock mode behavior when yt-dlp/whisper unavailable."""

    @pytest.fixture
    def dl(self, tmp_path):
        downloader = VideoDownloader(output_dir=tmp_path)
        downloader._ytdlp_available = False
        downloader._whisper_available = False
        return downloader

    @pytest.mark.asyncio
    async def test_download_returns_mock_metadata(self, dl):
        """Without yt-dlp, download should return mock metadata."""
        metadata = await dl.download("https://www.tiktok.com/@user/video/123")
        assert isinstance(metadata, VideoMetadata)
        assert metadata.source_url == "https://www.tiktok.com/@user/video/123"
        assert "[MOCK]" in metadata.title
        assert metadata.platform == "tiktok"
        assert "[MOCK_DOWNLOAD" in metadata.local_path

    @pytest.mark.asyncio
    async def test_transcribe_returns_mock_segments(self, dl):
        """Without whisper, transcribe should return mock segments."""
        segments = await dl.transcribe("/fake/path.mp4")
        assert len(segments) == 6
        assert all(isinstance(s, TranscribeSegment) for s in segments)
        assert segments[0].start == 0.0
        assert segments[0].text.startswith("Hey everyone")

    @pytest.mark.asyncio
    async def test_mock_download_sentinel_skips_available_whisper(self, dl):
        dl._whisper_available = True

        segments = await dl.transcribe("[MOCK_DOWNLOAD — fixture]")

        assert len(segments) == 6

    @pytest.mark.asyncio
    async def test_download_and_transcribe_returns_both(self, dl):
        """download_and_transcribe should return metadata + segments."""
        result = await dl.download_and_transcribe("https://www.douyin.com/video/456")
        assert "metadata" in result
        assert "segments" in result
        assert result["metadata"]["platform"] == "douyin"
        assert len(result["segments"]) == 6

    @pytest.mark.asyncio
    async def test_download_and_transcribe_skips_transcribe_for_mock_download(self, dl, monkeypatch):
        """Mock download paths should not be passed into real transcription backends."""
        dl._whisper_available = True

        async def fail_if_called(_video_path: str):
            raise AssertionError("mock download path reached transcription")

        monkeypatch.setattr(dl, "transcribe", fail_if_called)
        result = await dl.download_and_transcribe("https://www.douyin.com/video/456")
        assert result["metadata"]["local_path"].startswith("[MOCK_DOWNLOAD")
        assert len(result["segments"]) == 6

    @pytest.mark.asyncio
    async def test_mock_metadata_from_douyin(self, dl):
        """Mock metadata should preserve URL platform info."""
        meta = await dl.download("https://www.douyin.com/video/test123")
        assert meta.platform == "douyin"

    @pytest.mark.asyncio
    async def test_mock_metadata_unknown_platform(self, dl):
        """Unknown URLs should get 'unknown' platform."""
        meta = await dl.download("https://random-site.com/video")
        assert meta.platform == "unknown"


class TestVideoDownloaderHelpers:
    """Helper functionality."""

    def test_transcribe_segment_model(self):
        """TranscribeSegment should store timing and text."""
        seg = TranscribeSegment(start=1.0, end=5.5, text="hello world")
        assert seg.start == 1.0
        assert seg.end == 5.5
        assert seg.text == "hello world"

    def test_video_metadata_model(self):
        """VideoMetadata should store all fields."""
        meta = VideoMetadata(
            title="Test Video",
            author="test_user",
            duration=60.0,
            source_url="https://tiktok.com/@u/v/1",
            platform="tiktok",
            local_path="/tmp/video.mp4",
        )
        assert meta.title == "Test Video"
        assert meta.duration == 60.0


# ==============================================================================
# AssetStorage Tests
# ==============================================================================


class TestAssetStorageInit:
    """Initialization."""

    def test_init_creates_storage_dir(self, tmp_path):
        """Should create storage directory on init."""
        storage = AssetStorage(storage_dir=tmp_path / "my_assets")
        assert storage.storage_dir.exists()

    def test_init_mock_mode(self):
        """Mock mode should not create directories."""
        storage = AssetStorage(use_mock=True)
        assert storage.use_mock is True


class TestAssetStorageStore:
    """Store operations."""

    def test_store_returns_asset_record(self, tmp_path):
        """Store should return a valid AssetRecord."""
        storage = AssetStorage(storage_dir=tmp_path)
        record = storage.store(
            file_data=b"fake video content",
            original_name="product_demo.mp4",
            tags=["video", "product"],
            metadata={"source": "upload"},
        )
        assert record.asset_id.startswith("ASSET-")
        assert record.original_name == "product_demo.mp4"
        assert "video" in record.tags
        assert record.file_size == len(b"fake video content")

    def test_store_writes_file_to_disk(self, tmp_path):
        """Store should persist file to disk."""
        storage = AssetStorage(storage_dir=tmp_path)
        data = b"binary video data here"
        record = storage.store(file_data=data, original_name="test.mp4")
        assert Path(record.file_path).exists()
        assert Path(record.file_path).read_bytes() == data

    def test_store_updates_index(self, tmp_path):
        """Store should update the in-memory index."""
        storage = AssetStorage(storage_dir=tmp_path)
        assert storage.total_assets == 0
        storage.store(file_data=b"test", original_name="a.mp4")
        assert storage.total_assets == 1

    def test_store_persists_index_to_disk(self, tmp_path):
        """Store should persist index to disk as JSON."""
        storage = AssetStorage(storage_dir=tmp_path)
        storage.store(file_data=b"test", original_name="a.mp4")
        assert storage.index_path.exists()
        index_data = json.loads(storage.index_path.read_text())
        assert len(index_data) == 1

    def test_store_multiple_assets(self, tmp_path):
        """Should support storing multiple assets."""
        storage = AssetStorage(storage_dir=tmp_path)
        for i in range(5):
            storage.store(file_data=f"data{i}".encode(), original_name=f"vid{i}.mp4")
        assert storage.total_assets == 5


class TestAssetStorageGet:
    """Get operations."""

    def test_get_returns_record(self, tmp_path):
        """Get should return the correct record."""
        storage = AssetStorage(storage_dir=tmp_path)
        record = storage.store(file_data=b"test", original_name="demo.mp4")
        fetched = storage.get(record.asset_id)
        assert fetched is not None
        assert fetched.asset_id == record.asset_id
        assert fetched.original_name == "demo.mp4"

    def test_get_nonexistent_returns_none(self, tmp_path):
        """Get on nonexistent ID should return None."""
        storage = AssetStorage(storage_dir=tmp_path)
        assert storage.get("NONEXISTENT") is None

    def test_get_file_path_returns_path(self, tmp_path):
        """get_file_path should return the file path."""
        storage = AssetStorage(storage_dir=tmp_path)
        record = storage.store(file_data=b"test", original_name="vid.mp4")
        path = storage.get_file_path(record.asset_id)
        assert path is not None
        assert Path(path).exists()

    def test_get_file_path_nonexistent(self, tmp_path):
        """get_file_path for nonexistent asset should return None."""
        storage = AssetStorage(storage_dir=tmp_path)
        assert storage.get_file_path("FAKE-ID") is None


class TestAssetStorageList:
    """List operations."""

    def test_list_returns_all(self, tmp_path):
        """List should return all stored assets."""
        storage = AssetStorage(storage_dir=tmp_path)
        for i in range(4):
            storage.store(file_data=f"d{i}".encode(), original_name=f"v{i}.mp4")
        all_records = storage.list()
        assert len(all_records) == 4

    def test_list_with_tag_filter(self, tmp_path):
        """List with tag filter should only return tagged assets."""
        storage = AssetStorage(storage_dir=tmp_path)
        storage.store(file_data=b"1", original_name="a.mp4", tags=["product"])
        storage.store(file_data=b"2", original_name="b.mp4", tags=["brand"])
        storage.store(file_data=b"3", original_name="c.mp4", tags=["product", "demo"])
        product_assets = storage.list(tags=["product"])
        assert len(product_assets) == 2
        brand_assets = storage.list(tags=["brand"])
        assert len(brand_assets) == 1

    def test_list_with_limit(self, tmp_path):
        """List with limit should cap results."""
        storage = AssetStorage(storage_dir=tmp_path)
        for i in range(10):
            storage.store(file_data=f"d{i}".encode(), original_name=f"v{i}.mp4")
        assert len(storage.list(limit=3)) == 3

    def test_search_by_tags(self, tmp_path):
        """search_by_tags returns assets matching ANY tag."""
        storage = AssetStorage(storage_dir=tmp_path)
        storage.store(file_data=b"1", original_name="a.mp4", tags=["product"])
        storage.store(file_data=b"2", original_name="b.mp4", tags=["brand"])
        storage.store(file_data=b"3", original_name="c.mp4", tags=["demo"])
        results = storage.search_by_tags(["product", "brand"])
        assert len(results) == 2


class TestAssetStorageDelete:
    """Delete operations."""

    def test_delete_removes_record(self, tmp_path):
        """Delete should remove from index."""
        storage = AssetStorage(storage_dir=tmp_path)
        record = storage.store(file_data=b"test", original_name="vid.mp4")
        assert storage.total_assets == 1
        storage.delete(record.asset_id)
        assert storage.total_assets == 0

    def test_delete_removes_file(self, tmp_path):
        """Delete should remove the file from disk."""
        storage = AssetStorage(storage_dir=tmp_path)
        record = storage.store(file_data=b"test", original_name="vid.mp4")
        file_path = storage.get_file_path(record.asset_id)
        assert Path(file_path).exists()  # type: ignore[arg-type]
        storage.delete(record.asset_id)
        assert not Path(file_path).exists()  # type: ignore[arg-type]

    def test_delete_nonexistent_returns_false(self, tmp_path):
        """Delete on nonexistent ID should return False."""
        storage = AssetStorage(storage_dir=tmp_path)
        assert storage.delete("FAKE-ID") is False


class TestAssetStorageMockMode:
    """Mock mode behavior."""

    @pytest.fixture
    def storage(self):
        return AssetStorage(use_mock=True)

    def test_mock_store_returns_record(self, storage):
        """Mock store should return a valid record."""
        record = storage.store(file_data=b"test", original_name="demo.mp4")
        assert record.asset_id.startswith("MOCK-")
        assert "[MOCK_STORAGE" in record.file_path

    def test_mock_get_returns_record(self, storage):
        """Mock get should return a record."""
        record = storage.get("any-id")
        assert record is not None
        assert record.asset_id.startswith("MOCK-")

    def test_mock_list_returns_records(self, storage):
        """Mock list should return records."""
        records = storage.list()
        assert len(records) == 3

    def test_mock_delete_returns_true(self, storage):
        """Mock delete should return True."""
        assert storage.delete("anything") is True

    def test_mock_get_file_path(self, storage):
        """Mock get_file_path should return mock path."""
        path = storage.get_file_path("test-id")
        assert path is not None
        assert "MOCK_PATH" in path


class TestAssetStorageEdgeCases:
    """Edge cases."""

    def test_disallowed_extension(self, tmp_path):
        """Disallowed extension should fallback to .bin."""
        storage = AssetStorage(storage_dir=tmp_path)
        record = storage.store(file_data=b"test", original_name="doc.pdf")
        assert record.filename.endswith(".bin")

    def test_empty_file_data(self, tmp_path):
        """Should handle empty file data."""
        storage = AssetStorage(storage_dir=tmp_path)
        record = storage.store(file_data=b"", original_name="empty.mp4")
        assert record.file_size == 0
        assert Path(record.file_path).exists()

    def test_total_size_calculation(self, tmp_path):
        """total_size_bytes should sum all file sizes."""
        storage = AssetStorage(storage_dir=tmp_path)
        storage.store(file_data=b"12345", original_name="a.mp4")
        storage.store(file_data=b"67890", original_name="b.mp4")
        assert storage.total_size_bytes == 10

    def test_index_survives_reinit(self, tmp_path):
        """Index should be reloaded from disk on init."""
        storage1 = AssetStorage(storage_dir=tmp_path)
        storage1.store(file_data=b"test", original_name="survive.mp4")
        del storage1

        storage2 = AssetStorage(storage_dir=tmp_path)
        assert storage2.total_assets == 1
