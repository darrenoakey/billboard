#!/usr/bin/env python3
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from src.apple_music import get_client


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger(__name__)

    client = get_client()
    playlist_name = "blah"
    logger.info("Creating playlist: %s", playlist_name)
    playlist = client.create_library_playlist(playlist_name)
    if not playlist:
        logger.error("Create failed for playlist: %s", playlist_name)
        return 1

    playlist_id = playlist.get("id")
    if not playlist_id:
        logger.error("Create returned no playlist id for %s", playlist_name)
        return 1

    logger.info("Created playlist id=%s name=%s", playlist_id, playlist_name)

    verified = client.get_library_playlist(playlist_id)
    if not verified:
        logger.warning("Playlist id %s not retrievable immediately after creation", playlist_id)
    else:
        attrs = verified.get("attributes", {})
        logger.info(
            "Verified playlist id=%s name=%s canEdit=%s",
            playlist_id,
            attrs.get("name"),
            attrs.get("canEdit"),
        )

    logger.info("Deleting playlist id=%s", playlist_id)
    deleted = False
    delays = [1, 2, 4, 8]
    for attempt, delay in enumerate(delays, 1):
        if client.delete_library_playlist(playlist_id):
            deleted = True
            break
        logger.warning("Delete attempt %d failed; retrying in %ds", attempt, delay)
        time.sleep(delay)
    if not deleted:
        logger.error("Delete failed for playlist id=%s after %d attempts", playlist_id, len(delays))
        queue_path = repo_root / "output" / "playlist_delete_queue.jsonl"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "playlist_id": playlist_id,
            "name": playlist_name,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "reason": "delete_failed",
        }
        with queue_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        logger.warning("Soft-delete queued in %s", queue_path)
        return 0

    logger.info("Deleted playlist id=%s", playlist_id)
    post_delete = client.get_library_playlist(playlist_id)
    if post_delete:
        logger.warning("Playlist id %s still retrievable after delete", playlist_id)
    else:
        logger.info("Playlist id %s no longer retrievable after delete", playlist_id)

    logger.info("Completed playlist create/delete test at %s", datetime.now(timezone.utc).isoformat())
    return 0


if __name__ == "__main__":
    sys.exit(main())
