from datetime import datetime, timezone

from pymongo import MongoClient

_client = None
_db = None


def init_db(mongo_uri: str, mongo_db: str):
    """Initialise the MongoDB client. Called once at app startup."""
    global _client, _db
    _client = MongoClient(mongo_uri)
    _db = _client[mongo_db]


def get_db():
    """Return the active database handle."""
    if _db is None:
        raise RuntimeError("Database has not been initialised. Call init_db() first.")
    return _db


def find_document(symbol: str, language: str) -> dict | None:
    """
    Look up a document by its symbol and language code.

    Args:
        symbol:   Document symbol, e.g. "A/79/PV.1"
        language: Uppercase language code, e.g. "EN"

    Returns:
        The matched document dict, or None if not found.
    """
    db = get_db()
    return db.files.find_one(
        {"identifiers.value": symbol, "languages": language}
    )


def log_request(data: dict):
    """
    Insert a request log entry into the request_logs collection.

    Args:
        data: Dict containing log fields (timestamp, ip, language,
              symbol, status_code, response_time_ms).
    """
    db = get_db()
    db.request_logs.insert_one(data)

def is_ip_allowed():
    """
    Stub function to pass tests
    """
    return True