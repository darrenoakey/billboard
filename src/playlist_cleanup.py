import logging
import re
from collections import defaultdict
from dataclasses import dataclass

from src.apple_music import get_client

logger = logging.getLogger(__name__)


@dataclass
class PlaylistInfo:
    name: str
    index: int
    track_count: int
    playlist_id: str


DECADE_PLAYLIST_PATTERN = re.compile(r"^(?P<decade>\d{4})s\s+Top Hits$", re.IGNORECASE)


# ##################################################################
# parse decade playlist name
# returns decade start year for matching playlist names
def parse_decade_playlist_name(name: str) -> int | None:
    match = DECADE_PLAYLIST_PATTERN.match(name.strip())
    if not match:
        return None
    decade = int(match.group("decade"))
    if decade % 10 != 0:
        return None
    return decade


# ##################################################################
# check decade playlist name
# verifies playlist name matches decade top hits format
def is_decade_top_hits_playlist(name: str) -> bool:
    return parse_decade_playlist_name(name) is not None


# ##################################################################
# get all playlists with track counts
# retrieves all user playlists with their track counts
def get_all_playlists() -> list[PlaylistInfo]:
    client = get_client()
    library_playlists = client.get_library_playlists()
    playlists = []
    for index, playlist in enumerate(library_playlists, 1):
        attributes = playlist.get("attributes", {})
        name = attributes.get("name", "")
        playlist_id = playlist.get("id", "")
        track_count = 0
        if playlist_id:
            count = client.get_library_playlist_track_count(playlist_id)
            if count is None:
                logger.warning("Could not fetch track count for playlist %s (%s)", name, playlist_id)
            else:
                track_count = count
        playlists.append(
            PlaylistInfo(
                name=name,
                index=index,
                track_count=track_count,
                playlist_id=playlist_id,
            )
        )

    return playlists


# ##################################################################
# find duplicates
# groups playlists by name and identifies duplicates
def find_duplicates(playlists: list[PlaylistInfo]) -> dict[str, list[PlaylistInfo]]:
    by_name: dict[str, list[PlaylistInfo]] = defaultdict(list)
    for p in playlists:
        by_name[p.name].append(p)

    duplicates = {name: items for name, items in by_name.items() if len(items) > 1}
    return duplicates


# ##################################################################
# delete playlist by index
# deletes a playlist using its index position
def delete_playlist_by_index(index: int) -> bool:
    client = get_client()
    playlists = client.get_library_playlists()
    if index < 1 or index > len(playlists):
        logger.warning("Playlist index out of range: %s", index)
        return False
    playlist_id = playlists[index - 1].get("id")
    if not playlist_id:
        logger.error("Playlist missing id at index %s", index)
        return False
    return client.delete_library_playlist(playlist_id)


# ##################################################################
# delete playlist by id
# deletes a playlist using its library id
def delete_playlist_by_id(playlist_id: str) -> bool:
    client = get_client()
    if not playlist_id:
        logger.error("Playlist id is empty")
        return False
    return client.delete_library_playlist(playlist_id)


# ##################################################################
# delete playlist by name and track count
# deletes a specific playlist matching name and track count
def delete_playlist_by_name_and_count(name: str, track_count: int) -> bool:
    client = get_client()
    for playlist in client.get_library_playlists():
        attributes = playlist.get("attributes", {})
        if attributes.get("name") != name:
            continue
        playlist_id = playlist.get("id")
        if not playlist_id:
            logger.warning("Playlist %s missing id", name)
            continue
        count = client.get_library_playlist_track_count(playlist_id)
        if count is None:
            logger.warning("Could not fetch track count for playlist %s (%s)", name, playlist_id)
            continue
        if count == track_count:
            return delete_playlist_by_id(playlist_id)
    return False


# ##################################################################
# cleanup duplicate playlists
# keeps the playlist with most tracks and deletes others
def cleanup_duplicate_playlists(dry_run: bool = True) -> dict:
    playlists = get_all_playlists()
    duplicates = find_duplicates(playlists)

    results = {
        "duplicates_found": len(duplicates),
        "playlists_deleted": 0,
        "playlists_kept": 0,
        "details": [],
    }

    if not duplicates:
        logger.info("No duplicate playlists found")
        return results

    for name, items in duplicates.items():
        items_sorted = sorted(items, key=lambda x: x.track_count, reverse=True)
        keep = items_sorted[0]
        to_delete = items_sorted[1:]

        logger.info(
            "Playlist '%s': keeping with %d tracks, deleting %d duplicates",
            name,
            keep.track_count,
            len(to_delete),
        )

        results["details"].append(
            {
                "name": name,
                "kept_track_count": keep.track_count,
                "kept_playlist_id": keep.playlist_id,
                "deleted_count": len(to_delete),
                "deleted_track_counts": [d.track_count for d in to_delete],
                "deleted_playlist_ids": [d.playlist_id for d in to_delete],
            }
        )

        results["playlists_kept"] += 1

        if not dry_run:
            for dup in to_delete:
                if delete_playlist_by_id(dup.playlist_id):
                    results["playlists_deleted"] += 1
                    logger.info(
                        "Deleted '%s' (id=%s) with %d tracks",
                        name,
                        dup.playlist_id,
                        dup.track_count,
                    )
                else:
                    logger.warning(
                        "Could not delete '%s' (id=%s) with %d tracks",
                        name,
                        dup.playlist_id,
                        dup.track_count,
                    )
        else:
            results["playlists_deleted"] += len(to_delete)

    return results


# ##################################################################
# find decade playlists below track count
# filters decade playlists with fewer than min tracks
def find_decade_playlists_below_track_count(
    playlists: list[PlaylistInfo],
    min_tracks: int,
) -> list[PlaylistInfo]:
    return [
        playlist
        for playlist in playlists
        if is_decade_top_hits_playlist(playlist.name) and playlist.track_count < min_tracks
    ]


# ##################################################################
# cleanup decade playlists below track count
# deletes decade playlists with fewer than min tracks
def cleanup_decade_playlists_below_track_count(min_tracks: int = 50, dry_run: bool = True) -> dict:
    playlists = get_all_playlists()
    to_delete = find_decade_playlists_below_track_count(playlists, min_tracks)

    results = {
        "min_tracks": min_tracks,
        "playlists_found": len(to_delete),
        "playlists_deleted": 0,
        "playlists_failed": 0,
        "details": [],
    }

    if not to_delete:
        logger.info("No decade playlists below %d tracks found", min_tracks)
        return results

    for playlist in to_delete:
        if dry_run:
            results["playlists_deleted"] += 1
            results["details"].append(
                {
                    "name": playlist.name,
                    "track_count": playlist.track_count,
                    "action": "WOULD DELETE",
                }
            )
            continue

        if delete_playlist_by_name_and_count(playlist.name, playlist.track_count):
            results["playlists_deleted"] += 1
            action = "DELETED"
            logger.info(
                "Deleted decade playlist '%s' with %d tracks",
                playlist.name,
                playlist.track_count,
            )
        else:
            results["playlists_failed"] += 1
            action = "FAILED"
            logger.warning(
                "Failed to delete decade playlist '%s' with %d tracks",
                playlist.name,
                playlist.track_count,
            )

        results["details"].append(
            {
                "name": playlist.name,
                "track_count": playlist.track_count,
                "action": action,
            }
        )

    return results


# ##################################################################
# print cleanup report
# displays summary of cleanup operation
def print_cleanup_report(results: dict, dry_run: bool = True) -> None:
    print()
    if dry_run:
        print("=== DRY RUN - No changes made ===")
    print()
    print("Duplicate Playlist Cleanup Report")
    print("=" * 50)

    if results["duplicates_found"] == 0:
        print("No duplicate playlists found.")
        return

    print(f"Duplicate playlist names found: {results['duplicates_found']}")
    print()

    for detail in results["details"]:
        print(f"  {detail['name']}:")
        print(f"    - Keeping: {detail['kept_track_count']} tracks")
        print(f"    - Deleting {detail['deleted_count']} copies with: {detail['deleted_track_counts']} tracks")

    print()
    print(f"Total playlists to keep: {results['playlists_kept']}")
    print(f"Total playlists to delete: {results['playlists_deleted']}")

    if dry_run:
        print()
        print("Run with --execute to actually delete the playlists.")


# ##################################################################
# print decade cleanup report
# displays summary of decade playlist cleanup operation
def print_decade_cleanup_report(results: dict, dry_run: bool = True) -> None:
    print()
    if dry_run:
        print("=== DRY RUN - No changes made ===")
    print()
    print("Incomplete Decade Playlist Cleanup Report")
    print("=" * 50)

    if results["playlists_found"] == 0:
        print("No decade playlists below the minimum track count were found.")
        return

    print(f"Minimum tracks required: {results['min_tracks']}")
    print(f"Playlists found: {results['playlists_found']}")
    print()

    for detail in results["details"]:
        print(f"  {detail['name']} ({detail['track_count']} tracks): {detail['action']}")

    print()
    print(f"Total playlists deleted: {results['playlists_deleted']}")
    if results["playlists_failed"]:
        print(f"Total playlists failed to delete: {results['playlists_failed']}")

    if dry_run:
        print()
        print("Run with --execute to delete and regenerate playlists.")
