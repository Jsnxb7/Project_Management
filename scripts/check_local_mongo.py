from __future__ import annotations

"""One-time/local MongoDB health check for AI PeopleOps HRMS.

This script is safe to run repeatedly.  It verifies the local MongoDB server,
creates the expected database handle, and applies the app indexes.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
db_name = os.getenv("DB_NAME", "ai_hrms_local")

try:
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
except ServerSelectionTimeoutError as exc:
    print("MongoDB connection failed.")
    print(f"URI: {mongo_uri}")
    print("Start MongoDB first, then run this script again.")
    print(str(exc))
    raise SystemExit(1)

print("MongoDB connection OK")
print(f"URI: {mongo_uri}")
print(f"Database: {db_name}")

try:
    from database.db import COLLECTION_NAMES, ensure_local_mongo_indexes

    ensure_local_mongo_indexes()
    db = client[db_name]
    existing = set(db.list_collection_names())
    # Create lightweight placeholders so first-run users can see the expected collections.
    for name in COLLECTION_NAMES:
        if name not in existing:
            db[name].insert_one({"_setup_placeholder": True})
            db[name].delete_one({"_setup_placeholder": True})
    print(f"Indexes checked for {len(COLLECTION_NAMES)} collections.")
    print("Local MongoDB setup check completed successfully.")
except Exception as exc:
    print("MongoDB ping worked, but app index setup failed.")
    print(str(exc))
    raise SystemExit(2)
