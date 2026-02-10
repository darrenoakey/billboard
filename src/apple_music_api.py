import jwt
import time
import requests
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

APPLE_MUSIC_API_BASE = "https://api.music.apple.com/v1"
TOKEN_EXPIRY_SECONDS = 3600 * 12


@dataclass
class AppleMusicConfig:
    team_id: str
    key_id: str
    private_key_path: Path
    music_user_token: str


# ##################################################################
# generate developer token
# creates a jwt token for apple music api authentication
def generate_developer_token(config: AppleMusicConfig) -> str:
    private_key = config.private_key_path.read_text()
    now = int(time.time())
    payload = {
        "iss": config.team_id,
        "iat": now,
        "exp": now + TOKEN_EXPIRY_SECONDS,
    }
    headers = {
        "alg": "ES256",
        "kid": config.key_id,
    }
    token = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
    return token


# ##################################################################
# apple music client
# handles api requests to apple music
class AppleMusicClient:
    def __init__(self, config: AppleMusicConfig) -> None:
        self.config = config
        self.developer_token = generate_developer_token(config)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.developer_token}",
                "Music-User-Token": config.music_user_token,
                "Content-Type": "application/json",
            }
        )

    # ##################################################################
    # refresh developer token
    # regenerates token and updates session header
    def refresh_developer_token(self) -> None:
        self.developer_token = generate_developer_token(self.config)
        self.session.headers.update({"Authorization": f"Bearer {self.developer_token}"})

    # ##################################################################
    # request wrapper
    # centralizes api calls with logging and error handling
    def _request(self, method: str, url: str, **kwargs) -> requests.Response | None:
        retry_on_401 = kwargs.pop("_retry_on_401", True)
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
        except requests.RequestException as exc:
            logger.error("%s %s failed: %s", method, url, exc)
            return None

        if response.status_code == 401 and retry_on_401:
            logger.warning("%s %s returned 401; refreshing developer token and retrying", method, url)
            self.refresh_developer_token()
            return self._request(method, url, _retry_on_401=False, **kwargs)

        if response.status_code >= 400:
            self._log_error_response(method, url, response)
            return response

        logger.debug("%s %s -> %d", method, url, response.status_code)
        return response

    # ##################################################################
    # log error response
    # captures json error details when available
    def _log_error_response(self, method: str, url: str, response: requests.Response) -> None:
        try:
            payload: Any = response.json()
        except ValueError:
            payload = None
        logger.error(
            "%s %s failed: %s %s",
            method,
            url,
            response.status_code,
            response.text if payload is None else payload,
        )

    # ##################################################################
    # search catalog
    # searches apple music catalog for songs
    def search_catalog(self, query: str, limit: int = 5) -> list[dict]:
        url = f"{APPLE_MUSIC_API_BASE}/catalog/us/search"
        params = {
            "term": query,
            "types": "songs",
            "limit": limit,
        }
        response = self._request("GET", url, params=params)
        if not response or response.status_code != 200:
            return []
        data = response.json()
        songs = data.get("results", {}).get("songs", {}).get("data", [])
        return songs

    # ##################################################################
    # get library playlists
    # retrieves user library playlists
    def get_library_playlists(self) -> list[dict]:
        url = f"{APPLE_MUSIC_API_BASE}/me/library/playlists"
        params = {"limit": 100}
        playlists: list[dict] = []
        page = 0

        while url:
            response = self._request("GET", url, params=params)
            if not response or response.status_code != 200:
                return playlists
            data = response.json()
            page_playlists = data.get("data", [])
            playlists.extend(page_playlists)
            page += 1
            logger.info("Fetched playlists page %d: %d items", page, len(page_playlists))
            next_path = data.get("next")
            if next_path:
                url = f"{APPLE_MUSIC_API_BASE}{next_path}"
                params = None
            else:
                url = ""

        logger.info("Total playlists fetched: %d", len(playlists))
        return playlists

    # ##################################################################
    # get library playlist
    # retrieves a library playlist by id
    def get_library_playlist(self, playlist_id: str) -> dict | None:
        url = f"{APPLE_MUSIC_API_BASE}/me/library/playlists/{playlist_id}"
        response = self._request("GET", url)
        if not response or response.status_code != 200:
            return None
        data = response.json()
        playlists = data.get("data", [])
        if not playlists:
            logger.warning("Playlist id %s not found in get response", playlist_id)
            return None
        return playlists[0]

    # ##################################################################
    # get library playlist track count
    # retrieves total track count for a library playlist
    def get_library_playlist_track_count(self, playlist_id: str) -> int | None:
        url = f"{APPLE_MUSIC_API_BASE}/me/library/playlists/{playlist_id}/tracks"
        response = self._request("GET", url, params={"limit": 1})
        if not response or response.status_code != 200:
            return None
        data = response.json()
        meta = data.get("meta", {})
        total = meta.get("total")
        if isinstance(total, int):
            return total
        return len(data.get("data", []))

    # ##################################################################
    # find library playlist by name
    # searches full library playlists for a matching name
    def find_library_playlist_by_name(self, name: str) -> dict | None:
        for playlist in self.get_library_playlists():
            if playlist.get("attributes", {}).get("name") == name:
                logger.info("Found existing playlist: %s", name)
                return playlist
        logger.info("Playlist not found in library listing: %s", name)
        return None

    # ##################################################################
    # create library playlist
    # creates a new playlist in user library
    def create_library_playlist(self, name: str, description: str = "") -> dict | None:
        url = f"{APPLE_MUSIC_API_BASE}/me/library/playlists"
        payload = {
            "attributes": {
                "name": name,
                "description": description,
            }
        }
        response = self._request("POST", url, json=payload)
        if not response or response.status_code not in (200, 201):
            return None
        data = response.json()
        playlists = data.get("data", [])
        if not playlists:
            logger.error("Create playlist returned no data for %s", name)
            return None
        playlist = playlists[0]
        playlist_id = playlist.get("id")
        logger.info("Created playlist '%s' (id=%s)", name, playlist_id)
        if playlist_id:
            verified = self.get_library_playlist(playlist_id)
            if verified:
                logger.info("Verified playlist id %s is accessible via API", playlist_id)
            else:
                logger.warning("Playlist id %s not accessible immediately after creation", playlist_id)
        return playlist

    # ##################################################################
    # add tracks to playlist
    # adds songs to a library playlist by catalog ids
    def add_tracks_to_playlist(self, playlist_id: str, song_ids: list[str]) -> bool:
        url = f"{APPLE_MUSIC_API_BASE}/me/library/playlists/{playlist_id}/tracks"
        payload = {"data": [{"id": song_id, "type": "songs"} for song_id in song_ids]}
        response = self._request("POST", url, json=payload)
        if not response or response.status_code not in (200, 201, 204):
            return False
        return True

    # ##################################################################
    # delete library playlist
    # removes a playlist from the user library
    def delete_library_playlist(self, playlist_id: str) -> bool:
        url = f"{APPLE_MUSIC_API_BASE}/me/library/playlists/{playlist_id}"
        response = self._request("DELETE", url)
        if not response:
            return False
        if response.status_code in (200, 202, 204):
            logger.info("Deleted playlist id %s", playlist_id)
            return True
        return False

    # ##################################################################
    # find or create playlist
    # gets existing playlist by name or creates new one
    def find_or_create_playlist(self, name: str) -> dict | None:
        playlist = self.find_library_playlist_by_name(name)
        if playlist:
            return playlist
        logger.info("Creating new playlist: %s", name)
        created = self.create_library_playlist(name)
        if not created:
            return None
        playlist_id = created.get("id")
        if not playlist_id:
            logger.error("Created playlist missing id for %s", name)
            return None
        return created


# ##################################################################
# search song in catalog
# searches for a specific song by title and artist
def search_song_in_catalog(client: AppleMusicClient, song: str, artist: str) -> str | None:
    query = f"{artist} {song}"
    results = client.search_catalog(query, limit=5)
    if not results:
        return None
    song_lower = song.lower()
    artist_lower = artist.lower()
    for result in results:
        attrs = result.get("attributes", {})
        title = attrs.get("name", "").lower()
        result_artist = attrs.get("artistName", "").lower()
        if song_lower in title and artist_lower in result_artist:
            return result.get("id")
    for result in results:
        attrs = result.get("attributes", {})
        title = attrs.get("name", "").lower()
        if song_lower in title:
            return result.get("id")
    if results:
        return results[0].get("id")
    return None
