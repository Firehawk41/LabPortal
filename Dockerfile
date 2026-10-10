FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY slim_lab_portal ./slim_lab_portal
RUN pip install --no-cache-dir .

EXPOSE 8000

# Apply portal migrations, then serve. Proxy headers are trusted so url_for() builds
# https:// links behind Caddy / Render.
CMD ["sh", "-c", "alembic -c slim_lab_portal/alembic.ini upgrade head && uvicorn --factory slim_lab_portal.main:create_app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
