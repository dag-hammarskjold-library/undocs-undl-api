from flask import Blueprint, jsonify, redirect

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

    doc = db.find_document(symbol, language.upper())

    if doc is None:
        return jsonify({
            "error": "Document not found",
            "symbol": symbol,
            "language": language,
        }), 404

    url = "https://" + doc["uri"]
    return redirect(url, code=302)
