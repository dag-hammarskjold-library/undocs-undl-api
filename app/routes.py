from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from flask import Blueprint, Response, jsonify

import app.db as db

bp = Blueprint("redirect", __name__)

VALID_LANGUAGES = {"ar", "en", "fr", "ru", "es", "zh", "ot"}


@bp.route("/<language>/<path:symbol>")
def resolve_document(language: str, symbol: str):
    """
    Resolve a document by language code and symbol, then redirect to it.

    Args:
        language: Lowercase language code (ar, en, fr, ru, es, zh, ot).
        symbol:   Document symbol, e.g. "A/79/PV.1".

    Returns:
        302 redirect to the document URI on success.
        400 JSON error if the language code is invalid.
        404 JSON error if the document or language is not found.
    """
    if language not in VALID_LANGUAGES:
        return jsonify({
            "error": "Invalid language code",
            "valid_languages": sorted(VALID_LANGUAGES),
        }), 400

    # The external language code 'ot' maps to 'de' in the database.
    db_language = "DE" if language.lower() == "ot" else language.upper()
    doc = db.find_document(symbol, db_language)

    if doc is None:
        return jsonify({
            "error": "Document not found",
            "symbol": symbol,
            "language": language,
        }), 404

    url = "https://" + doc["uri"]

    try:
        request = Request(url, headers={"User-Agent": "undocs-undl-api/1.0"})
        with urlopen(request, timeout=5) as remote_response:
            headers = remote_response.headers or {}
            content_type = headers.get("Content-Type", "application/octet-stream")
            body = remote_response.read()
    except (URLError, HTTPError, TimeoutError) as exc:
        return jsonify({
            "error": "Unable to fetch document content",
            "detail": str(exc),
        }), 502

    return Response(body, content_type=content_type, status=200)
