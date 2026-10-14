
from app import create_app


def test_app_creation():
    app = create_app()

    assert app is not None
    assert app.testing is False
