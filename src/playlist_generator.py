import sqlite3
import logging
from dataclasses import dataclass

from src.top_songs import get_top_songs_for_decade, get_all_decades_with_data
from src.apple_music import (
    playlist_exists,
    create_playlist,
    search_and_add_songs_to_playlist,
)

logger = logging.getLogger(__name__)


# ##################################################################
# decade playlist name
# generates consistent playlist name for a decade
def decade_playlist_name(decade_start: int) -> str:
    return f"{decade_start}s Top Hits"


@dataclass
class PlaylistGenerationResult:
    decade: int
    playlist_name: str
    created: bool
    already_existed: bool
    songs_added: int
    songs_not_found: int
    total_songs: int


# ##################################################################
# generate decade playlist
# creates a playlist for a decade if it does not exist
def generate_decade_playlist(
    connection: sqlite3.Connection,
    decade_start: int,
) -> PlaylistGenerationResult:
    if decade_start % 10 != 0:
        logger.error("Invalid decade start year: %s (must end in 0)", decade_start)
        return PlaylistGenerationResult(
            decade=decade_start,
            playlist_name=decade_playlist_name(decade_start),
            created=False,
            already_existed=False,
            songs_added=0,
            songs_not_found=0,
            total_songs=0,
        )

    playlist_name = decade_playlist_name(decade_start)
    if playlist_exists(playlist_name):
        logger.info("Playlist already exists: %s", playlist_name)
        return PlaylistGenerationResult(
            decade=decade_start,
            playlist_name=playlist_name,
            created=False,
            already_existed=True,
            songs_added=0,
            songs_not_found=0,
            total_songs=0,
        )
    try:
        songs = get_top_songs_for_decade(connection, decade_start)
        if not songs:
            logger.warning("No songs found for decade %ds", decade_start)
            return PlaylistGenerationResult(
                decade=decade_start,
                playlist_name=playlist_name,
                created=False,
                already_existed=False,
                songs_added=0,
                songs_not_found=0,
                total_songs=0,
            )
        logger.info("Creating playlist: %s with %d songs", playlist_name, len(songs))
        playlist = create_playlist(playlist_name)
        if not playlist:
            logger.error("Failed to create playlist: %s", playlist_name)
            return PlaylistGenerationResult(
                decade=decade_start,
                playlist_name=playlist_name,
                created=False,
                already_existed=False,
                songs_added=0,
                songs_not_found=0,
                total_songs=len(songs),
            )
        playlist_id = playlist.get("id")
        if not playlist_id:
            logger.error("Created playlist missing id: %s", playlist_name)
            return PlaylistGenerationResult(
                decade=decade_start,
                playlist_name=playlist_name,
                created=False,
                already_existed=False,
                songs_added=0,
                songs_not_found=0,
                total_songs=len(songs),
            )
        if not playlist_exists(playlist_name):
            logger.warning(
                "Playlist %s created but not visible in library listing yet",
                playlist_name,
            )
        song_tuples = [(s.song, s.artist) for s in songs]
        results = search_and_add_songs_to_playlist(song_tuples, playlist_name, playlist_id=playlist_id)
        songs_added = sum(1 for r in results if r.found)
        songs_not_found = sum(1 for r in results if not r.found)
        logger.info(
            "Playlist %s: %d songs added, %d not found in library",
            playlist_name,
            songs_added,
            songs_not_found,
        )
        return PlaylistGenerationResult(
            decade=decade_start,
            playlist_name=playlist_name,
            created=True,
            already_existed=False,
            songs_added=songs_added,
            songs_not_found=songs_not_found,
            total_songs=len(songs),
        )
    except Exception:
        logger.exception("Unexpected error generating playlist for %s", playlist_name)
        return PlaylistGenerationResult(
            decade=decade_start,
            playlist_name=playlist_name,
            created=False,
            already_existed=False,
            songs_added=0,
            songs_not_found=0,
            total_songs=0,
        )


# ##################################################################
# create decade playlist
# convenience function to generate a playlist for a specific decade
def create_decade_playlist(
    connection: sqlite3.Connection,
    decade_start: int,
) -> PlaylistGenerationResult:
    logger.info("Generating playlist for decade: %ds", decade_start)
    return generate_decade_playlist(connection, decade_start)


# ##################################################################
# generate all decade playlists
# creates playlists for all decades with data, ignoring existing ones
def generate_all_decade_playlists(
    connection: sqlite3.Connection,
) -> list[PlaylistGenerationResult]:
    decades = get_all_decades_with_data(connection)
    logger.info("Found decades with data: %s", decades)
    results = []
    for decade in decades:
        result = generate_decade_playlist(connection, decade)
        results.append(result)
    return results


# ##################################################################
# print generation summary
# displays summary of playlist generation results
def print_generation_summary(results: list[PlaylistGenerationResult]) -> None:
    print("\nPlaylist Generation Summary")
    print("=" * 50)
    for r in results:
        if r.already_existed:
            status = "EXISTING"
        elif r.created:
            status = f"CREATED ({r.songs_added}/{r.total_songs} songs)"
        else:
            status = "FAILED"
        print(f"  {r.playlist_name}: {status}")
    created = sum(1 for r in results if r.created)
    existing = sum(1 for r in results if r.already_existed)
    total_added = sum(r.songs_added for r in results)
    total_missing = sum(r.songs_not_found for r in results)
    print()
    print(f"Playlists created: {created}")
    print(f"Playlists already existed: {existing}")
    print(f"Total songs added: {total_added}")
    print(f"Songs not in library: {total_missing}")
