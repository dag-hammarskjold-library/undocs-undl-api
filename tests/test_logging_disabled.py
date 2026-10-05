"""
Tests for the 'logging disabled' path in app/db.py — when no dedicated log
connection string is configured (log_mongo_uri is None), log writes must
no-op gracefully rather than raise, so document serving is unaffected.

These test db.py directly without a real MongoDB.
"""

from unittest.mock import patch

import app.db as db


def _reset_log_state():
    """Simulate init_db having run with no log connection."""
    db._log_client = None
    db._log_db = None


def test_get_log_db_returns_none_when_disabled():
    _reset_log_state()
    assert db.get_log_db() is None


def test_log_request_noops_when_disabled():
    _reset_log_state()
    # Should simply return without raising.
    db.log_request({"status_code": 200})


def test_record_missing_file_noops_when_disabled():
    _reset_log_state()
    # Should simply return without raising.
    db.record_missing_file("A/79/PV.1", "en")


def test_init_db_without_log_uri_disables_logging():
    """init_db with log_mongo_uri=None leaves the log DB unset."""
    with patch("app.db.MongoClient") as mock_client:
        db.init_db("mongodb://undl", "undlFiles", log_mongo_uri=None)
    # UNDL client was created; log client was not.
    assert mock_client.call_count == 1
    assert db.get_log_db() is None


def test_init_db_with_log_uri_creates_separate_client():
    """init_db with a log_mongo_uri creates a second client for logs."""
    with patch("app.db.MongoClient") as mock_client, \
         patch("app.db._ensure_log_indexes"):
        db.init_db(
            "mongodb://undl", "undlFiles",
            log_mongo_uri="mongodb://logs", log_db_name="undocs_api",
        )
    # Two separate clients: one for UNDL, one for logs.
    assert mock_client.call_count == 2
    assert db.get_log_db() is not None
