"""
Integration tests for app/db.py.

Requires a running MongoDB instance. The conftest.py fixture points the
db module at a dedicated test database (undocs_test by default) which is
dropped after the session.

Run with:
    MONGO_URI=mongodb://localhost:27017 pytest tests/test_db.py -v
"""

import pytest
from datetime import datetime, timezone

import app.db as db_module
from app.db import find_document, log_request


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_collections(init_test_db):
    """Drop test collections before each test to ensure isolation."""
    init_test_db.files.drop()
    init_test_db.allowlist.drop()
    init_test_db.request_logs.drop()
    yield


@pytest.fixture
def sample_document(init_test_db):
    """Insert a sample document and return it."""
    doc = {
        "_id": "f2b7a2942690a486645ab9214d48bd6a",
        "filename": "A_79_PV.1-EN.pdf",
        "identifiers": [{"type": "symbol", "value": "A/79/PV.1"}],
        "languages": ["EN"],
        "mimetype": "application/pdf",
        "size": 287700,
        "source": "gdoc-dlx-NY",
        "timestamp": datetime(2025, 2, 8, 8, 10, 25, tzinfo=timezone.utc),
        "uri": "undl-files.s3.amazonaws.com/f2b7a2942690a486645ab9214d48bd6a",
    }
    init_test_db.files.insert_one(doc)
    return doc


@pytest.fixture
def sample_allowlist_entry(init_test_db):
    """Insert an allowlisted IP entry and return it."""
    entry = {"ip": "192.168.1.10", "label": "System A", "active": True}
    init_test_db.allowlist.insert_one(entry)
    return entry


# ---------------------------------------------------------------------------
# find_document
# ---------------------------------------------------------------------------

class TestFindDocument:
    def test_returns_document_for_valid_symbol_and_language(self, sample_document):
        result = find_document("A/79/PV.1", "EN")
        assert result is not None
        assert result["_id"] == "f2b7a2942690a486645ab9214d48bd6a"
        assert result["uri"] == "undl-files.s3.amazonaws.com/f2b7a2942690a486645ab9214d48bd6a"

    def test_returns_none_for_unknown_symbol(self, sample_document):
        result = find_document("UNKNOWN/SYMBOL", "EN")
        assert result is None

    def test_returns_none_when_language_not_available(self, sample_document):
        result = find_document("A/79/PV.1", "FR")
        assert result is None

    def test_returns_none_when_collection_is_empty(self, init_test_db):
        result = find_document("A/79/PV.1", "EN")
        assert result is None

    def test_language_match_is_case_sensitive(self, sample_document):
        # Database stores "EN"; lowercase "en" must not match
        result = find_document("A/79/PV.1", "en")
        assert result is None


# ---------------------------------------------------------------------------
# log_request
# ---------------------------------------------------------------------------

class TestLogRequest:
    def test_inserts_log_document(self, init_test_db):
        data = {
            "timestamp": datetime.now(timezone.utc),
            "ip": "192.168.1.10",
            "language": "en",
            "symbol": "A/79/PV.1",
            "status_code": 302,
            "response_time_ms": 12,
        }
        log_request(data)
        entry = init_test_db.request_logs.find_one({"symbol": "A/79/PV.1"})
        assert entry is not None
        assert entry["status_code"] == 302
        assert entry["language"] == "en"
        assert entry["ip"] == "192.168.1.10"

    def test_multiple_log_entries_accumulate(self, init_test_db):
        for i in range(3):
            log_request({
                "timestamp": datetime.now(timezone.utc),
                "ip": "10.0.0.1",
                "language": "fr",
                "symbol": f"DOC/{i}",
                "status_code": 302,
                "response_time_ms": 5,
            })
        count = init_test_db.request_logs.count_documents({})
        assert count == 3


# ---------------------------------------------------------------------------
# init_db / get_db guard
# ---------------------------------------------------------------------------

class TestGetDbGuard:
    def test_get_db_raises_if_not_initialised(self, monkeypatch):
        # Temporarily clear the module-level _db to simulate uninitialised state
        monkeypatch.setattr(db_module, "_db", None)
        with pytest.raises(RuntimeError, match="Database has not been initialised"):
            db_module.get_db()
