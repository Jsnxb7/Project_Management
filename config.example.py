import os
from dotenv import load_dotenv

# Load local .env variables. Keep .env private and never commit it.
load_dotenv()


class Config:
    """Application configuration loaded from environment variables.

    Setup:
    1. Copy this file as config.py.
    2. Create .env from .env.example.
    3. Fill LOCAL_MONGO_URI, ATLAS_MONGO_URI, DB_NAME, SECRET_KEY, and JWT_SECRET_KEY.

    The real config.py is ignored by Git so secrets are not uploaded.
    """

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-this")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-this")
    LOCAL_MONGO_URI = os.getenv("LOCAL_MONGO_URI", os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017"))
    ATLAS_MONGO_URI = os.getenv("ATLAS_MONGO_URI", "")
    MONGO_URI = LOCAL_MONGO_URI
    DB_NAME = os.getenv("DB_NAME", "ai_hrms_local")
    MONGO_MAX_POOL_SIZE = int(os.getenv("MONGO_MAX_POOL_SIZE", "200"))
    MONGO_MIN_POOL_SIZE = int(os.getenv("MONGO_MIN_POOL_SIZE", "5"))
    MONGO_SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "20000"))
    MONGO_CONNECT_TIMEOUT_MS = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "20000"))
    MONGO_FALLBACK_SELECTION_TIMEOUT_MS = int(os.getenv("MONGO_FALLBACK_SELECTION_TIMEOUT_MS", "5000"))
    MONGO_RETRY_WRITES = os.getenv("MONGO_RETRY_WRITES", "true").lower() == "true"
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(24 * 1024 * 1024)))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "static/uploads")
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 60 * 60 * 24))
