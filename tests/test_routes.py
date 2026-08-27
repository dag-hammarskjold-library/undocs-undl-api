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
# Successful streaming response
# ---------------------------------------------------------------------------

class FakeRemoteResponse:
    """Mimics the object returned by urlopen for streaming reads."""

    def __init__(self, body: bytes, headers=None):
        self._buffer = body
        self._pos = 0
        self.headers = headers if headers is not None else {}
        self.closed = False

    def read(self, size=-1):
        if size is None or size < 0:
            chunk = self._buffer[self._pos:]
            self._pos = len(self._buffer)
            return chunk
        chunk = self._buffer[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk

    def close(self):
        self.closed = True


class _Headers(dict):
    """dict with a .get that behaves like http.client headers."""


def _fake_response(body=b"file-body", content_type="application/pdf"):
    return FakeRemoteResponse(body, _Headers({"Content-Type": content_type}))


class TestSuccessfulStreamingResponse:
    def test_returns_200(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.routes.urlopen", return_value=_fake_response()):
            response = client.get("/en/A/79/PV.1")
        assert response.status_code == 200

    def test_streams_full_body(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.routes.urlopen", return_value=_fake_response(b"the-pdf-bytes")):
            response = client.get("/en/A/79/PV.1")
        assert response.data == b"the-pdf-bytes"

    def test_streams_body_larger_than_chunk_size(self, client):
        # Body larger than STREAM_CHUNK_SIZE to exercise multi-chunk streaming
        big_body = b"x" * (64 * 1024 * 3 + 17)
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.routes.urlopen", return_value=_fake_response(big_body)):
            response = client.get("/en/A/79/PV.1")
        assert response.data == big_body

    def test_does_not_set_location_header(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.routes.urlopen", return_value=_fake_response()):
            response = client.get("/en/A/79/PV.1")
        assert "Location" not in response.headers

    def test_content_disposition_uses_filename(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.routes.urlopen", return_value=_fake_response()):
            response = client.get("/en/A/79/PV.1")
        assert response.headers["Content-Disposition"] == (
            'inline; filename="A_79_PV.1-EN.pdf"'
        )

    def test_content_disposition_falls_back_when_no_filename(self, client):
        doc = dict(SAMPLE_DOC)
        doc.pop("filename")
        with patch("app.db.find_document", return_value=doc), \
             patch("app.routes.urlopen", return_value=_fake_response()):
            response = client.get("/en/A/79/PV.1")
        # Fallback is built from symbol (slashes -> underscores) + language
        assert response.headers["Content-Disposition"] == (
            'inline; filename="A_79_PV.1-EN.pdf"'
        )

    def test_fallback_filename_for_ot_uses_uppercased_code(self, client):
        doc = dict(SAMPLE_DOC)
        doc.pop("filename")
        with patch("app.db.find_document", return_value=doc), \
             patch("app.routes.urlopen", return_value=_fake_response()):
            response = client.get("/ot/A/79/PV.1")
        assert response.headers["Content-Disposition"] == (
            'inline; filename="A_79_PV.1-OT.pdf"'
        )

    def test_find_document_called_with_uppercased_language(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC) as mock_find, \
             patch("app.routes.urlopen", return_value=_fake_response()):
            client.get("/en/A/79/PV.1")
        mock_find.assert_called_once_with("A/79/PV.1", "EN")

    def test_all_valid_language_codes_accepted(self, client):
        for lang in ("ar", "en", "fr", "ru", "es", "zh", "ot"):
            with patch("app.db.find_document", return_value=SAMPLE_DOC), \
                 patch("app.routes.urlopen", return_value=_fake_response()):
                response = client.get(f"/{lang}/A/79/PV.1")
            assert response.status_code == 200, f"Expected 200 for language '{lang}'"


# ---------------------------------------------------------------------------
# 502 — origin fetch failure
# ---------------------------------------------------------------------------

class TestOriginFetchFailure:
    def test_returns_502_on_urlerror(self, client):
        from urllib.error import URLError
        with patch("app.db.find_document", return_value=SAMPLE_DOC), \
             patch("app.routes.urlopen", side_effect=URLError("boom")):
            response = client.get("/en/A/79/PV.1")
        assert response.status_code == 502


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
        assert b"en" in response.data

    def test_symbol_with_multiple_slashes_is_captured(self, client):
        """<path:symbol> must capture symbols like A/79/PV.1 containing slashes."""
        with patch("app.db.find_document", return_value=None) as mock_find:
            client.get("/en/A/79/PV.1")
        mock_find.assert_called_once_with("A/79/PV.1", "EN")
