import requests
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
REQUEST_DELAY_SECONDS = 0.1


@dataclass
class ItunesTrack:
    track_id: int
    track_name: str
    artist_name: str
    collection_name: str


# ##################################################################
# search itunes
# searches itunes api for a song by title and artist
def search_itunes(song: str, artist: str) -> ItunesTrack | None:
    query = f"{artist} {song}"
    params = {
        "term": query,
        "media": "music",
        "entity": "song",
        "limit": 5,
    }
    try:
        response = requests.get(ITUNES_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if not results:
            return None
        best_match = find_best_match(results, song, artist)
        if best_match:
            return ItunesTrack(
                track_id=best_match["trackId"],
                track_name=best_match["trackName"],
                artist_name=best_match["artistName"],
                collection_name=best_match.get("collectionName", ""),
            )
        return None
    except requests.RequestException as err:
        logger.error("iTunes search failed: %s", err)
        return None


# ##################################################################
# find best match
# finds the best matching track from search results
def find_best_match(results: list[dict], song: str, artist: str) -> dict | None:
    song_lower = song.lower()
    artist_lower = artist.lower()
    for result in results:
        track_name = result.get("trackName", "").lower()
        artist_name = result.get("artistName", "").lower()
        if song_lower in track_name and artist_lower in artist_name:
            return result
    for result in results:
        track_name = result.get("trackName", "").lower()
        if song_lower in track_name:
            return result
    if results:
        return results[0]
    return None


# ##################################################################
# rate limit
# pauses execution to respect api rate limits
def rate_limit() -> None:
    import threading

    event = threading.Event()
    event.wait(timeout=REQUEST_DELAY_SECONDS)


# ##################################################################
# search itunes with delay
# searches itunes with rate limiting delay
def search_itunes_with_delay(song: str, artist: str) -> ItunesTrack | None:
    rate_limit()
    return search_itunes(song, artist)
