#!/usr/bin/env python3
"""
Download contest/user uploads from S3 into LOCAL_STORAGE_PATH on VPS.

Usage (on VPS, from repo root):
  cd backend && source .venv/bin/activate && export PYTHONPATH=.
  python scripts/sync_media_from_s3.py
  python scripts/sync_media_from_s3.py --prefix uploads/9/ --limit 20
"""
from __future__ import annotations

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync S3 uploads to local media dir")
    parser.add_argument("--prefix", default="uploads/", help="S3 key prefix (default uploads/)")
    parser.add_argument("--limit", type=int, default=0, help="Max objects (0 = all)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from app.core.config import settings
    from app.core.storage import media_storage_roots

    bucket = (settings.S3_BUCKET_NAME or settings.AWS_S3_BUCKET or "").strip()
    if not bucket or not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        print("ERROR: Set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET in backend/.env")
        return 1

    dest_root = settings.LOCAL_STORAGE_PATH
    os.makedirs(dest_root, exist_ok=True)
    print(f"Bucket: {bucket}")
    print(f"Dest:   {dest_root}")
    print(f"Also:   {', '.join(p for p in media_storage_roots() if p != dest_root)}")

    import boto3

    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
    )

    paginator = s3.get_paginator("list_objects_v2")
    downloaded = 0
    skipped = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=args.prefix):
        for obj in page.get("Contents") or []:
            key = obj.get("Key") or ""
            if not key or key.endswith("/"):
                continue
            if not key.startswith("uploads/"):
                continue
            parts = key.split("/")
            if len(parts) < 3:
                continue
            user_id, filename = parts[1], parts[2]
            local_path = os.path.join(dest_root, user_id, filename)
            if os.path.isfile(local_path):
                skipped += 1
                continue
            if args.dry_run:
                print(f"would download {key} -> {local_path}")
                downloaded += 1
            else:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                s3.download_file(bucket, key, local_path)
                print(f"OK {key}")
                downloaded += 1
            if args.limit and downloaded >= args.limit:
                print(f"Done (limit {args.limit}): downloaded={downloaded} skipped={skipped}")
                return 0

    print(f"Done: downloaded={downloaded} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
