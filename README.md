# IRONCore (Phase 1)

## Quick Start (Local Host + Dockerized PostgreSQL)
1. Install deps:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Create env file:
   ```bash
   cp .env.example .env
   ```
3. Start PostgreSQL only (Docker compose):
   ```bash
   docker compose -f docker/docker-compose.yml up -d db
   ```
4. Run migrations from host:
   ```bash
   FLASK_APP=manage.py flask db upgrade
   ```
5. Seed demo data from host:
   ```bash
   FLASK_APP=manage.py flask seed
   ```
6. Run Flask from host:
   ```bash
   FLASK_APP=manage.py flask run --host=0.0.0.0 --port=5000
   ```

## Default local DATABASE_URL
For host-based Flask execution, use:

```env
DATABASE_URL=postgresql://ironcore:ironcore@127.0.0.1:5432/ironcore
```

> `db` hostname is only valid for container-to-container networking when Flask itself runs inside Docker compose.

## Default demo login
- email: `admin@ironcore.com`
- password: `admin1234`

## Notes
- `flask seed` is idempotent and deterministic for demo auth setup.
- Legacy demo admins (`admin@ironcore.local`, `admin@ironcore.test`) are normalized to `admin@ironcore.com` during seed.
