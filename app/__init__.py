
from flask import Flask


def create_app():
    app = Flask(__name__)

    from app.auth.routes import auth_bp
    from app.users.routes import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)

    return app
