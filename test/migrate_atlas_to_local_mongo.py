"""One-time migration: Mongo Atlas -> local MongoDB.

Set:
    ATLAS_MONGO_URI=mongodb+srv://...
    LOCAL_MONGO_URI=mongodb://127.0.0.1:27017
    DB_NAME=ai_hrms_local

Run:
    python test/migrate_atlas_to_local_mongo.py
"""
from __future__ import annotations

import os
from pymongo import MongoClient, ReplaceOne

ATLAS_URI = os.getenv("ATLAS_MONGO_URI")
LOCAL_URI = os.getenv("LOCAL_MONGO_URI", "mongodb://127.0.0.1:27017")
DB_NAME = os.getenv("DB_NAME", "ai_hrms_local")


def main():
    if not ATLAS_URI:
        raise SystemExit("Set ATLAS_MONGO_URI before running this migration.")
    src_client = MongoClient(ATLAS_URI)
    dst_client = MongoClient(LOCAL_URI)
    src_client.admin.command("ping")
    dst_client.admin.command("ping")
    src = src_client[DB_NAME]
    dst = dst_client[DB_NAME]
    for name in src.list_collection_names():
        rows = list(src[name].find({}))
        if rows:
            dst[name].bulk_write([ReplaceOne({"_id": row["_id"]}, row, upsert=True) for row in rows])
        print(f"{name}: {len(rows)}")
    print("Atlas -> local MongoDB migration completed.")


if __name__ == "__main__":
    main()
