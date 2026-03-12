from app import create_app
from app.extensions import db
from app.services.seed_service import seed_phase1_data

app = create_app()


@app.shell_context_processor
def shell_context():
    return {"db": db}


@app.cli.command("seed")
def seed_command():
    """Seed minimal Phase 1 demo data."""
    seed_phase1_data()
    print("Phase 1 seed completed.")
