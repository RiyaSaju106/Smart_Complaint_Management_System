
import os
from flask import Flask


def create_app():
    app = Flask(__name__)

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable must be set.")

    app.config["SECRET_KEY"] = secret_key

    from app.auth.routes import auth_bp
    from app.users.routes import users_bp
    from app.roles.routes import roles_bp
    from process import processing_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(processing_bp)

    return app
