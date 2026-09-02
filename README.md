# undocs-undl-api

A Flask API that resolves UN document symbols to their stored files and
**streams the file content back to the client**. It acts as a stable,
URL-masking front door to documents held in S3, backed by the UN Digital
Library (UNDL) MongoDB metadata.

Deployed as a container on **AWS Lambda** (via the AWS Lambda Web Adapter),
exposed through a **Lambda Function URL**, and fronted by **CloudFront** for a
stable public endpoint.

---

## Endpoint

```
GET /<language>/<symbol>
```

| Parameter  | Description                                   | Example     |
|------------|-----------------------------------------------|-------------|
| `language` | Lowercase language code                       | `en`        |
| `symbol`   | Document symbol (may contain slashes/spaces)  | `A/79/PV.1` |

**Valid language codes:** `ar`, `en`, `fr`, `ru`, `es`, `zh`, `ot`

- The symbol may contain slashes (`A/79/PV.1`) and other characters such as
  spaces and parentheses (`A/81/6 (SECT. 3)/ADD.4`); clients should
  URL-encode the path.
- The external code `ot` ("other") maps to `DE` in the database.

### Responses

| Status | Meaning                                                        |
|--------|----------------------------------------------------------------|
| 200    | Document found — file content is streamed back to the client   |
| 400    | Invalid language code (HTML error page)                        |
| 404    | Document or language not found (HTML error page)               |
| 502    | Document exists but its file could not be fetched from origin  |

On success the response includes a `Content-Disposition: inline; filename="..."`
header so browsers offer a sensible filename on download. The filename comes
from the document's `filename` field, or is derived as
`<symbol-with-underscores>-<LANG>.pdf` when that field is absent.

### Example

```bash
curl -v https://<cloudfront-domain>/en/A/79/PV.1
# HTTP/1.1 200 OK
# Content-Type: application/pdf
# Content-Disposition: inline; filename="A_79_PV.1-EN.pdf"
# Transfer-Encoding: chunked
```

### Health check

```
GET /health   ->   200 {"status": "ok"}
```

---

## How it works

1. **Validate** the language code against the allowed set (400 if invalid).
2. **Map** `ot` -> `DE`; otherwise uppercase the language for the DB query.
3. **Look up** the document in MongoDB (case-insensitive on the symbol):
   ```python
   db.files.find_one(
       {"identifiers.value": symbol, "languages": language},
       collation=Collation(locale="en", strength=2),
   )
   ```
   Returns 404 if no match.
4. **Fetch** the file from the origin URL (`https://` + the document's `uri`).
   Returns 502 if the origin cannot be reached.
5. **Stream** the file back to the client in 64 KB chunks using
   `Transfer-Encoding: chunked`. The origin URL is never exposed to the
   client.
6. **Log** every request to the `request_logs` collection.

### Why streaming (not redirect or buffered proxy)

- A **302 redirect** would expose the underlying S3/hash URL to the client.
- **Buffering** the whole file in the Lambda response hits the 6 MB
  synchronous payload limit, which fails for the many large documents
  (some exceed 100 MB).
- **Streaming** keeps the origin URL hidden *and* supports large files,
  since the Lambda Function URL streams the response as it is read.

---

## Architecture

```
Client
  |  GET /en/A/79/PV.1
  v
CloudFront  (stable public URL; pass-through, no caching)
  |
  v
Lambda Function URL  (InvokeMode: RESPONSE_STREAM)
  |
  v
Lambda container: Flask + Gunicorn + AWS Lambda Web Adapter
  |  - looks up metadata in MongoDB
  |  - fetches the file from S3 origin
  |  - streams bytes back
  v
MongoDB (UNDL)   +   S3 (document files)
```

Key points:

- **CloudFront** provides a stable endpoint. Because the raw Function URL
  changes whenever the Lambda infrastructure is recreated, CloudFront is the
  URL handed to consumers so future changes/rollbacks stay invisible to them.
  It is configured for pass-through (CachingDisabled +
  AllViewerExceptHostHeader) so every request reaches the Lambda and is
  logged.
- **Lambda Function URL** with `RESPONSE_STREAM` invoke mode enables response
  streaming (required for large files; not supported by API Gateway).
- **AWS Lambda Web Adapter** runs the unmodified Flask/Gunicorn app on Lambda.
  `AWS_LWA_INVOKE_MODE=response_stream` turns on streaming.
- **Gunicorn `--timeout 120`** matches the Lambda timeout; the 30s default
  would kill the worker mid-stream on large files and truncate the download.

---

## Configuration

Configuration is loaded from **AWS SSM Parameter Store** at startup. The only
environment variable is the environment selector:

| Variable    | Required | Description                                              |
|-------------|----------|----------------------------------------------------------|
| `FLASK_ENV` | No       | `development` or `production` (defaults to `production`) |

The environment selects which SSM parameter and database are used:

| `FLASK_ENV`   | SSM parameter (connection string) | MongoDB database |
|---------------|-----------------------------------|------------------|
| `development` | `devISSU-admin-connect-string`    | `dev_undlFiles`  |
| `production`  | `prodISSU-admin-connect-string`   | `undlFiles`      |

The Lambda execution role must have `ssm:GetParameter` for the relevant
parameter (both are granted in the SAM template).

---

## MongoDB collections

### `files` (existing — read)

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

The symbol lookup relies on a **collation-aware index** on
`identifiers.value` (case-insensitive, `locale=en`, `strength=2`) so symbols
match regardless of case (e.g. `RESUMPTION` vs `Resumption`).

### `request_logs` (written)

One document is written per request for analytics.

```json
{
  "timestamp": "2025-02-08T08:10:25.796Z",
  "ip": "192.168.1.10",
  "language": "en",
  "symbol": "A/79/PV.1",
  "status_code": 200,
  "response_time_ms": 12
}
```

The `ip` is taken from the first entry of `X-Forwarded-For` (set by
CloudFront/Lambda), falling back to the remote address. Logging failures are
caught and never affect the response.

> Analytics tooling for this collection lives in the separate
> `undocs_log_stats` project.

---

## Local development

### Prerequisites

- Python 3.12+
- AWS credentials configured locally with `ssm:GetParameter` access to the
  relevant connection-string parameter (the app calls SSM even locally)

### Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows PowerShell: venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Run

```bash
# Windows PowerShell
$env:FLASK_ENV = "development"
python -m flask --app wsgi:app run

# then, in another shell:
curl http://127.0.0.1:5000/health
```

> Note: `development` connects to `dev_undlFiles`. Some documents exist only
> in the production database, and some dev records point at a private bucket
> that returns 403 (surfacing as a 502). Test with symbols known to exist in
> the environment you are running against.

### Run tests

Unit tests mock all AWS and MongoDB calls — no live connections required:

```bash
pytest tests/test_health.py tests/test_routes.py tests/test_middleware.py -v
```

The database integration tests (`tests/test_db.py`) require a reachable
MongoDB and are not part of the unit run.

### Smoke-testing a list of documents

`scripts/smoke_test_endpoints.py` checks a list of paths against a deployed
endpoint and writes a CSV report (status, response time, bytes, filename):

```bash
python scripts/smoke_test_endpoints.py \
    --base-url https://<cloudfront-domain> \
    --input scripts/your_paths.txt \
    --output report.csv
```

---

## Deployment (AWS SAM)

CI/CD is handled by GitHub Actions:

- **`deploy-dev.yml`** — deploys to dev on push to `main`.
- **`deploy-prod.yml`** — deploys to prod when a semver release is published.

Both workflows authenticate to ECR Public (to avoid the Lambda-adapter image
rate limit) before `sam build`.

### Manual deploy

```bash
cd sam
sam build --use-container --parameter-overrides FunctionArchitecture=x86_64
sam deploy --config-env dev  --parameter-overrides FunctionArchitecture=x86_64
sam deploy --config-env prod --parameter-overrides FunctionArchitecture=x86_64
```

### Stacks and endpoints

| Environment | Stack name              | Public endpoint              |
|-------------|-------------------------|------------------------------|
| dev         | `undocs-undl-api`       | CloudFront dev distribution  |
| prod        | `undocs-undl-api-prod`  | CloudFront prod distribution |

The Lambda Function URL for each environment is available as the `FunctionUrl`
stack output. Consumers should be given the **CloudFront** URL, not the raw
Function URL.

### CloudFront (currently managed manually)

The CloudFront distributions are configured in the AWS console (not yet in the
SAM template) with:

- **Origin:** the Lambda Function URL host (no `https://`, no trailing `/`)
- **Cache policy:** CachingDisabled (pass-through, preserves logging)
- **Origin request policy:** AllViewerExceptHostHeader (required for Function
  URL origins; forwarding the viewer Host header causes 403s)

When a deploy changes the Function URL, repoint the CloudFront origin at the
new host. Consumers keep using the unchanged CloudFront domain.

### Cost monitoring

Resources are tagged `Project=undocs-undl-api` and `Environment=<env>` for cost
allocation. SAM-managed resources are tagged via the template and
`samconfig.toml`; manually-created resources (CloudFront, ECR) must be tagged
in the console. Activate the tags under **Billing > Cost allocation tags** to
break costs down in Cost Explorer.

---

## Project structure

```
undocs-undl-api/
├── app/
│   ├── __init__.py        # Flask app factory; before/after-request hooks (IP capture, logging)
│   ├── config.py          # Loads Mongo connection from AWS SSM (dev/prod switch)
│   ├── db.py              # PyMongo client, document lookup, request logging
│   ├── routes.py          # Resolve + stream endpoint, error rendering
│   └── templates/
│       └── error.html     # Shared HTML error page (400/404/502)
├── tests/                 # pytest unit + integration tests
├── scripts/               # Endpoint smoke-test utility (not part of the app)
├── sam/
│   ├── template.yaml      # SAM/CloudFormation template
│   └── samconfig.toml     # Per-environment deploy config
├── .github/workflows/     # CI/CD (deploy-dev, deploy-prod, test)
├── wsgi.py                # Gunicorn entry point (create_app)
├── Dockerfile             # Lambda container image (Flask + Gunicorn + LWA)
└── requirements.txt
```

---

## Operational notes & known limitations

- **Very large files + slow clients:** a request must complete within the
  120s Lambda/Gunicorn timeout. The largest documents (100+ MB) stream in
  well under this on a normal connection, but a very slow client on the
  largest files could approach the limit.
- **Function URL auth is `NONE`:** the endpoint is public. Concurrency is
  capped via `ReservedConcurrentExecutions` (default 100) as a safeguard,
  since Function URLs have no built-in throttling.
- **`is_ip_allowed` in `db.py`** is a leftover stub retained only for test
  compatibility; there is no IP allowlisting in the request path.
- **CloudFront and ECR are not yet in infrastructure-as-code** — they are
  managed in the console and tracked as a follow-up item.
