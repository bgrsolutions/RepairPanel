from app import create_app


def test_app_factory():
    app = create_app()
    assert app is not None
    assert "auth" in app.blueprints
    assert "core" in app.blueprints
    assert "tickets" in app.blueprints
