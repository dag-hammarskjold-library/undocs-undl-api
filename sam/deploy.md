# Deploying undocs-undl-api to Lambda via SAM

This adds a serverless deployment path (Lambda + API Gateway) alongside the
existing repo, using the following assumptions:

- Aiming for baseline load of 1-2 million hits per month, but need a more 
  picture of the total traffic.
- Cold-start latency is acceptable during an unplanned outage affecting ODS, 
  so no provisioned concurrency is configured by default.
- Detailed monitoring specs (dashboards, alarms, the ToR's "AWS usage and
  bandwidth" reporting) are a follow-up; this stack ships with the metrics
  Lambda, API Gateway, and CloudWatch already provide by default.


## What the SAM template does

- Builds the existing Dockerfile as a Lambda container image (`PackageType: Image`).
- Sets `PORT=8000` so the adapter knows where Gunicorn is listening, and
  `AWS_LWA_READINESS_CHECK_PATH=/health` so the adapter uses the app's
  existing health endpoint to know when the container is ready.
- Grants the function `ssm:GetParameter` on both the prod and dev SSM
  parameters `app/config.py` already reads, matching the permission the
  ECS task role has today.
- Exposes an HTTP API with two routes: `GET /health` and
  `GET /{language}/{symbol+}`, matching the existing Flask routes 1:1
  (the `symbol+` greedy path variable is required since document symbols
  contain slashes, e.g. `A/79/PV.1`).
- Sets HTTP API throttling to 1000 burst / 500 requests-per-second, well
  above what a 1-2M/month baseline needs on average, without provisioning
  fixed capacity for it.
- Leaves `ProvisionedConcurrentExecutions` at 0 by default (see assumptions
  above); it's a template parameter, so it can be raised later with a
  one-line `sam deploy` override if a stricter latency target is set.

## Deploy steps

From the repo root, with the SAM CLI and Docker installed:

```bash
# one-time: build the container image and run sam deploy interactively
# to confirm the stack name, region, and capabilities
cd sam
sam build --use-container
sam deploy --guided
```

After the first guided deploy, `samconfig.toml` has your answers saved, so
subsequent deploys are just:

```bash
sam build --use-container
sam deploy
```

The stack output `ApiEndpoint` is the `<base_url>` for the ToR's
`<base_url>/<language>/<document_symbol>` pattern. That's what gets handed
to the DGACM/UNDOCS team to wire into their failover switch.

## Before the August simulation

Run a load test against the deployed `ApiEndpoint` at the 1-2M/month
baseline rate (and some headroom above it) to confirm Gunicorn worker
count, Mongo connection handling, and the throttling limits above hold up.
Adjust `ThrottlingBurstLimit`/`ThrottlingRateLimit` or
`ProvisionedConcurrentExecutions` afterward if the results call for it.

## Monitoring (follow-up)

Lambda and the HTTP API already emit invocation count, error count,
duration, and throttle metrics to CloudWatch with no extra configuration.
Once the detailed monitoring spec is available, the natural next additions
are a CloudWatch dashboard and alarms on error rate and throttling, added
to `template.yaml` as `AWS::CloudWatch::Alarm` resources.