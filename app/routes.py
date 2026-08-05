from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from flask import Blueprint, Response, render_template

import app.db as db

bp = Blueprint("redirect", __name__)

VALID_LANGUAGES = {"ar", "en", "fr", "ru", "es", "zh", "ot"}


def _error(message: str, status: int):
    """Render the shared error page with the given message and status code."""
    return render_template("error.html", message=message), status


@bp.route("/<language>/<path:symbol>")
def resolve_document(language: str, symbol: str):
    """
    Resolve a document by language code and symbol, then serve its content.

    Args:
        language: Lowercase language code (ar, en, fr, ru, es, zh, ot).
        symbol:   Document symbol, e.g. "A/79/PV.1".

    Returns:
        200 with document content on success.
        400 error page if the language code is invalid.
        404 error page if the document or language is not found.
        502 error page if the document content cannot be fetched.
    """
    if language not in VALID_LANGUAGES:
        return _error(
            f"'{language}' is not a valid language code. "
            f"Valid codes are: {', '.join(sorted(VALID_LANGUAGES))}.",
            400,
        )

    # The external language code 'ot' maps to 'DE' in the database.
    db_language = "DE" if language.lower() == "ot" else language.upper()
    doc = db.find_document(symbol, db_language)

    if doc is None:
        return _error(
            f"The document '{symbol}' is not available in '{language.lower()}'.",
            404,
        )

    url = "https://" + doc["uri"]

    try:
        request = Request(url, headers={"User-Agent": "undocs-undl-api/1.0"})
        with urlopen(request, timeout=5) as remote_response:
            headers = remote_response.headers or {}
            content_type = headers.get("Content-Type", "application/octet-stream")
            body = remote_response.read()
    except (URLError, HTTPError, TimeoutError) as exc:
        return _error(
            f"The document '{symbol}' could not be retrieved at this time.",
            502,
        )

    return Response(body, content_type=content_type, status=200)
