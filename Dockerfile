FROM python:3.12-slim

# Explicitly request amd64 for the adapter too
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ app/
COPY wsgi.py .

# Expose Gunicorn port
EXPOSE 8000


# Start Gunicorn.
# --timeout 120 matches the Lambda function timeout. The default of 30s is
# too low for streaming large files (>100 MB), where the transfer duration
# exceeds 30s and the worker would otherwise be killed mid-stream, truncating
# the response.
CMD ["gunicorn", "--workers", "2", "--timeout", "120", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
