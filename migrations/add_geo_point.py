# migrations/add_geo_point.py
"""
One-time migration: add GeoJSON point field + 2dsphere index, remove flat lat/lng.

Usage:
    python migrations/add_geo_point.py              # live run
    python migrations/add_geo_point.py --dry-run    # print counts only
"""
import os
import sys
import argparse
from urllib.parse import quote

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()


def _connect() -> MongoClient:
    pw = os.environ.get("MONGODB_PW")
    if not pw:
        raise RuntimeError("MONGODB_PW not set")
    encoded = quote(pw, safe="")
    uri = (
        "mongodb+srv://Vercel-Admin-property_listing:"
        f"{encoded}@cluster0.fznmnjx.mongodb.net/?appName=Cluster0"
    )
    client = MongoClient(uri, server_api=ServerApi("1"))
    client.admin.command("ping")
    return client


def run(dry_run: bool = False) -> dict:
    client = _connect()
    col = client["property"]["property_listing"]

    # Count docs that need migration
    needs_migration = col.count_documents({
        "location.geo.latitude": {"$exists": True, "$ne": None},
        "location.geo.longitude": {"$exists": True, "$ne": None},
        "location.geo.point": {"$exists": False},
    })
    print(f"Documents needing geo point migration: {needs_migration}")

    if dry_run:
        print("[dry-run] no changes written.")
        return {"needs_migration": needs_migration, "updated": 0, "indexed": False, "unset": 0}

    # Step 1 — add GeoJSON point field using aggregation pipeline update
    result1 = col.update_many(
        {
            "location.geo.latitude": {"$exists": True, "$ne": None},
            "location.geo.longitude": {"$exists": True, "$ne": None},
            "location.geo.point": {"$exists": False},
        },
        [{
            "$set": {
                "location.geo.point": {
                    "type": "Point",
                    "coordinates": ["$location.geo.longitude", "$location.geo.latitude"],
                }
            }
        }],
    )
    print(f"Step 1 — point field added: {result1.modified_count} documents")

    # Step 2 — create 2dsphere index
    col.create_index([("location.geo.point", "2dsphere")])
    print("Step 2 — 2dsphere index created on location.geo.point")

    # Step 3 — remove old flat fields
    result3 = col.update_many(
        {"location.geo.point": {"$exists": True}},
        {"$unset": {"location.geo.latitude": "", "location.geo.longitude": ""}},
    )
    print(f"Step 3 — flat lat/lng removed: {result3.modified_count} documents")

    client.close()
    return {
        "needs_migration": needs_migration,
        "updated": result1.modified_count,
        "indexed": True,
        "unset": result3.modified_count,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
