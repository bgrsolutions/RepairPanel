# IRONCore (Phase 1)

## Quick Start (Local)
1. Install deps:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Create env file:
   ```bash
   cp .env.example .env
   ```
3. Start PostgreSQL (Docker compose path):
   ```bash
   docker compose -f docker/docker-compose.yml up -d db
   ```
4. Run migrations:
   ```bash
   FLASK_APP=manage.py flask db upgrade
   ```
5. Seed demo data:
   ```bash
   FLASK_APP=manage.py flask seed
   ```
6. Run app:
   ```bash
   FLASK_APP=manage.py flask run --host=0.0.0.0 --port=5000
   ```

Default demo login:
- email: `admin@ironcore.local`
- password: `admin1234`
