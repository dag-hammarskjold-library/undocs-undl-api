import os

import pytest
from pymongo import MongoClient


# ---------------------------------------------------------------------------
# Shared fixture: raw PyMongo test database
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_db():
    """
    Connect to a local MongoDB instance and return a dedicated test database.
    Drops the database after the test session to leave no residue.
    """
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB_TEST", "undocs_test")
    client = MongoClient(uri)
    db = client[db_name]
    yield db
    client.drop_database(db_name)
    client.close()


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
