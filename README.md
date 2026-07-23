# undocs-undl-api

A production-ready Flask API that resolves document symbols to file URLs via HTTP redirect.

## Endpoint

```
GET /<language>/<symbol>
```

| Parameter  | Description                                           | Example      |
|------------|-------------------------------------------------------|--------------|
| `language` | Lowercase language code                               | `en`         |
| `symbol`   | Document symbol (slashes are part of the path)        | `A/79/PV.1`  |

**Valid language codes:** `ar`, `en`, `fr`, `ru`, `es`, `zh`, `ot`

### Responses

| Status | Meaning                                      |
|--------|----------------------------------------------|
| 302    | Document found — redirect to file URL        |
| 400    | Invalid language code                        |
| 403    | Client IP not in allowlist                   |
| 404    | Document or language not found               |

### Example

```bash
curl -v http://localhost:5000/en/A/79/PV.1
# HTTP/1.1 302 FOUND
# Location: https://undl-files.s3.amazonaws.com/<id>
```

---

## Local Development

### Prerequisites

- Python 3.12+
- Docker and Docker Compose

### Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `MONGO_URI` and `MONGO_DB` to point at your local or remote MongoDB.

### Run with Docker Compose

```bash
docker-compose up
```

This starts the Flask app on port 5000 and a local MongoDB on port 27017.

### Run tests

```bash
pytest tests/test_health.py tests/test_routes.py tests/test_middleware.py -v
```

Unit tests mock all MongoDB calls — no live database needed.

The integration tests in `tests/test_db.py` require a running MongoDB:

```bash
MONGO_URI=mongodb://localhost:27017 pytest tests/test_db.py -v
```

---

## Configuration

| Variable        | Required | Description                                                                 |
|-----------------|----------|-----------------------------------------------------------------------------|
| `MONGO_URI`     | No       | MongoDB connection string. If absent, fetched from AWS SSM (see below).     |
| `MONGO_DB`      | Yes      | MongoDB database name.                                                       |
| `FLASK_ENV`     | No       | `development` or `production` (default: `production`).                      |

### AWS SSM Parameter Store

When `MONGO_URI` is not set as an environment variable (all deployed environments),
the app fetches it from AWS SSM Parameter Store at startup:

- **Parameter name:** `devISSU-admin-connect-string`

The ECS task role must have the following IAM permission:

```json
{
  "Effect": "Allow",
  "Action": "ssm:GetParameter",
  "Resource": "arn:aws:ssm:<region>:<account-id>:parameter/devISSU-admin-connect-string"
}
```

---

## MongoDB Collections

### `files` (existing)

Documents resolved by the API. The query used:

```python
{"identifiers.value": "<symbol>", "languages": "<LANG>"}
```

Language codes are uppercased before querying (`en` → `EN`).

### `allowlist` (new)

Controls which client IPs can access the API.

```json
{
  "ip": "192.168.1.10",
  "label": "System A",
  "active": true
}
```

Set `active: false` to revoke access without deleting the entry.
Changes take effect immediately — no redeployment needed.

### `request_logs` (new)

One document per request, written after every response.

```json
{
  "timestamp": "<ISO datetime>",
  "ip": "192.168.1.10",
  "language": "en",
  "symbol": "A/79/PV.1",
  "status_code": 302,
  "response_time_ms": 12
}
```

---

## Deployment (AWS ECS Fargate)

### Build and push to ECR

```bash
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

docker build -t undocs-undl-api .
docker tag undocs-undl-api:latest <account-id>.dkr.ecr.<region>.amazonaws.com/undocs-undl-api:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/undocs-undl-api:latest
```

### ECS Task Definition (key fields)

```json
{
  "containerDefinitions": [{
    "image": "<account-id>.dkr.ecr.<region>.amazonaws.com/undocs-undl-api:latest",
    "portMappings": [{"containerPort": 8000}],
    "environment": [
      {"name": "MONGO_DB", "value": "undocs"},
      {"name": "FLASK_ENV", "value": "production"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/undocs-undl-api",
        "awslogs-region": "<region>",
        "awslogs-stream-prefix": "ecs"
      }
    }
  }]
}
```

`MONGO_URI` is intentionally absent — the app will fetch it from SSM at startup.

### ALB health check

Configure the ALB target group health check to:

- **Path:** `/health`
- **Protocol:** HTTP
- **Port:** 8000
- **Expected status:** 200

---

## Project Structure

```
undocs-undl-api/
├── app/
│   ├── __init__.py       # Flask app factory, before/after request hooks
│   ├── config.py         # Config loading (env vars + AWS SSM)
│   ├── db.py             # PyMongo client and query functions
│   └── routes.py         # Redirect blueprint
├── tests/
│   ├── conftest.py       # Shared fixtures for integration tests
│   ├── test_db.py        # Integration tests for db.py (requires MongoDB)
│   ├── test_health.py    # Health endpoint tests
│   ├── test_middleware.py # IP allowlist and request logging tests
│   └── test_routes.py    # Redirect route unit tests
├── wsgi.py               # Gunicorn entry point
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
