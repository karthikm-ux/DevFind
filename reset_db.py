"""Safe database reset script for DevFind.

DESTRUCTIVE: Deletes and recreates Weaviate collections.
Run this ONLY when you explicitly want to wipe existing data.
Always prompts for confirmation before destroying any data.

Usage:
    python reset_db.py
    python reset_db.py --yes --collection DevFindIssue
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from src.db.client import get_client
from src.db.schema import (
    ISSUE_COLLECTION,
    KNOWLEDGE_COLLECTION,
    get_collection_stats,
    reset_collections,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset DevFind Weaviate collections.")
    parser.add_argument(
        "--collection",
        choices=[ISSUE_COLLECTION, KNOWLEDGE_COLLECTION, "all"],
        default="all",
        help="Which collection to reset (default: all).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    args = parser.parse_args()

    target = args.collection
    collections = (
        [ISSUE_COLLECTION, KNOWLEDGE_COLLECTION]
        if target == "all"
        else [target]
    )

    print("\n" + "=" * 60)
    print("  DevFind — Safe Database Reset")
    print("=" * 60)

    try:
        client = get_client()
        print(f"Connected to Weaviate: {client.is_ready()}")
    except Exception as exc:
        print(f"\n❌ Cannot connect to Weaviate: {exc}")
        sys.exit(1)

    stats = get_collection_stats(client)
    print("\nCurrent collection state:")
    for name in collections:
        info = stats.get(name, {"exists": False, "count": 0})
        if info["exists"]:
            print(f"  • {name}: {info['count']} objects  ← WILL BE DELETED")
        else:
            print(f"  • {name}: does not exist (will be created fresh)")

    print()

    if not args.yes:
        confirm = input(
            f"⚠️  This will PERMANENTLY DELETE all data in: {', '.join(collections)}\n"
            "Type 'reset' to confirm, or anything else to cancel: "
        ).strip()
        if confirm.lower() != "reset":
            print("❌ Reset cancelled. No data was changed.")
            client.close()
            sys.exit(0)

    print("\nResetting collections...")
    reset_collections(client, collections)
    print("✅ Collections reset successfully.")

    new_stats = get_collection_stats(client)
    print("\nNew state:")
    for name in collections:
        info = new_stats.get(name, {"exists": False, "count": 0})
        print(f"  • {name}: {info['count']} objects")

    client.close()
    print("\nDone. Run 'python -c \"..\"' or use the app to reload data.\n")


if __name__ == "__main__":
    main()
