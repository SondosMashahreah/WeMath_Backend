"""Validate/import reviewed content: python -m scripts.platform_content content.json [--check]."""
import argparse
import json
from pathlib import Path

from pydantic import TypeAdapter

from app.db.database import SessionLocal
from app.platform.models import PlatformEntry
from app.platform.schemas import EntryWrite
import app.models  # noqa: F401 — registers FK targets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    entries = TypeAdapter(list[EntryWrite]).validate_python(json.loads(args.file.read_text(encoding="utf-8-sig")))
    if len({entry.id for entry in entries}) != len(entries):
        parser.error("Duplicate content IDs")
    if not args.check:
        with SessionLocal.begin() as db:
            for entry in entries:
                db.merge(PlatformEntry(**entry.model_dump()))
    print(f"{len(entries)} entries {'validated' if args.check else 'saved'}")


if __name__ == "__main__":
    main()
