import os
from flask import Flask
from datetime import timedelta
from dotenv import load_dotenv
from app.complaints import complaints_bp

load_dotenv()


def create_app():
    app = Flask(__name__)

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable must be set.")

    app.config.update(
    SECRET_KEY=secret_key,
    SESSION_COOKIE_NAME="scms_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get(
        "SESSION_COOKIE_SECURE", "false"
    ).lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(
        minutes=int(os.environ.get("SESSION_LIFETIME_MINUTES", "30"))
    ),
    SESSION_REFRESH_EACH_REQUEST=True,
)

    from app.auth.routes import auth_bp
    from app.users.routes import users_bp
    from app.roles.routes import roles_bp
    from process import processing_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(processing_bp)
    app.register_blueprint(complaints_bp)
    
    return app
