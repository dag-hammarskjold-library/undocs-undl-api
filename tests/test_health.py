from unittest.mock import patch

import pytest

from app import create_app
from app.config import Config

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


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.get_json() == {"status": "ok"}
