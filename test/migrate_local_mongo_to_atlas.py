"""One-time migration: local MongoDB -> MongoDB Atlas.

Set:
    LOCAL_MONGO_URI=mongodb://127.0.0.1:27017
    ATLAS_MONGO_URI=mongodb+srv://...
    DB_NAME=ai_hrms_local

Run:
    python test/migrate_local_mongo_to_atlas.py

Optional:
    python test/migrate_local_mongo_to_atlas.py --drop-target
    python test/migrate_local_mongo_to_atlas.py --collections users employees
"""
from __future__ import annotations

import argparse
import os
from typing import Iterable

from dotenv import load_dotenv
from pymongo import MongoClient, ReplaceOne
from pymongo.errors import OperationFailure

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

LOCAL_URI = os.getenv("LOCAL_MONGO_URI") or os.getenv("MONGO_URI") or "mongodb://127.0.0.1:27017"
ATLAS_URI = os.getenv("ATLAS_MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "ai_hrms_local")
BATCH_SIZE = int(os.getenv("MONGO_MIGRATION_BATCH_SIZE", "500"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate local MongoDB data to MongoDB Atlas.")
    parser.add_argument("--collections", nargs="*", help="Specific collections to migrate. Defaults to all local collections.")
    parser.add_argument("--drop-target", action="store_true", help="Drop target Atlas collections before copying documents.")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Bulk write batch size.")
    return parser.parse_args()


def copy_indexes(source_collection, target_collection) -> None:
    for index in source_collection.list_indexes():
        if index["name"] == "_id_":
            continue
        options = {
            key: value
            for key, value in index.items()
            if key not in {"v", "key", "ns"}
        }
        try:
            target_collection.create_index(list(index["key"].items()), **options)
        except OperationFailure as exc:
            print(f"  index skipped ({index['name']}): {exc.details.get('errmsg', exc)}")


def batched_writes(rows: Iterable[dict], batch_size: int) -> Iterable[list[ReplaceOne]]:
    batch: list[ReplaceOne] = []
    for row in rows:
        batch.append(ReplaceOne({"_id": row["_id"]}, row, upsert=True))
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> None:
    args = parse_args()
    if not ATLAS_URI:
        raise SystemExit("Set ATLAS_MONGO_URI before running this migration.")

    local_client = MongoClient(LOCAL_URI, serverSelectionTimeoutMS=8000)
    atlas_client = MongoClient(ATLAS_URI, serverSelectionTimeoutMS=8000)
    local_client.admin.command("ping")
    atlas_client.admin.command("ping")

    source_db = local_client[DB_NAME]
    target_db = atlas_client[DB_NAME]
    collection_names = args.collections or source_db.list_collection_names()

    print(f"Source: local MongoDB database '{DB_NAME}'")
    print(f"Target: Atlas database '{DB_NAME}'")

    for name in collection_names:
        source_collection = source_db[name]
        target_collection = target_db[name]
        if args.drop_target:
            target_collection.drop()

        copied = 0
        cursor = source_collection.find({}, no_cursor_timeout=True).batch_size(args.batch_size)
        try:
            for batch in batched_writes(cursor, args.batch_size):
                result = target_collection.bulk_write(batch, ordered=False)
                copied += result.upserted_count + result.modified_count + result.matched_count
        finally:
            cursor.close()

        copy_indexes(source_collection, target_collection)
        print(f"{name}: copied/upserted {copied} documents")

    print("Local MongoDB -> Atlas migration completed.")


if __name__ == "__main__":
    main()
