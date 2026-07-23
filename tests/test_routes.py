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
    "_id": "f2b7a2942690a486645ab9214d48bd6a",
    "filename": "A_79_PV.1-EN.pdf",
    "identifiers": [{"type": "symbol", "value": "A/79/PV.1"}],
    "languages": ["EN"],
    "mimetype": "application/pdf",
    "size": 287700,
    "source": "gdoc-dlx-NY",
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
         patch("app.db.init_db"), \
         patch("app.db.log_request"):
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# Successful redirect
# ---------------------------------------------------------------------------

class TestSuccessfulRedirect:
    def test_returns_302(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC):
            response = client.get("/en/A/79/PV.1")
        assert response.status_code == 302

    def test_location_header_is_https_uri(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC):
            response = client.get("/en/A/79/PV.1")
        assert response.headers["Location"] == (
            "https://undl-files.s3.amazonaws.com/f2b7a2942690a486645ab9214d48bd6a"
        )

    def test_find_document_called_with_uppercased_language(self, client):
        with patch("app.db.find_document", return_value=SAMPLE_DOC) as mock_find:
            client.get("/en/A/79/PV.1")
        mock_find.assert_called_once_with("A/79/PV.1", "EN")

    def test_all_valid_language_codes_accepted(self, client):
        for lang in ("ar", "en", "fr", "ru", "es", "zh", "ot"):
            with patch("app.db.find_document", return_value=SAMPLE_DOC):
                response = client.get(f"/{lang}/A/79/PV.1")
            assert response.status_code == 302, f"Expected 302 for language '{lang}'"


# ---------------------------------------------------------------------------
# 400 — invalid language code
# ---------------------------------------------------------------------------

class TestInvalidLanguageCode:
    def test_returns_400_for_unknown_language(self, client):
        response = client.get("/xx/A/79/PV.1")
        assert response.status_code == 400

    def test_error_body_contains_message(self, client):
        response = client.get("/xx/A/79/PV.1")
        data = response.get_json()
        assert "error" in data
        assert "valid_languages" in data

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

    def test_error_body_contains_symbol_and_language(self, client):
        with patch("app.db.find_document", return_value=None):
            response = client.get("/en/A/79/PV.1")
        data = response.get_json()
        assert data["symbol"] == "A/79/PV.1"
        assert data["language"] == "en"

    def test_symbol_with_multiple_slashes_is_captured(self, client):
        """<path:symbol> must capture symbols like A/79/PV.1 containing slashes."""
        with patch("app.db.find_document", return_value=None) as mock_find:
            client.get("/en/A/79/PV.1")
        mock_find.assert_called_once_with("A/79/PV.1", "EN")
