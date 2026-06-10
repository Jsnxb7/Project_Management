from functools import wraps
from datetime import timedelta
import os

from flask import Flask, render_template, session, redirect, url_for, request, make_response
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from socket_events import init_socket_events, socketio

from config import Config
from services.page_access import can_access_page, default_page_for_role


bcrypt = Bcrypt()
jwt = JWTManager()


def protected_page(view=None, *, path=None):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login_page"))

            role = session.get("hrms_role") or session.get("portal_role") or session.get("role")
            requested_path = path or request.path
            if not can_access_page(role, requested_path):
                return redirect(url_for(default_page_for_role(role)))

            response = make_response(view_func(*args, **kwargs))
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        return wrapper

    if view is None:
        return decorator
    return decorator(view)


def create_app():
    app = Flask(__name__)

    # Load app configuration
    app.config.from_object(Config)
    app.config["TEMPLATES_AUTO_RELOAD"] = True

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
    from routes.notification_routes import notification_bp
    from routes.activity_routes import activity_bp
    from routes.user_routes import user_bp
    from routes.portal_routes import portal_bp
    from routes.hrms_routes import hrms_bp
    from routes.recruitment_routes import recruitment_bp
    from routes.theme_routes import theme_bp
    from routes.ai_interview_routes import ai_interview_bp
    from routes.candidate_pipeline_routes import candidate_pipeline_bp
    from routes.human_interview_routes import human_interview_bp
    from routes.interview_pages_v2_routes import interview_pages_v2_bp

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        return jwt_payload.get("jti") in TOKEN_BLOCKLIST

    from routes.live_room_routes import live_room_bp

    # Register API blueprints
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(notification_bp, url_prefix="/api/notifications")
    app.register_blueprint(activity_bp, url_prefix="/api/activity")
    app.register_blueprint(user_bp, url_prefix="/api/users")
    app.register_blueprint(portal_bp, url_prefix="/api/portal")
    app.register_blueprint(hrms_bp, url_prefix="/api/hrms")
    app.register_blueprint(recruitment_bp, url_prefix="/api/recruitment")
    app.register_blueprint(theme_bp, url_prefix="/api/theme")
    app.register_blueprint(ai_interview_bp, url_prefix="/api/ai-interview")
    app.register_blueprint(human_interview_bp, url_prefix="/api/human-interview")
    app.register_blueprint(candidate_pipeline_bp, url_prefix="/api/candidate-pipeline")
    app.register_blueprint(live_room_bp, url_prefix="/api/live")
    app.register_blueprint(interview_pages_v2_bp)

    init_socket_events(app)
    from database.db import local_cache_status, start_local_cache_warmup
    start_local_cache_warmup()

    @app.get("/api/cache/status")
    def cache_status_endpoint():
        return {"success": True, "data": local_cache_status()}

    @app.after_request
    def no_cache_for_app_pages(response):
        protected_prefixes = (
            "/dashboard",
            "/notifications",
            "/messages",
            "/profile",
            "/portal",
            "/employees",
            "/attendance",
            "/payroll",
            "/performance",
            "/recruitment",
            "/candidate-pipeline",
            "/interviews",
            "/voice-interview",
            "/themes",
            "/candidate-process",
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
        return render_template("login.html")

    @app.route("/signup")
    def signup_page():
        return render_template("signup.html")

    @app.route("/dashboard")
    @protected_page
    def dashboard_page():
        return render_template("dashboard.html")

    @app.route("/employees")
    @protected_page
    def employees_page():
        return render_template("employees.html")

    @app.route("/attendance")
    @protected_page
    def attendance_page():
        return render_template("attendance.html")

    @app.route("/payroll")
    @protected_page
    def payroll_page():
        return render_template("payroll.html")

    @app.route("/performance")
    @protected_page
    def performance_page():
        return render_template("performance.html")


    @app.route("/careers")
    def careers_page():
        return render_template("careers.html")

    @app.route("/apply")
    def apply_page():
        return render_template("apply.html")

    @app.route("/recruitment")
    @protected_page
    def recruitment_page():
        return render_template("recruitment.html")

    @app.route("/applications")
    @protected_page
    def applications_page():
        return render_template("applications.html")

    @app.route("/candidate-pipeline")
    @protected_page
    def candidate_pipeline_page():
        return render_template("candidate_pipeline.html")

    @app.route("/second-round-candidates")
    @protected_page
    def second_round_candidates_page():
        return redirect(url_for("candidate_pipeline_page"))

    @app.route("/voice-interview")
    @protected_page
    def voice_interview_page():
        return render_template("voice_interview.html")

    @app.route("/interviews")
    @protected_page
    def interviews_page():
        return render_template("interviews.html")

    @app.route("/candidate-process")
    @protected_page
    def candidate_process_page():
        return render_template("candidate_process.html")

    @app.route("/interview-room/<room_code>")
    def interview_room_page(room_code):
        role = (session.get("hrms_role") or session.get("portal_role") or session.get("role") or "").lower().replace(" ", "_")
        controller_roles = {
            "super_user", "superuser", "controller", "admin", "hr", "hr_staff", "org_head",
            "management_admin", "hr_director", "hr_manager", "hr_business_partner", "hr_recruiter",
            "talent_acquisition_specialist", "technical_interviewer", "panel_interviewer", "senior_manager",
        }
        if role in controller_roles:
            return redirect(url_for("interview_pages_v2.configure_ai_room_page", room_code=room_code))
        return redirect(url_for("interview_pages_v2.ai_interview_candidate_page", room_code=room_code))

    @app.route("/themes")
    @protected_page
    def themes_page():
        return render_template("themes.html")

    @app.route("/notifications")
    @protected_page
    def notifications_page():
        return render_template("notifications.html")

    @app.route("/messages")
    @protected_page
    def messages_page():
        return render_template("messages.html")

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

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=os.getenv("FLASK_ENV") == "development", use_reloader=False, allow_unsafe_werkzeug=True)
