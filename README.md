# undocs-undl-api

A production-ready Flask API that resolves UN document symbols to file URLs via HTTP redirect.

## Endpoint

```
GET /<language>/<symbol>
```

| Parameter  | Description                                    | Example     |
|------------|------------------------------------------------|-------------|
| `language` | Lowercase language code                        | `en`        |
| `symbol`   | Document symbol (may contain slashes)          | `A/79/PV.1` |

**Valid language codes:** `ar`, `en`, `fr`, `ru`, `es`, `zh`, `ot`

### Responses

| Status | Meaning                                    |
|--------|--------------------------------------------|
| 302    | Document found — redirect to file URL      |
| 400    | Invalid language code                      |
| 404    | Document or language not found             |

### Example

```bash
curl -v http://localhost:5000/en/A/79/PV.1
# HTTP/1.1 302 FOUND
# Location: https://undl-files.s3.amazonaws.com/<id>
```

---

## How It Works

1. The language code is validated against the allowed set.
2. The language is uppercased and used to query MongoDB:
   ```python
   {"identifiers.value": "A/79/PV.1", "languages": "EN"}
   ```
3. The redirect URL is constructed as `https://` + the document's `uri` field.
4. Every request is logged to the `request_logs` collection with timestamp, IP, symbol, language, status code, and response time.

---

## Configuration

All configuration is loaded from AWS SSM Parameter Store at startup. The environment is controlled by a single variable:

| Variable    | Required | Description                                             |
|-------------|----------|---------------------------------------------------------|
| `FLASK_ENV` | No       | `development` or `production` (defaults to `production`) |

### SSM Parameters

| `FLASK_ENV`   | SSM Key                        | Database      |
|---------------|--------------------------------|---------------|
| `development` | `devISSU-admin-connect-string` | `dev_undlFiles` |
| `production`  | `prodISSU-admin-connect-string`| `undlFiles`   |

The ECS task role must have `ssm:GetParameter` permission for the relevant key.

---

## MongoDB Collections

### `files` (existing)

The collection queried to resolve documents.

```json
{
  "_id": "f2b7a2942690a486645ab9214d48bd6a",
  "filename": "A_79_PV.1-EN.pdf",
  "identifiers": [{ "type": "symbol", "value": "A/79/PV.1" }],
  "languages": ["EN"],
  "mimetype": "application/pdf",
  "size": 287700,
  "source": "gdoc-dlx-NY",
  "timestamp": "2025-02-08T08:10:25.796Z",
  "uri": "undl-files.s3.amazonaws.com/f2b7a2942690a486645ab9214d48bd6a"
}
```

### `request_logs` (new)

One document written per request for analytics.

```json
{
  "timestamp": "2025-02-08T08:10:25.796Z",
  "ip": "192.168.1.10",
  "language": "en",
  "symbol": "A/79/PV.1",
  "status_code": 302,
  "response_time_ms": 12
}
```

---

## Local Development

### Prerequisites

- Python 3.12+
- AWS credentials configured locally with access to the `devISSU-admin-connect-string` SSM parameter

### Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### Run

```bash
FLASK_ENV=development flask --app wsgi:app run
```

Or with Docker Compose (starts the app + a local MongoDB, but note the app will still call SSM for the connection string on startup — ensure AWS credentials are available):

```bash
docker-compose up
```

### Run tests

Unit tests mock all AWS and MongoDB calls — no live connections needed:

```bash
pytest tests/test_health.py tests/test_routes.py tests/test_middleware.py -v
```

Integration tests for the database layer require a running MongoDB:

```bash
MONGO_URI=mongodb://localhost:27017 pytest tests/test_db.py -v
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

The ECS task role must have:

```json
{
  "Effect": "Allow",
  "Action": "ssm:GetParameter",
  "Resource": "arn:aws:ssm:<region>:<account-id>:parameter/prodISSU-admin-connect-string"
}
```

### ALB health check

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
│   ├── config.py         # Config loading from AWS SSM (dev/prod switch)
│   ├── db.py             # PyMongo client and query functions
│   └── routes.py         # Redirect blueprint
├── tests/
│   ├── conftest.py       # Shared fixtures for integration tests
│   ├── test_db.py        # Integration tests for db.py (requires MongoDB)
│   ├── test_health.py    # Health endpoint tests
│   ├── test_middleware.py # Request logging tests
│   └── test_routes.py    # Redirect route unit tests
├── wsgi.py               # Gunicorn entry point
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
