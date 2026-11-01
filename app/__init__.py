
import os
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask

load_dotenv()


def create_app():
    app = Flask(__name__)

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY environment variable must be set."
        )

    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_NAME="scms_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get(
            "SESSION_COOKIE_SECURE", "false"
        ).lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(
            minutes=int(
                os.environ.get("SESSION_LIFETIME_MINUTES", "30")
            )
        ),
        SESSION_REFRESH_EACH_REQUEST=True,
    )

    app.config["ATTACHMENT_UPLOAD_DIR"] = os.environ.get(
        "ATTACHMENT_UPLOAD_DIR",
        os.path.join(app.instance_path, "attachments"),
    )

    app.config["ATTACHMENT_MAX_BYTES"] = int(
        os.environ.get(
            "ATTACHMENT_MAX_BYTES",
            str(5 * 1024 * 1024),
        )
    )

    app.config["ATTACHMENT_ALLOWED_EXTENSIONS"] = tuple(
        item.strip().lower()
        for item in os.environ.get(
            "ATTACHMENT_ALLOWED_EXTENSIONS",
            "pdf,png,jpg,jpeg",
        ).split(",")
        if item.strip()
    )

    # Import route modules before registering their blueprints.
    from app.auth.routes import auth_bp
    from app.users.routes import users_bp
    from app.roles.routes import roles_bp
    from app.complaints import complaints_bp
    from app.complaints import routes as complaints_routes
    from app.categories import categories_bp
    from process import processing_bp
    from app.notifications.routes import notifications_bp
    from app.tracking import tracking_bp
    from app.tracking import routes as tracking_routes
    from app.tracking import search as tracking_search
    from app.ui import ui_bp            

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(complaints_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(processing_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(tracking_bp)
    app.register_blueprint(ui_bp)

    return app
