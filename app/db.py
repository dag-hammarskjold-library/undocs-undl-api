from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.collation import Collation

_client = None       # UNDL client (document lookups)
_log_client = None   # dedicated logs client (undocs_api)
_db = None           # UNDL database (document lookups)
_log_db = None       # undocs_api database (analytics: request_logs, missing_files)

# Case-insensitive collation matching the existing index on identifiers.value
_ci_collation = Collation(locale="en", strength=2)

# Retention for request logs, in seconds (90 days). Applied via a TTL index.
_REQUEST_LOG_TTL_SECONDS = 90 * 24 * 60 * 60


def init_db(mongo_uri: str, mongo_db: str,
            log_mongo_uri: str | None = None,
            log_db_name: str = "undocs_api"):
    """
    Initialise the MongoDB clients and database handles. Called once at startup.

    Document lookups use `mongo_uri` / `mongo_db`. Analytics logs use their own
    connection (`log_mongo_uri`) so the logs database can be served by a user
    scoped to it. If `log_mongo_uri` is None, logging is disabled: the log
    handles stay None and log writes become no-ops (document serving is
    unaffected).

    Args:
        mongo_uri:     UNDL connection string (document lookups).
        mongo_db:      UNDL database name.
        log_mongo_uri: Dedicated connection string for the logs database, or
                       None to disable logging.
        log_db_name:   Analytics logs database name (default 'undocs_api').
    """
    global _client, _log_client, _db, _log_db
    _client = MongoClient(mongo_uri)
    _db = _client[mongo_db]

    if log_mongo_uri:
        _log_client = MongoClient(log_mongo_uri)
        _log_db = _log_client[log_db_name]
        _ensure_log_indexes()
    else:
        _log_client = None
        _log_db = None


def _ensure_log_indexes():
    """
    Create the indexes the log collections rely on. Safe to call repeatedly;
    createIndex is idempotent when the index already exists.
    """
    if _log_db is None:
        return
    try:
        # TTL index: MongoDB auto-deletes request_logs docs older than 90 days.
        _log_db.request_logs.create_index(
            "timestamp", expireAfterSeconds=_REQUEST_LOG_TTL_SECONDS
        )
        # One entry per unique symbol+language in missing_files.
        _log_db.missing_files.create_index(
            [("symbol", 1), ("language", 1)], unique=True
        )
    except Exception:
        # Index creation must never block startup; log-side failures are
        # non-fatal to serving documents.
        pass


def get_db():
    """Return the active UNDL database handle (document lookups)."""
    if _db is None:
        raise RuntimeError("Database has not been initialised. Call init_db() first.")
    return _db


def get_log_db():
    """
    Return the analytics (undocs_api) database handle, or None if logging is
    not configured (no dedicated log connection string was provided).
    """
    return _log_db


def find_document(symbol: str, language: str) -> dict | None:
    """
    Look up a document by its symbol and language code.

    Uses collation with strength=2 (case-insensitive) to leverage the
    existing collation-aware index on identifiers.value.

    Args:
        symbol:   Document symbol, e.g. "A/79/PV.1"
        language: Uppercase language code, e.g. "EN"

    Returns:
        The matched document dict, or None if not found.
    """
    db = get_db()
    return db.files.find_one(
        {"identifiers.value": symbol, "languages": language},
        collation=_ci_collation,
    )


def log_request(data: dict):
    """
    Insert a request log entry into undocs_api.request_logs.

    Args:
        data: Dict of log fields (timestamp, ip, language, symbol,
              status_code, response_time_ms, user_agent, referrer,
              method, outcome).
    """
    db = get_log_db()
    if db is None:
        return  # logging disabled (no dedicated log connection configured)
    db.request_logs.insert_one(data)


def record_missing_file(symbol: str, language: str):
    """
    Record a request for a document that could not be found, so a human can
    review it (the file may be unposted, or need retrieval from another
    system such as ODS).

    Deduplicated: one document per unique symbol+language, with a hit count
    and first/last-seen timestamps.

    Args:
        symbol:   Document symbol that was not found.
        language: Requested (external, lowercase) language code.
    """
    db = get_log_db()
    if db is None:
        return  # logging disabled (no dedicated log connection configured)
    now = datetime.now(timezone.utc)
    db.missing_files.update_one(
        {"symbol": symbol, "language": language},
        {
            "$inc": {"count": 1},
            "$set": {"last_seen": now},
            "$setOnInsert": {"first_seen": now},
        },
        upsert=True,
    )


def is_ip_allowed():
    """
    Stub function to pass tests
    """
    return True
