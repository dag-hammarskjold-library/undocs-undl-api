FROM python:3.12-slim

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

# Start Gunicorn with a conservative worker count for burst-friendly scaling.
# The shell form is used so the expression is evaluated at runtime.
CMD gunicorn --workers $((2 * $(nproc) + 1)) \
             --worker-class gthread \
             --threads 8 \
             --worker-connections 1000 \
             --timeout 30 \
             --keep-alive 30 \
             --bind 0.0.0.0:8000 \
             --access-logfile - \
             --error-logfile - \
             wsgi:app
