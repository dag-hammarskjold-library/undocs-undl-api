FROM python:3.12-slim

# Lambda Web Adapter: lets this same image run unchanged on AWS Lambda.
# Placed in /opt/extensions/, so it's a no-op outside Lambda (local docker
# run, ECS, App Runner all keep working exactly as before).
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

# Create a non-root user to run the application
RUN useradd --create-home appuser
WORKDIR /home/appuser

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ app/
COPY wsgi.py .

# Switch to non-root user
USER appuser

# Expose Gunicorn port
EXPOSE 8000

# Start Gunicorn with (2 * nproc) + 1 workers.
# The shell form is used so the expression is evaluated at runtime.
CMD gunicorn --workers $((2 * $(nproc) + 1)) \
             --bind 0.0.0.0:8000 \
             --access-logfile - \
             --error-logfile - \
             wsgi:app
