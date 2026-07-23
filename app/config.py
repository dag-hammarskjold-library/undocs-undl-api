import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, mongo_uri: str, mongo_db: str, flask_env: str):
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self.flask_env = flask_env


def _fetch_ssm_parameter(client, name: str) -> str:
    """Fetch a plaintext or SecureString parameter from SSM Parameter Store."""
    try:
        return client.get_parameter(
            Name=name, WithDecryption=True
        )["Parameter"]["Value"]
    except ClientError as exc:
        raise ConfigError(
            f"Could not fetch SSM parameter '{name}': {exc}"
        ) from exc
    except BotoCoreError as exc:
        raise ConfigError(
            f"AWS error fetching SSM parameter '{name}': {exc}"
        ) from exc


def load_config() -> Config:
    """
    Load application configuration from AWS SSM Parameter Store.

    Both the MongoDB connection string and database name are fetched from SSM.
    The ECS task role must have ssm:GetParameter permission for:
      - devISSU-admin-connect-string
      - devISSU-mongo-db

    FLASK_ENV is the only optional environment variable (defaults to 'production').
    """
    flask_env = os.environ.get("FLASK_ENV", "production")

    ssm = boto3.client("ssm")

    if flask_env == 'development':
        mongo_uri = _fetch_ssm_parameter(ssm, "devISSU-admin-connect-string")
        mongo_db = 'dev_undlFiles'
    else:
        mongo_uri = _fetch_ssm_parameter(ssm, "'prodISSU-admin-connect-string'")
        mongo_db = 'undlFiles'

    return Config(
        mongo_uri=mongo_uri,
        mongo_db=mongo_db,
        flask_env=flask_env,
    )
