import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, mongo_uri: str, mongo_db: str, flask_env: str,
                 log_mongo_uri: str | None = None,
                 log_db_name: str = "undocs_api"):
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self.flask_env = flask_env
        # Logs are written to a dedicated database using its own connection
        # string (a user scoped to the undocs_api database), so analytics data
        # is isolated from the source document metadata. If no dedicated log
        # connection string is available, log_mongo_uri is None and logging is
        # disabled rather than failing requests.
        self.log_mongo_uri = log_mongo_uri
        self.log_db_name = log_db_name


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


def _fetch_optional_ssm_parameter(client, name: str) -> str | None:
    """
    Fetch an SSM parameter that may not exist yet.

    Returns the value, or None if the parameter is absent. Used for the
    dedicated logs connection string so that an environment without one
    (e.g. prod before its parameter is created) starts normally with
    logging simply disabled, rather than failing to boot.
    """
    try:
        return client.get_parameter(
            Name=name, WithDecryption=True
        )["Parameter"]["Value"]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ParameterNotFound":
            return None
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

    Selects dev or prod SSM parameters based on FLASK_ENV:
      - development: devISSU-admin-connect-string  / db: dev_undlFiles
      - production:  prodISSU-admin-connect-string / db: undlFiles

    FLASK_ENV defaults to 'production' if not set.
    """
    flask_env = os.environ.get("FLASK_ENV", "production")

    ssm = boto3.client("ssm")

    if flask_env == "development":
        mongo_uri = _fetch_ssm_parameter(ssm, "devISSU-admin-connect-string")
        mongo_db = "dev_undlFiles"
        log_mongo_uri = _fetch_optional_ssm_parameter(
            ssm, "dev-undocs-api-connect-string"
        )
    else:
        mongo_uri = _fetch_ssm_parameter(ssm, "prodISSU-admin-connect-string")
        mongo_db = "undlFiles"
        # Prod logs connection string (optional until the parameter is
        # created). Logging is disabled gracefully if absent.
        log_mongo_uri = _fetch_optional_ssm_parameter(
            ssm, "prod-undocs-api-connect-string"
        )

    return Config(
        mongo_uri=mongo_uri,
        mongo_db=mongo_db,
        flask_env=flask_env,
        log_mongo_uri=log_mongo_uri,
        log_db_name="undocs_api",
    )
