import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    """Read boolean values from environment variables safely."""
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # -------------------------------------------------------------------------
    # App / security
    # -------------------------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-this")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-this")
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", str(60 * 60 * 24)))

    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    IS_RENDER = _env_bool("RENDER", False) or bool(os.getenv("RENDER_EXTERNAL_URL"))

    # -------------------------------------------------------------------------
    # MongoDB
    # -------------------------------------------------------------------------
    DB_NAME = os.getenv("DB_NAME", "ai_hrms_local")

    # Local Mongo is only the default during local development.
    # On Render, do not default to 127.0.0.1 because there is no local mongod.
    DEFAULT_LOCAL_MONGO_URI = "" if IS_RENDER else "mongodb://127.0.0.1:27017"

    LOCAL_MONGO_URI = os.getenv(
        "LOCAL_MONGO_URI",
        os.getenv("MONGO_URI", DEFAULT_LOCAL_MONGO_URI)
    )

    ATLAS_MONGO_URI = os.getenv("ATLAS_MONGO_URI", "")

    # Useful for older code that imports Config.MONGO_URI directly.
    # On Render, prefer Atlas. Locally, prefer local Mongo unless MONGO_URI is set.
    MONGO_URI = ATLAS_MONGO_URI if IS_RENDER and ATLAS_MONGO_URI else LOCAL_MONGO_URI

    MONGO_MAX_POOL_SIZE = int(os.getenv("MONGO_MAX_POOL_SIZE", "200"))
    MONGO_MIN_POOL_SIZE = int(os.getenv("MONGO_MIN_POOL_SIZE", "5"))

    # Keep timeouts shorter on Render so fallback does not hang deploy/startup.
    MONGO_SERVER_SELECTION_TIMEOUT_MS = int(
        os.getenv(
            "MONGO_SERVER_SELECTION_TIMEOUT_MS",
            "5000" if IS_RENDER else "20000"
        )
    )
    MONGO_CONNECT_TIMEOUT_MS = int(
        os.getenv(
            "MONGO_CONNECT_TIMEOUT_MS",
            "5000" if IS_RENDER else "20000"
        )
    )
    MONGO_FALLBACK_SELECTION_TIMEOUT_MS = int(
        os.getenv("MONGO_FALLBACK_SELECTION_TIMEOUT_MS", "5000")
    )
    MONGO_RETRY_WRITES = _env_bool("MONGO_RETRY_WRITES", True)

    # -------------------------------------------------------------------------
    # Uploads
    # -------------------------------------------------------------------------
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(24 * 1024 * 1024)))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "static/uploads")

    # -------------------------------------------------------------------------
    # SocketIO / live rooms
    # -------------------------------------------------------------------------
    # Render + Gunicorn recommended command for this config:
    # gunicorn -w 1 --threads 100 "app:create_app()"
    #
    # Use simple-websocket in requirements.txt.
    # Do not use eventlet workers unless you switch this value to "eventlet"
    # and update the Gunicorn command accordingly.
    SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "threading")
    SOCKETIO_CORS_ALLOWED_ORIGINS = os.getenv("SOCKETIO_CORS_ALLOWED_ORIGINS", "*")
    LIVE_ROOM_EVENT_RETENTION = int(os.getenv("LIVE_ROOM_EVENT_RETENTION", "500"))

    # -------------------------------------------------------------------------
    # AI model lifecycle
    # -------------------------------------------------------------------------
    AI_MODEL_KEEP_WARM_SECONDS = int(os.getenv("AI_MODEL_KEEP_WARM_SECONDS", "600"))
    AI_LOCAL_CACHE_DIR = os.getenv("AI_LOCAL_CACHE_DIR", "")
