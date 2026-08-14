import os

import pytest
import mongomock

# ---------------------------------------------------------------------------
# Shared fixture: raw PyMongo test database
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_db():
    """
    Use mongomock to provide an in-memory MongoDB instance.
    """
    client = mongomock.MongoClient()
    db_name = os.environ.get("MONGO_DB_TEST", "undocs_test")
    db = client[db_name]
    yield db
    # No need to drop or close for in-memory mock


# ---------------------------------------------------------------------------
# Shared fixture: initialised app/db module pointing at the test database
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def init_test_db(test_db):
    """
    Point the app's db module at the test database so all db.py functions
    operate against it during the test session.
    """
    import app.db as db_module
    db_module._db = test_db
    yield test_db
    # Reset so other test sessions start clean
    db_module._db = None
    db_module._client = None
