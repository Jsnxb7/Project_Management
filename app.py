from functools import wraps
from datetime import timedelta
import os

from flask import Flask, render_template, session, redirect, url_for, request, make_response
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager

from config import Config


bcrypt = Bcrypt()
jwt = JWTManager()


def protected_page(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login_page"))

        response = make_response(view(*args, **kwargs))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return wrapper


def create_app():
    app = Flask(__name__)

    # Load app configuration
    app.config.from_object(Config)

    # Session configuration
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Enable secure cookies only in production
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"

    # Optional but recommended for production
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"

    # CORS
    # If frontend and backend are served from the same Flask app, this is not strictly needed.
    # Keeping it enabled for API access.
    CORS(app, supports_credentials=True)

    # Initialize extensions
    bcrypt.init_app(app)
    jwt.init_app(app)

    # Import blueprints
    from routes.auth_routes import auth_bp, TOKEN_BLOCKLIST
    from routes.project_routes import project_bp
    from routes.task_routes import task_bp
    from routes.dashboard_routes import dashboard_bp
    from routes.comment_routes import comment_bp
    from routes.notification_routes import notification_bp
    from routes.activity_routes import activity_bp
    from routes.attachment_routes import attachment_bp
    from routes.user_routes import user_bp
    from routes.portal_routes import portal_bp
    from routes.organization_routes import organization_bp
    from routes.milestone_routes import milestone_bp
    from routes.team_routes import team_bp

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        return jwt_payload.get("jti") in TOKEN_BLOCKLIST

    # Register API blueprints
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(project_bp, url_prefix="/api/projects")
    app.register_blueprint(task_bp, url_prefix="/api/tasks")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.register_blueprint(comment_bp, url_prefix="/api")
    app.register_blueprint(notification_bp, url_prefix="/api/notifications")
    app.register_blueprint(activity_bp, url_prefix="/api/activity")
    app.register_blueprint(attachment_bp, url_prefix="/api")
    app.register_blueprint(user_bp, url_prefix="/api/users")
    app.register_blueprint(portal_bp, url_prefix="/api/portal")
    app.register_blueprint(organization_bp, url_prefix="/api/organizations")
    app.register_blueprint(milestone_bp, url_prefix="/api")
    app.register_blueprint(team_bp, url_prefix="/api/teams")

    @app.after_request
    def no_cache_for_app_pages(response):
        protected_prefixes = (
            "/dashboard",
            "/projects",
            "/project/",
            "/notifications",
            "/profile",
            "/my-tasks",
            "/portal",
            "/organizations",
            "/teams",
        )

        if request.path.startswith(protected_prefixes):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response

    # Frontend routes
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/login")
    def login_page():
        if session.get("user_id"):
            return redirect(url_for("dashboard_page"))
        return render_template("login.html")

    @app.route("/signup")
    def signup_page():
        if session.get("user_id"):
            return redirect(url_for("dashboard_page"))
        return render_template("signup.html")

    @app.route("/dashboard")
    @protected_page
    def dashboard_page():
        return render_template("dashboard.html")

    @app.route("/projects")
    @protected_page
    def projects_page():
        return render_template("projects.html")

    @app.route("/my-tasks")
    @protected_page
    def my_tasks_page():
        return render_template("my_tasks.html")

    @app.route("/project/<project_id>/tasks")
    @protected_page
    def task_board_page(project_id):
        return render_template("task_board.html", project_id=project_id)

    @app.route("/notifications")
    @protected_page
    def notifications_page():
        return render_template("notifications.html")

    @app.route("/profile")
    @protected_page
    def profile_page():
        return render_template("profile.html")

    @app.route("/portal/users")
    @protected_page
    def portal_users_page():
        return render_template("portal_users.html")

    @app.route("/portal/import-users")
    @protected_page
    def portal_import_users_page():
        return render_template("portal_import_users.html")

    @app.route("/teams")
    @protected_page
    def teams_page():
        return render_template("teams.html")

    @app.route("/teams/<team_id>")
    @protected_page
    def team_detail_page(team_id):
        return render_template("team_detail.html", team_id=team_id)

    @app.route("/organizations")
    @protected_page
    def organizations_page():
        return render_template("organizations.html")

    @app.route("/organizations/<org_id>")
    @protected_page
    def organization_detail_page(org_id):
        return render_template("organization_detail.html", org_id=org_id)

    @app.route("/organizations/<org_id>/config")
    @protected_page
    def organization_config_page(org_id):
        return render_template("organization_config.html", org_id=org_id)

    @app.route("/project/<project_id>/manage")
    @protected_page
    def manage_project_page(project_id):
        return render_template("manage_project.html", project_id=project_id)

    @app.route("/project/<project_id>/analytics")
    @protected_page
    def project_analytics_page(project_id):
        return render_template("project_analytics.html", project_id=project_id)

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)