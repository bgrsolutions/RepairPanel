from flask import Flask, g, redirect, request, session
from flask_babel import get_locale
from dotenv import load_dotenv

from app.blueprints.auth.routes import auth_bp
from app.blueprints.core.routes import core_bp
from app.blueprints.tickets.routes import tickets_bp
from app.blueprints.intake.routes import intake_bp
from app.blueprints.customers.routes import customers_bp
from app.blueprints.diagnostics.routes import diagnostics_bp
from app.blueprints.quotes.routes import quotes_bp
from app.blueprints.public_portal.routes import public_portal_bp
<<<<<<< codex/create-project-governance-documentation-u004qc
from app.blueprints.inventory.routes import inventory_bp
from app.blueprints.suppliers.routes import suppliers_bp
from app.blueprints.orders.routes import orders_bp
=======
>>>>>>> main
from app.config import Config
from app.extensions import babel, db, login_manager, migrate
from app import models  # noqa: F401

load_dotenv()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    babel.init_app(app, locale_selector=_select_locale)

    app.register_blueprint(auth_bp)
    app.register_blueprint(core_bp)
    app.register_blueprint(tickets_bp)
    app.register_blueprint(intake_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(diagnostics_bp)
    app.register_blueprint(quotes_bp)
    app.register_blueprint(public_portal_bp)
<<<<<<< codex/create-project-governance-documentation-u004qc
    app.register_blueprint(inventory_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(orders_bp)
=======
>>>>>>> main

    @app.before_request
    def inject_locale():
        g.current_locale = str(get_locale())

    @app.context_processor
    def utility_processor():
        return {
            "current_locale": str(get_locale()),
            "supported_locales": app.config["SUPPORTED_LOCALES"],
        }

    @app.get("/set-language/<locale>")
    def set_language(locale: str):
        if locale in app.config["SUPPORTED_LOCALES"]:
            session["locale"] = locale
        return redirect(request.referrer or "/")

    return app


def _select_locale():
    from flask_login import current_user

    if "locale" in session:
        return session["locale"]

    if current_user.is_authenticated and getattr(current_user, "preferred_language", None):
        return current_user.preferred_language

    return request.accept_languages.best_match(["en", "es"]) or "en"
