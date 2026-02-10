import json
import logging
from dataclasses import dataclass
from pathlib import Path

from src.apple_music_api import AppleMusicClient, AppleMusicConfig, search_song_in_catalog

logger = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".config" / "billboard" / "config.json"


# ##################################################################
# load config
# reads apple music credentials from config file
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config not found at {CONFIG_PATH}. "
            "Create it with apple_music_team_id, apple_music_key_id, and apple_music_private_key_path."
        )
    return json.loads(CONFIG_PATH.read_text())


# ##################################################################
# load apple music client
# creates client with credentials from config files
def load_apple_music_client() -> AppleMusicClient:
    cfg = load_config()
    user_token_path = Path.home() / ".config" / "billboard" / "music_user_token"
    if not user_token_path.exists():
        raise FileNotFoundError(
            f"Music user token not found at {user_token_path}. Run tools/music_auth_server.py to authorize."
        )
    user_token = user_token_path.read_text().strip()
    config = AppleMusicConfig(
        team_id=cfg["apple_music_team_id"],
        key_id=cfg["apple_music_key_id"],
        private_key_path=Path(cfg["apple_music_private_key_path"]).expanduser(),
        music_user_token=user_token,
    )
    return AppleMusicClient(config)


_client: AppleMusicClient | None = None


# ##################################################################
# get client
# returns singleton apple music client instance
def get_client() -> AppleMusicClient:
    global _client
    if _client is None:
        _client = load_apple_music_client()
    return _client


# ##################################################################
# get existing playlists
# retrieves list of all playlist names from user library
def get_existing_playlists() -> list[str]:
    client = get_client()
    playlists = client.get_library_playlists()
    return [p.get("attributes", {}).get("name", "") for p in playlists]


# ##################################################################
# playlist exists
# checks if a playlist with given name already exists
def playlist_exists(name: str) -> bool:
    playlists = get_existing_playlists()
    return name in playlists


# ##################################################################
# create playlist
# creates a new empty playlist with given name
def create_playlist(name: str) -> dict | None:
    client = get_client()
    playlist = client.create_library_playlist(name)
    if playlist is None:
        logger.error("Failed to create playlist via Apple Music API: %s", name)
        return None
    logger.info("Created playlist via Apple Music API: %s (id=%s)", name, playlist.get("id"))
    return playlist


@dataclass
class TrackSearchResult:
    song: str
    artist: str
    found: bool
    track_id: str | None


REQUEST_DELAY_SECONDS = 0.2


# ##################################################################
# rate limit
# pauses execution to respect api rate limits
def rate_limit() -> None:
    import threading

    event = threading.Event()
    event.wait(timeout=REQUEST_DELAY_SECONDS)


# ##################################################################
# search and add songs to playlist
# searches apple music catalog and adds found songs to playlist
def search_and_add_songs_to_playlist(
    songs: list[tuple[str, str]],
    playlist_name: str,
    playlist_id: str | None = None,
) -> list[TrackSearchResult]:
    client = get_client()
    if playlist_id is None:
        playlist = client.find_or_create_playlist(playlist_name)
        if not playlist:
            logger.error("Failed to find or create playlist: %s", playlist_name)
            return [TrackSearchResult(song=s, artist=a, found=False, track_id=None) for s, a in songs]
        playlist_id = playlist.get("id")
    if not playlist_id:
        logger.error("Playlist missing id after create/find: %s", playlist_name)
        return [TrackSearchResult(song=s, artist=a, found=False, track_id=None) for s, a in songs]
    logger.info("Using playlist id=%s for %s", playlist_id, playlist_name)
    results = []
    found_ids = []
    for song, artist in songs:
        rate_limit()
        track_id = search_song_in_catalog(client, song, artist)
        if track_id:
            found_ids.append(track_id)
            results.append(
                TrackSearchResult(
                    song=song,
                    artist=artist,
                    found=True,
                    track_id=track_id,
                )
            )
            logger.info("Found: %s - %s (ID: %s)", artist, song, track_id)
        else:
            results.append(
                TrackSearchResult(
                    song=song,
                    artist=artist,
                    found=False,
                    track_id=None,
                )
            )
            logger.warning("Not found in Apple Music catalog: %s - %s", artist, song)
    if found_ids:
        batch_size = 25
        for i in range(0, len(found_ids), batch_size):
            batch = found_ids[i : i + batch_size]
            success = client.add_tracks_to_playlist(playlist_id, batch)
            if success:
                logger.info("Added batch of %d tracks to playlist", len(batch))
            else:
                logger.error("Failed to add batch of tracks to playlist")
    return results
