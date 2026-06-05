import os
from dotenv import load_dotenv

# Load local .env variables. Keep .env private and never commit it.
load_dotenv()


class Config:
    """Application configuration loaded from environment variables.

    Setup:
    1. Copy this file as config.py.
    2. Create .env from .env.example.
    3. Fill MONGO_URI, DB_NAME, SECRET_KEY, and JWT_SECRET_KEY.

    The real config.py is ignored by Git so secrets are not uploaded.
    """

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-this")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-this")
    MONGO_URI = os.getenv("MONGO_URI")
    DB_NAME = os.getenv("DB_NAME", "new_teams_db")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 8 * 1024 * 1024))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "static/uploads")
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 60 * 60 * 24))
