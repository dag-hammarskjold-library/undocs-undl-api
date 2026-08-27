from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from flask import Blueprint, Response, render_template

import app.db as db

bp = Blueprint("redirect", __name__)

VALID_LANGUAGES = {"ar", "en", "fr", "ru", "es", "zh", "ot"}

# Size of each chunk streamed from the origin to the client, in bytes.
STREAM_CHUNK_SIZE = 64 * 1024  # 64 KB


def _error(message: str, status: int):
    """Render the shared error page with the given message and status code."""
    return render_template("error.html", message=message), status


def _download_filename(doc: dict, symbol: str, language: str) -> str:
    """
    Determine the filename to offer the user on download.

    Uses the document's 'filename' field when present; otherwise derives a
    fallback from the symbol and language, e.g. "A_79_PV.1-EN.pdf".
    """
    filename = doc.get("filename")
    if filename:
        return filename

    # Fallback: build a name from the symbol and language.
    safe_symbol = symbol.replace("/", "_")
    return f"{safe_symbol}-{language.upper()}.pdf"


@bp.route("/<language>/<path:symbol>")
def resolve_document(language: str, symbol: str):
    """
    Resolve a document by language code and symbol, then stream its content.

    The file is streamed from the origin (S3) through this service to the
    client. The origin URL is never exposed to the client, and the
    Content-Disposition header sets a friendly download filename.

    Args:
        language: Lowercase language code (ar, en, fr, ru, es, zh, ot).
        symbol:   Document symbol, e.g. "A/79/PV.1".

    Returns:
        200 streaming the document content on success.
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
        remote_response = urlopen(request, timeout=10)
    except (URLError, HTTPError, TimeoutError):
        return _error(
            f"The document '{symbol}' could not be retrieved at this time.",
            502,
        )

    headers = remote_response.headers or {}
    content_type = headers.get("Content-Type", "application/octet-stream")
    filename = _download_filename(doc, symbol, language)

    def generate():
        """Stream the origin response to the client in chunks."""
        try:
            while True:
                chunk = remote_response.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            remote_response.close()

    response = Response(generate(), content_type=content_type, status=200)
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'

    # Note: no Content-Length is set. The response is streamed with
    # Transfer-Encoding: chunked, and setting Content-Length alongside
    # chunked encoding is contradictory and can truncate the download.

    return response
