import sqlite3
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.best_of_decade import get_best_songs_for_decade, get_best_songs_all_decades, BestSongScore
from src.apple_music import (
    playlist_exists,
    create_playlist,
    search_and_add_songs_to_playlist,
)

logger = logging.getLogger(__name__)

COVERS_DIR = Path(__file__).parent.parent / "playlist_covers"


# ##################################################################
# best of decade playlist name
# generates consistent playlist name for best-of-decade
def best_of_decade_playlist_name(decade_start: int) -> str:
    return f"Best of the {decade_start}s"


# ##################################################################
# best of best playlist name
# returns the name for the combined mega-playlist
def best_of_best_playlist_name() -> str:
    return "Best of the Best"


@dataclass
class BestOfPlaylistResult:
    playlist_name: str
    created: bool
    already_existed: bool
    songs_added: int
    songs_not_found: int
    total_songs: int


# ##################################################################
# generate best of decade playlist
# creates an apple music playlist with the top 10 songs for a decade
def generate_best_of_decade_playlist(
    connection: sqlite3.Connection,
    decade_start: int,
) -> BestOfPlaylistResult:
    playlist_name = best_of_decade_playlist_name(decade_start)

    if playlist_exists(playlist_name):
        logger.info("Playlist already exists: %s", playlist_name)
        return BestOfPlaylistResult(
            playlist_name=playlist_name,
            created=False,
            already_existed=True,
            songs_added=0,
            songs_not_found=0,
            total_songs=0,
        )

    songs = get_best_songs_for_decade(connection, decade_start, limit=10)
    if not songs:
        logger.warning("No songs found for decade %ds", decade_start)
        return BestOfPlaylistResult(
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
        return BestOfPlaylistResult(
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
        return BestOfPlaylistResult(
            playlist_name=playlist_name,
            created=False,
            already_existed=False,
            songs_added=0,
            songs_not_found=0,
            total_songs=len(songs),
        )

    song_tuples = [(s.song, s.artist) for s in songs]
    results = search_and_add_songs_to_playlist(song_tuples, playlist_name, playlist_id=playlist_id)
    songs_added = sum(1 for r in results if r.found)
    songs_not_found = sum(1 for r in results if not r.found)

    logger.info("Playlist %s: %d songs added, %d not found", playlist_name, songs_added, songs_not_found)
    return BestOfPlaylistResult(
        playlist_name=playlist_name,
        created=True,
        already_existed=False,
        songs_added=songs_added,
        songs_not_found=songs_not_found,
        total_songs=len(songs),
    )


# ##################################################################
# generate best of best playlist
# creates the combined mega-playlist with top 10 from every decade
def generate_best_of_best_playlist(
    connection: sqlite3.Connection,
) -> BestOfPlaylistResult:
    playlist_name = best_of_best_playlist_name()

    if playlist_exists(playlist_name):
        logger.info("Playlist already exists: %s", playlist_name)
        return BestOfPlaylistResult(
            playlist_name=playlist_name,
            created=False,
            already_existed=True,
            songs_added=0,
            songs_not_found=0,
            total_songs=0,
        )

    all_decades = get_best_songs_all_decades(connection, limit=10)
    all_songs: list[BestSongScore] = []
    for decade in sorted(all_decades.keys()):
        all_songs.extend(all_decades[decade])

    if not all_songs:
        logger.warning("No songs found for any decade")
        return BestOfPlaylistResult(
            playlist_name=playlist_name,
            created=False,
            already_existed=False,
            songs_added=0,
            songs_not_found=0,
            total_songs=0,
        )

    logger.info("Creating playlist: %s with %d songs", playlist_name, len(all_songs))
    playlist = create_playlist(playlist_name)
    if not playlist:
        logger.error("Failed to create playlist: %s", playlist_name)
        return BestOfPlaylistResult(
            playlist_name=playlist_name,
            created=False,
            already_existed=False,
            songs_added=0,
            songs_not_found=0,
            total_songs=len(all_songs),
        )

    playlist_id = playlist.get("id")
    if not playlist_id:
        logger.error("Created playlist missing id: %s", playlist_name)
        return BestOfPlaylistResult(
            playlist_name=playlist_name,
            created=False,
            already_existed=False,
            songs_added=0,
            songs_not_found=0,
            total_songs=len(all_songs),
        )

    song_tuples = [(s.song, s.artist) for s in all_songs]
    results = search_and_add_songs_to_playlist(song_tuples, playlist_name, playlist_id=playlist_id)
    songs_added = sum(1 for r in results if r.found)
    songs_not_found = sum(1 for r in results if not r.found)

    logger.info("Playlist %s: %d songs added, %d not found", playlist_name, songs_added, songs_not_found)
    return BestOfPlaylistResult(
        playlist_name=playlist_name,
        created=True,
        already_existed=False,
        songs_added=songs_added,
        songs_not_found=songs_not_found,
        total_songs=len(all_songs),
    )


# ##################################################################
# generate best of decade image
# creates a cover image for a best-of-decade playlist
def generate_best_of_decade_image(decade_start: int, songs: list[BestSongScore]) -> Path | None:
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = COVERS_DIR / f"best_of_{decade_start}s.png"

    song_list = ", ".join(f'"{s.song}"' for s in songs[:5])
    prompt = (
        f"Elegant black and gold art deco style poster. "
        f"Large bold text '{decade_start}s' prominently centered. "
        f"Smaller text 'BEST OF THE {decade_start}s' above or below. "
        f"Premium minimalist design with geometric art deco patterns. "
        f"Gold metallic text on deep black background. "
        f"No photographs, no people, no instruments. "
        f"Featuring hits like {song_list}."
    )

    generate_image = Path.home() / "bin" / "generate_image"
    cmd = [
        str(generate_image),
        "--prompt", prompt,
        "--output", str(output_path),
        "--width", "1024",
        "--height", "1024",
    ]

    logger.info("Generating cover image for Best of the %ds...", decade_start)
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        logger.info("Generated cover image: %s", output_path)
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error("Failed to generate image for %ds: %s", decade_start, e.stderr)
        return None
    except FileNotFoundError:
        logger.error("generate_image not found at %s", generate_image)
        return None


# ##################################################################
# generate best of best image
# creates a cover image for the combined mega-playlist
def generate_best_of_best_image(decades: list[int]) -> Path | None:
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = COVERS_DIR / "best_of_the_best.png"

    decade_text = " ".join(f"{d}s" for d in sorted(decades))
    prompt = (
        f"Elegant black and gold art deco style poster. "
        f"Large bold text 'BEST OF THE BEST' prominently centered. "
        f"Smaller text showing decades: {decade_text}. "
        f"Premium minimalist design with geometric art deco patterns. "
        f"Gold metallic text on deep black background. "
        f"No photographs, no people, no instruments. "
        f"Crown or star motif suggesting the ultimate collection."
    )

    generate_image = Path.home() / "bin" / "generate_image"
    cmd = [
        str(generate_image),
        "--prompt", prompt,
        "--output", str(output_path),
        "--width", "1024",
        "--height", "1024",
    ]

    logger.info("Generating cover image for Best of the Best...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        logger.info("Generated cover image: %s", output_path)
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error("Failed to generate Best of the Best image: %s", e.stderr)
        return None
    except FileNotFoundError:
        logger.error("generate_image not found at %s", generate_image)
        return None


# ##################################################################
# generate all best of playlists
# orchestrates creation of all best-of-decade playlists plus best of best
def generate_all_best_of_playlists(
    connection: sqlite3.Connection,
    generate_images: bool = True,
) -> list[BestOfPlaylistResult]:
    all_decades = get_best_songs_all_decades(connection, limit=10)
    results = []

    for decade in sorted(all_decades.keys()):
        result = generate_best_of_decade_playlist(connection, decade)
        results.append(result)
        if generate_images and result.created:
            generate_best_of_decade_image(decade, all_decades[decade])

    best_result = generate_best_of_best_playlist(connection)
    results.append(best_result)
    if generate_images and best_result.created:
        generate_best_of_best_image(sorted(all_decades.keys()))

    return results


# ##################################################################
# print best of dry run
# displays ranked songs with scores for each decade without creating playlists
def print_best_of_dry_run(
    connection: sqlite3.Connection,
    decade_start: int | None = None,
) -> None:
    if decade_start:
        decades_data = {decade_start: get_best_songs_for_decade(connection, decade_start, limit=10)}
    else:
        decades_data = get_best_songs_all_decades(connection, limit=10)

    for decade in sorted(decades_data.keys()):
        songs = decades_data[decade]
        print(f"\nBest of the {decade}s")
        print("=" * 70)
        for i, song in enumerate(songs, 1):
            print(
                f"  {i:2}. {song.artist} - {song.song}"
                f"  (score: {song.total_score:,.0f}, weeks: {song.weeks_on_chart}, peak: #{song.peak_position})"
            )
        print()


# ##################################################################
# print best of summary
# displays summary of best-of playlist generation results
def print_best_of_summary(results: list[BestOfPlaylistResult]) -> None:
    print("\nBest-of Playlist Generation Summary")
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
    print(f"Songs not found: {total_missing}")
