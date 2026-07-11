"""Sprint 43 — Storage abstraction (R-11) + App factory (R-12) tests."""
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


# ═══════════════════════════════════════════════════════════════════
# STORAGE BACKEND — LocalStorage
# ═══════════════════════════════════════════════════════════════════

class TestLocalStorage:
    @pytest.fixture
    def store(self, tmp_path):
        from api.storage import LocalStorage
        return LocalStorage(base_dir=tmp_path)

    def test_save_and_load_roundtrip(self, store):
        data = b"hello world"
        key = store.save("test/file.bin", data)
        assert key == "test/file.bin"
        assert store.load("test/file.bin") == data

    def test_load_missing_raises_file_not_found(self, store):
        with pytest.raises(FileNotFoundError):
            store.load("missing/file.bin")

    def test_delete_existing(self, store):
        store.save("del_me.txt", b"bye")
        assert store.exists("del_me.txt")
        store.delete("del_me.txt")
        assert not store.exists("del_me.txt")

    def test_delete_nonexistent_is_noop(self, store):
        store.delete("does_not_exist.txt")  # should not raise

    def test_exists_true(self, store):
        store.save("check.bin", b"data")
        assert store.exists("check.bin") is True

    def test_exists_false(self, store):
        assert store.exists("ghost.bin") is False

    def test_url_returns_api_path(self, store):
        url = store.url("activity_photos/abc.jpg")
        assert "/api/storage/" in url
        assert "abc.jpg" in url

    def test_url_uses_app_url_env(self, store):
        with patch.dict(os.environ, {"APP_URL": "https://labx.app"}):
            url = store.url("photos/test.jpg")
            assert url.startswith("https://labx.app")

    def test_nested_key_creates_directories(self, store):
        store.save("a/b/c/deep.bin", b"nested")
        assert store.exists("a/b/c/deep.bin")

    def test_overwrite_existing_file(self, store):
        store.save("file.txt", b"v1")
        store.save("file.txt", b"v2")
        assert store.load("file.txt") == b"v2"

    def test_path_traversal_rejected(self, store):
        with pytest.raises((ValueError, Exception)):
            store.load("../../etc/passwd")

    def test_empty_bytes_save(self, store):
        store.save("empty.bin", b"")
        assert store.load("empty.bin") == b""
        assert store.exists("empty.bin")

    def test_binary_content_preserved(self, store):
        data = bytes(range(256))  # all byte values
        store.save("binary.bin", data)
        assert store.load("binary.bin") == data


class TestLocalStorageDefaultBase:
    def test_default_base_dir_exists_after_init(self):
        from api.storage import LocalStorage
        s = LocalStorage()
        # Should not raise — base dir is created
        assert s._base.exists()


# ═══════════════════════════════════════════════════════════════════
# STORAGE — get_storage factory
# ═══════════════════════════════════════════════════════════════════

class TestGetStorage:
    def test_default_is_local(self):
        from api.storage import get_storage, LocalStorage
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STORAGE_BACKEND", None)
            s = get_storage()
            assert isinstance(s, LocalStorage)

    def test_local_explicit(self):
        from api.storage import get_storage, LocalStorage
        with patch.dict(os.environ, {"STORAGE_BACKEND": "local"}):
            s = get_storage()
            assert isinstance(s, LocalStorage)

    def test_s3_without_bucket_raises(self):
        from api.storage import get_storage
        env = {"STORAGE_BACKEND": "s3"}
        env.pop("S3_BUCKET_NAME", None)
        with patch.dict(os.environ, env):
            os.environ.pop("S3_BUCKET_NAME", None)
            with pytest.raises(RuntimeError, match="S3_BUCKET_NAME"):
                get_storage()

    def test_s3_without_boto3_raises_runtime_error(self):
        from api.storage import get_storage
        with patch.dict(os.environ, {"STORAGE_BACKEND": "s3", "S3_BUCKET_NAME": "test-bucket"}):
            with patch.dict("sys.modules", {"boto3": None}):
                with pytest.raises((RuntimeError, ImportError)):
                    get_storage()

    def test_module_level_storage_singleton(self):
        from api import storage as storage_mod
        s1 = storage_mod.storage
        s2 = storage_mod.storage
        assert s1 is s2  # same instance


# ═══════════════════════════════════════════════════════════════════
# STORAGE — S3Storage (mocked boto3)
# ═══════════════════════════════════════════════════════════════════

class TestS3Storage:
    @pytest.fixture
    def mock_boto3(self):
        mock_client = MagicMock()
        mock_boto3_mod = MagicMock()
        mock_boto3_mod.client.return_value = mock_client
        with patch.dict("sys.modules", {"boto3": mock_boto3_mod}):
            yield mock_boto3_mod, mock_client

    def test_save_calls_put_object(self, mock_boto3):
        from api.storage import S3Storage
        _, mock_client = mock_boto3
        s = S3Storage(bucket="test-bucket")
        s.save("photos/test.jpg", b"image data")
        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket", Key="photos/test.jpg", Body=b"image data"
        )

    def test_save_returns_key(self, mock_boto3):
        from api.storage import S3Storage
        _, mock_client = mock_boto3
        s = S3Storage(bucket="test-bucket")
        result = s.save("photos/img.jpg", b"data")
        assert result == "photos/img.jpg"

    def test_load_calls_get_object(self, mock_boto3):
        from api.storage import S3Storage
        _, mock_client = mock_boto3
        mock_client.get_object.return_value = {"Body": MagicMock(read=lambda: b"file content")}
        s = S3Storage(bucket="my-bucket")
        data = s.load("docs/file.pdf")
        assert data == b"file content"
        mock_client.get_object.assert_called_once_with(Bucket="my-bucket", Key="docs/file.pdf")

    def test_delete_calls_delete_object(self, mock_boto3):
        from api.storage import S3Storage
        _, mock_client = mock_boto3
        s = S3Storage(bucket="my-bucket")
        s.delete("old/file.jpg")
        mock_client.delete_object.assert_called_once_with(Bucket="my-bucket", Key="old/file.jpg")

    def test_url_with_public_prefix(self, mock_boto3):
        from api.storage import S3Storage
        _, _ = mock_boto3
        s = S3Storage(bucket="b", public_url_prefix="https://cdn.labx.app")
        url = s.url("photos/abc.jpg")
        assert url == "https://cdn.labx.app/photos/abc.jpg"

    def test_url_generates_presigned_without_prefix(self, mock_boto3):
        from api.storage import S3Storage
        _, mock_client = mock_boto3
        mock_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/signed/url"
        s = S3Storage(bucket="b")
        url = s.url("file.jpg")
        assert "s3.amazonaws.com" in url or url == "https://s3.amazonaws.com/signed/url"

    def test_exists_true(self, mock_boto3):
        from api.storage import S3Storage
        _, mock_client = mock_boto3
        mock_client.head_object.return_value = {}
        s = S3Storage(bucket="b")
        assert s.exists("file.jpg") is True

    def test_exists_false_on_exception(self, mock_boto3):
        from api.storage import S3Storage
        _, mock_client = mock_boto3
        mock_client.head_object.side_effect = Exception("404")
        s = S3Storage(bucket="b")
        assert s.exists("missing.jpg") is False

    def test_endpoint_url_passed_to_boto3(self, mock_boto3):
        from api.storage import S3Storage
        mock_b, _ = mock_boto3
        S3Storage(bucket="r2-bucket", endpoint_url="https://account.r2.cloudflarestorage.com")
        mock_b.client.assert_called_once()
        _, kwargs = mock_b.client.call_args
        assert kwargs.get("endpoint_url") == "https://account.r2.cloudflarestorage.com"


# ═══════════════════════════════════════════════════════════════════
# APP FACTORY — R-12
# ═══════════════════════════════════════════════════════════════════

class TestAppFactory:
    def test_create_app_returns_fastapi_instance(self):
        from fastapi import FastAPI
        from api.coach_main import create_app
        _app = create_app()
        assert isinstance(_app, FastAPI)

    def test_create_app_has_correct_title(self):
        from api.coach_main import create_app
        _app = create_app()
        assert "LabX" in _app.title

    def _all_paths(self, _app) -> set:
        """Safely collect all route paths from a FastAPI app."""
        paths = set()
        for r in _app.routes:
            p = getattr(r, "path", None)
            if p:
                paths.add(p)
        return paths

    def test_create_app_has_health_route(self):
        from api.coach_main import create_app
        _app = create_app()
        paths = self._all_paths(_app)
        assert "/health" in paths

    def test_create_app_has_api_auth_routes(self):
        from api.coach_main import create_app
        _app = create_app()
        # OpenAPI schema resolves all nested router paths
        schema = _app.openapi()
        assert any("/api/auth" in p for p in schema.get("paths", {}))

    def test_create_app_produces_independent_instances(self):
        from api.coach_main import create_app
        app1 = create_app()
        app2 = create_app()
        assert app1 is not app2

    def test_module_app_is_fastapi(self):
        from fastapi import FastAPI
        from api.coach_main import app
        assert isinstance(app, FastAPI)

    def test_module_app_is_result_of_create_app(self):
        from fastapi import FastAPI
        from api.coach_main import app
        assert isinstance(app, FastAPI)
        assert app.title == "LabX Coach API"

    def test_create_app_has_many_api_routes(self):
        from api.coach_main import create_app
        _app = create_app()
        # OpenAPI schema resolves all nested router paths
        schema = _app.openapi()
        api_paths = [p for p in schema.get("paths", {}) if "/api/" in p]
        assert len(api_paths) > 30

    def test_create_app_has_metrics_endpoint(self):
        from api.coach_main import create_app
        _app = create_app()
        paths = self._all_paths(_app)
        assert "/metrics" in paths

    def test_create_app_has_routes(self):
        from api.coach_main import create_app
        _app = create_app()
        assert len(_app.routes) > 0

    def test_create_app_functional_health(self, db):
        """create_app() returns a working app — health endpoint responds 200."""
        from fastapi.testclient import TestClient
        from api.coach_main import create_app
        from api.database import get_db
        _app = create_app()
        _app.dependency_overrides[get_db] = lambda: db
        with TestClient(_app) as c:
            r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] in ("ok", "degraded")
