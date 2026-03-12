from app import create_app


def test_app_factory():
    app = create_app()
    assert app is not None
    assert "auth" in app.blueprints
    assert "core" in app.blueprints
    assert "tickets" in app.blueprints
    assert "intake" in app.blueprints
    assert "customers" in app.blueprints
    assert "diagnostics" in app.blueprints
    assert "quotes" in app.blueprints
    assert "public_portal" in app.blueprints
    assert "inventory" in app.blueprints
    assert "suppliers" in app.blueprints
    assert "orders" in app.blueprints
    assert "reports" in app.blueprints
    assert "notifications" in app.blueprints
    assert "settings" in app.blueprints
    assert "integrations" in app.blueprints
