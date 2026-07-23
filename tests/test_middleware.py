"""
Unit tests for the request logging hook (app/__init__.py after_request).

All db functions are patched at their source (app.db) so no MongoDB
connection is needed.

Run with:
    pytest tests/test_middleware.py -v
"""

from unittest.mock import patch

import pytest

from app import create_app
from app.config import Config

SAMPLE_DOC = {
    "_id": "f2b7a2942690a486645ab9214d48bd6a",
    "filename": "A_79_PV.1-EN.pdf",
    "identifiers": [{"type": "symbol", "value": "A/79/PV.1"}],
    "languages": ["EN"],
    "uri": "undl-files.s3.amazonaws.com/f2b7a2942690a486645ab9214d48bd6a",
}

FAKE_CONFIG = Config(
    mongo_uri="mongodb://localhost:27017",
    mongo_db="undocs_test",
    flask_env="testing",
)


@pytest.fixture
def client():
    with patch("app.config.load_config", return_value=FAKE_CONFIG), \
         patch("app.db.init_db"):
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# Request logging
# ---------------------------------------------------------------------------

class TestRequestLogging:
    def test_log_written_on_successful_redirect(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.db.log_request") as mock_log:
            client.get("/en/A/79/PV.1")
        mock_log.assert_called_once()
        logged = mock_log.call_args[0][0]
        assert logged["status_code"] == 302
        assert logged["language"] == "en"
        assert logged["symbol"] == "A/79/PV.1"
        assert "timestamp" in logged
        assert "response_time_ms" in logged

    def test_log_written_on_404(self, client):
        with patch("app.db.find_document", return_value=None), \
             patch("app.db.log_request") as mock_log:
            client.get("/en/UNKNOWN/SYMBOL")
        mock_log.assert_called_once()
        logged = mock_log.call_args[0][0]
        assert logged["status_code"] == 404

    def test_log_written_on_400(self, client):
        with patch("app.db.log_request") as mock_log:
            client.get("/xx/A/79/PV.1")
        mock_log.assert_called_once()
        logged = mock_log.call_args[0][0]
        assert logged["status_code"] == 400

    def test_response_time_ms_is_non_negative_integer(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.db.log_request") as mock_log:
            client.get("/en/A/79/PV.1")
        logged = mock_log.call_args[0][0]
        assert isinstance(logged["response_time_ms"], int)
        assert logged["response_time_ms"] >= 0

    def test_logging_failure_does_not_affect_response(self, client):
        """A broken log_request must not cause a 500."""
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.db.log_request", side_effect=Exception("db down")):
            response = client.get("/en/A/79/PV.1")
        assert response.status_code == 302

    def test_ip_captured_from_x_forwarded_for(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.db.log_request") as mock_log:
            client.get("/en/A/79/PV.1",
                       headers={"X-Forwarded-For": "203.0.113.5, 10.0.0.1"})
        logged = mock_log.call_args[0][0]
        assert logged["ip"] == "203.0.113.5"

    def test_ip_falls_back_to_remote_addr(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.db.log_request") as mock_log:
            client.get("/en/A/79/PV.1")
        logged = mock_log.call_args[0][0]
        assert logged["ip"] == "127.0.0.1"
