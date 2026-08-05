"""
Unit tests for the redirect route (app/routes.py).

All db functions are patched at their source (app.db) so no MongoDB
connection is needed.

Run with:
    pytest tests/test_routes.py -v
"""

from unittest.mock import patch

import pytest

from app import create_app
from app.config import Config

SAMPLE_DOC = {
    "_id": "f2a",
    "filename": "A_79_PV.1-EN.pdf",
    "identifiers": [{"type": "symbol", "value": "A/79/PV.1"}],
    "languages": ["EN"],
    "mimetype": "application/pdf",
    "size": 287700,
    "source": "gdoc-dlx-NY",
    "uri": "s3.amazonaws.com/f2a",
}

FAKE_CONFIG = Config(
    mongo_uri="mongodb://localhost:27017",
    mongo_db="undocs_test",
    flask_env="testing",
)


@pytest.fixture
def client():
    with patch("app.config.load_config", return_value=FAKE_CONFIG), \
         patch("app.db.init_db"), \
         patch("app.db.log_request"):
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# Successful proxy response
# ---------------------------------------------------------------------------

class FakeRemoteResponse:
    def __init__(self, body, headers=None):
        self._body = body
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestSuccessfulProxyResponse:
    def test_returns_200(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.routes.urlopen", return_value=FakeRemoteResponse(b"file-body", {"get": lambda *args, **kwargs: None})):
            response = client.get("/en/A/79/PV.1")
        assert response.status_code == 200

    def test_returns_remote_body(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.routes.urlopen", return_value=FakeRemoteResponse(b"file-body")):
            response = client.get("/en/A/79/PV.1")
        assert response.data == b"file-body"

    def test_does_not_set_location_header(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.routes.urlopen", return_value=FakeRemoteResponse(b"file-body")):
            response = client.get("/en/A/79/PV.1")
        assert "Location" not in response.headers

    def test_find_document_called_with_uppercased_language(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC) as mock_find, \
             patch("app.routes.urlopen", return_value=FakeRemoteResponse(b"file-body")):
            client.get("/en/A/79/PV.1")
        mock_find.assert_called_once_with("A/79/PV.1", "EN")

    def test_all_valid_language_codes_accepted(self, client):
        for lang in ("ar", "en", "fr", "ru", "es", "zh", "ot"):
            with patch("app.db.find_document", return_value=SAMPLE_DOC), \
                 patch("app.routes.urlopen", return_value=FakeRemoteResponse(b"file-body")):
                response = client.get(f"/{lang}/A/79/PV.1")
            assert response.status_code == 200, f"Expected 200 for language '{lang}'"


# ---------------------------------------------------------------------------
# 400 — invalid language code
# ---------------------------------------------------------------------------

class TestInvalidLanguageCode:
    def test_returns_400_for_unknown_language(self, client):
        response = client.get("/xx/A/79/PV.1")
        assert response.status_code == 400

    def test_response_is_html(self, client):
        response = client.get("/xx/A/79/PV.1")
        assert b"text/html" in response.content_type.encode()

    def test_error_page_contains_invalid_language(self, client):
        response = client.get("/xx/A/79/PV.1")
        assert b"xx" in response.data

    def test_error_page_lists_valid_languages(self, client):
        response = client.get("/xx/A/79/PV.1")
        for code in ("ar", "en", "fr", "ru", "es", "zh", "ot"):
            assert code.encode() in response.data

    def test_uppercase_language_input_is_rejected(self, client):
        # "EN" is not in VALID_LANGUAGES (lowercase only) — callers must use lowercase
        response = client.get("/EN/A/79/PV.1")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 404 — document not found
# ---------------------------------------------------------------------------

class TestDocumentNotFound:
    def test_returns_404_when_symbol_unknown(self, client):
        with patch("app.db.find_document", return_value=None):
            response = client.get("/en/UNKNOWN/SYMBOL")
        assert response.status_code == 404

    def test_returns_404_when_language_unavailable(self, client):
        with patch("app.db.find_document", return_value=None):
            response = client.get("/fr/A/79/PV.1")
        assert response.status_code == 404

    def test_response_is_html(self, client):
        with patch("app.db.find_document", return_value=None):
            response = client.get("/en/A/79/PV.1")
        assert b"text/html" in response.content_type.encode()

    def test_error_page_contains_symbol(self, client):
        with patch("app.db.find_document", return_value=None):
            response = client.get("/en/A/79/PV.1")
        assert b"A/79/PV.1" in response.data

    def test_error_page_contains_language(self, client):
        with patch("app.db.find_document", return_value=None):
            response = client.get("/en/A/79/PV.1")
        assert b"EN" in response.data

    def test_symbol_with_multiple_slashes_is_captured(self, client):
        """<path:symbol> must capture symbols like A/79/PV.1 containing slashes."""
        with patch("app.db.find_document", return_value=None) as mock_find:
            client.get("/en/A/79/PV.1")
        mock_find.assert_called_once_with("A/79/PV.1", "EN")
