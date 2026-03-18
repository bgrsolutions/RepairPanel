# IRONCore RepairPanel — Setup Guide

## Prerequisites

| Component   | Version  | Notes                                    |
|-------------|----------|------------------------------------------|
| Python      | 3.11+    | Required                                 |
| PostgreSQL  | 15+      | Runs via Docker (`docker-db-1`)          |
| Redis       | 7+       | Optional — needed for future Celery jobs |

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> /home/RepairPanel
cd /home/RepairPanel

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and configure environment
cp .env.example .env
# Edit .env — set at minimum SECRET_KEY and DATABASE_URL

# 5. Run database migrations
flask db upgrade

# 6. Seed initial data (optional)
flask seed

# 7. Start the development server
flask run
```

---

## Environment Variables

All configuration is loaded from `.env` via `python-dotenv`.
See `.env.example` for the full template.

### Required

| Variable       | Description                          | Example                                                 |
|----------------|--------------------------------------|---------------------------------------------------------|
| `SECRET_KEY`   | Flask session secret (random string) | `openssl rand -hex 32`                                  |
| `DATABASE_URL` | PostgreSQL connection string         | `postgresql://ironcore:ironcore@127.0.0.1:5432/ironcore`|

### Locale & Timezone

| Variable              | Default | Description                |
|-----------------------|---------|----------------------------|
| `BABEL_DEFAULT_LOCALE`| `en`    | Default UI language        |
| `SUPPORTED_LOCALES`   | `en,es` | Comma-separated locale list|
| `TIMEZONE`            | `UTC`   | Application timezone       |

### Email / SMTP

The app supports two email transports:

- **`log`** (default) — emails are written to stdout / application log. Good for development.
- **`smtp`** — emails are sent via an SMTP server. Required for production notifications.

| Variable                  | Default     | Description                        |
|---------------------------|-------------|------------------------------------|
| `MAIL_TRANSPORT`          | `log`       | `log` or `smtp`                    |
| `MAIL_ENABLED`            | `false`     | Master switch for email sending    |
| `MAIL_SERVER`             | `localhost` | SMTP host                          |
| `MAIL_PORT`               | `587`       | SMTP port                          |
| `MAIL_USE_TLS`            | `true`      | Use STARTTLS                       |
| `MAIL_USE_SSL`            | `false`     | Use implicit SSL                   |
| `MAIL_USERNAME`           |             | SMTP login                         |
| `MAIL_PASSWORD`           |             | SMTP password                      |
| `MAIL_DEFAULT_SENDER`     |             | From address for outgoing emails   |
| `MAIL_DEFAULT_SENDER_NAME`|             | Display name for From header       |

To enable SMTP in production:

```env
MAIL_TRANSPORT=smtp
MAIL_ENABLED=true
MAIL_SERVER=smtp.yourprovider.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your@email.com
MAIL_PASSWORD=yourpassword
MAIL_DEFAULT_SENDER=your@email.com
MAIL_DEFAULT_SENDER_NAME=IRONCore RepairPanel
```

### IMEICheck API

The application integrates with [imeicheck.net](https://imeicheck.net) for automatic device information lookup during intake. When enabled, staff can scan or type an IMEI and auto-fill brand, model, storage, colour, FMI status, and more.

| Variable               | Default                       | Description                        |
|------------------------|-------------------------------|-------------------------------------|
| `IMEICHECK_ENABLED`    | `false`                       | Enable IMEI lookups                 |
| `IMEICHECK_API_KEY`    |                               | Bearer token API key                |
| `IMEICHECK_API_URL`    | `https://api.imeicheck.net`   | API base URL                        |
| `IMEICHECK_SERVICE_ID` | `12`                          | Service type for checks (see below) |
| `IMEICHECK_TIMEOUT`    | `10`                          | Request timeout (seconds)           |

**`IMEICHECK_SERVICE_ID`** determines what type of device information is returned. Each service ID corresponds to a specific check type (e.g., Apple Info, Samsung Info). To find available services for your account, you can use the `list_services()` helper in `app/services/imei_lookup_service.py` or call `GET /v1/services` directly.

To enable:

1. Register at [imeicheck.net](https://imeicheck.net) and obtain an API key.
2. Whitelist your server IP in the [API Manager](https://imeicheck.net/developer-api).
3. Set the environment variables:

```env
IMEICHECK_ENABLED=true
IMEICHECK_API_KEY=your_api_key_here
IMEICHECK_SERVICE_ID=12
```

4. Restart the application. IMEI lookup buttons will appear on the intake and ticket forms.

When lookup fails, staff can always proceed with manual device entry. See `docs/PHASE18_DEVICE_INTELLIGENCE.md` for detailed error codes and troubleshooting.

> **Note:** When the API is disabled or unavailable, staff can always enter device details manually — the lookup is a convenience, not a requirement.

### Redis / Celery (Future)

| Variable            | Default                     | Description         |
|---------------------|-----------------------------|---------------------|
| `REDIS_URL`         | `redis://localhost:6379/0`  | Redis connection    |
| `CELERY_BROKER_URL` | Same as `REDIS_URL`         | Celery broker       |

These are reserved for future background job support and are not required for the current version.

---

## Database

PostgreSQL runs in Docker via `docker-db-1`:

```bash
# Start the database
docker compose up -d

# Connection (default)
# Host: 127.0.0.1
# Port: 5432
# User: ironcore
# Pass: ironcore
# DB:   ironcore
```

### Migrations

```bash
flask db upgrade          # Apply pending migrations
flask db migrate -m "msg" # Generate a new migration
flask db downgrade        # Roll back one migration
```

---

## Config Validation

On startup, the application runs automatic configuration checks
(`app/utils/config_check.py`). It logs warnings for:

- Missing `DATABASE_URL` or `SECRET_KEY`
- `MAIL_ENABLED=true` without SMTP credentials
- `IMEICHECK_ENABLED=true` without an API key

These are **warnings only** — the app will still start, but affected features may not work correctly.

---

## Production Deployment

1. Set `FLASK_ENV=production`
2. Use a strong, random `SECRET_KEY`
3. Use `gunicorn` or similar WSGI server:

```bash
gunicorn -w 4 -b 0.0.0.0:8000 "app:create_app()"
```

4. Configure a reverse proxy (nginx) in front of gunicorn
5. Ensure `.env` file permissions are restricted: `chmod 600 .env`
