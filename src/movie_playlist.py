import json
import logging
import re
import subprocess
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from src.apple_music_api import AppleMusicClient
from src.movie_artwork import fetch_movie_cover, slugify
from src.movie_soundtrack import MovieSoundtrack, SongEntry, find_movie_soundtrack

logger = logging.getLogger(__name__)

ARTWORK_JOBS_DIR = Path.home() / ".config" / "billboard" / "artwork_jobs"
ARTWORK_APP = Path(__file__).parent.parent / "tools" / "PlaylistArtwork" / "PlaylistArtwork.app"
REPORTS_DIR = Path(__file__).parent.parent / "output" / "movie_playlists"
MATCH_THRESHOLD = 0.72
AMBIGUOUS_THRESHOLD = 0.85


@dataclass
class TrackMatch:
    song: SongEntry
    status: str  # matched | ambiguous | missing
    item_type: str = ""
    item_id: str = ""
    found_title: str = ""
    found_artist: str = ""
    found_album: str = ""
    score: float = 0.0


# ##################################################################
# normalize
# lowercases, strips accents, bracketed qualifiers and punctuation for comparison
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\((?:feat|ft|with)\.?[^)]*\)|\[(?:feat|ft|with)\.?[^\]]*\]", " ", text)
    text = re.sub(r"\s-\s.*(remaster|single version|album version|radio edit|mono|stereo).*$", " ", text)
    text = re.sub(r"[(\[](?:[^)\]]*(remaster|single version|album version|radio edit|edit\b|mono|stereo|from |live at|single\b)[^)\]]*)[)\]]", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ##################################################################
# similarity
# fuzzy ratio that also rewards containment (e.g. "Lovefool" vs "Lovefool (Radio Edit)")
def similarity(wanted: str, found: str) -> float:
    na, nb = normalize(wanted), normalize(found)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    # a found title that merely adds qualifiers to the wanted title is fine; the reverse
    # ("O Verona (Reprise)" wanted, "O Verona" found) is a different track
    if len(na) >= 3 and f" {na} " in f" {nb} ":
        ratio = max(ratio, 0.9)
    return ratio


# ##################################################################
# artist similarity
# compares performers, allowing any credited artist on either side to match
def artist_similarity(wanted: str, found: str) -> float:
    split = r",|&| and | feat\.? | ft\.? | with | x "
    wanted_parts = [p for p in re.split(split, wanted.lower()) if p.strip()] or [wanted]
    found_parts = [p for p in re.split(split, found.lower()) if p.strip()] or [found]
    best = similarity(wanted, found)
    for w in wanted_parts:
        for f in found_parts:
            best = max(best, similarity(w, f))
    return best


# ##################################################################
# score candidate
# combined title/artist score, with a small bonus for soundtrack albums of this film
def score_candidate(song: SongEntry, attrs: dict, film_title: str) -> float:
    name = attrs.get("name", "")
    if " - " in name and attrs.get("artistName", "").lower() in ("various artists", "unknown artist", ""):
        artist_part, title_part = name.split(" - ", 1)
        attrs = {**attrs, "name": title_part, "artistName": artist_part}
    title_score = similarity(song.title, attrs.get("name", ""))
    artist_score = artist_similarity(song.artist, attrs.get("artistName", ""))
    score = 0.6 * title_score + 0.4 * artist_score
    album = normalize(attrs.get("albumName", ""))
    if normalize(film_title) and normalize(film_title) in album:
        score += 0.05
    haystack = f"{album} {normalize(attrs.get('artistName', ''))}"
    if re.search(r"karaoke|tribute|originally performed|made famous|cover version|lullaby|workout", haystack):
        score -= 0.3
    if re.search(r"\b(mixed|dj mix)\b", f"{album} {attrs.get('name', '').lower()}"):
        score -= 0.15
    if "live" not in normalize(song.title) and re.search(r"\blive\b|unplugged", normalize(f"{attrs.get('name', '')} {attrs.get('albumName', '')}")):
        score -= 0.1
    if title_score < 0.6 or artist_score < 0.5:
        score = min(score, 0.6)
    return min(score, 1.0)


# ##################################################################
# match song
# finds the best catalog recording, falling back to the user's own library
def match_song(client: AppleMusicClient, storefront: str, song: SongEntry, film_title: str) -> TrackMatch:
    best: TrackMatch = TrackMatch(song=song, status="missing")
    queries = [f"{song.title} {song.artist}", song.title]
    for query in queries:
        for result in client.search_catalog_songs(query, storefront):
            attrs = result.get("attributes", {})
            if not attrs.get("playParams"):
                continue
            score = score_candidate(song, attrs, film_title)
            if score > best.score:
                best = TrackMatch(song, "matched", "songs", result["id"], attrs.get("name", ""),
                                  attrs.get("artistName", ""), attrs.get("albumName", ""), score)
        if best.score >= AMBIGUOUS_THRESHOLD:
            break
    if best.score < AMBIGUOUS_THRESHOLD:
        plain_title = re.sub(r"[^\w\s']", " ", song.title)
        # apple's library search is literal and short-query oriented: also try the film (album) name
        # and the most distinctive single words of the title
        words = sorted(re.findall(r"[A-Za-z0-9']{4,}", plain_title), key=len, reverse=True)[:2]
        library_queries = [f"{song.title} {song.artist}", song.title, plain_title, film_title, *words]
        library_results = [r for q in dict.fromkeys(q.strip() for q in library_queries) for r in client.search_library_songs(q)]
        for result in library_results:
            attrs = result.get("attributes", {})
            score = score_candidate(song, attrs, film_title)
            if score > best.score:
                best = TrackMatch(song, "matched", "library-songs", result["id"], attrs.get("name", ""),
                                  attrs.get("artistName", ""), attrs.get("albumName", ""), score)
    if best.score < MATCH_THRESHOLD:
        return TrackMatch(song=song, status="missing", score=best.score, found_title=best.found_title,
                          found_artist=best.found_artist)
    if best.score < AMBIGUOUS_THRESHOLD:
        best.status = "ambiguous"
    return best


# ##################################################################
# playlist name
# stable, unique-ish name so reruns replace the same playlist
def playlist_name(soundtrack: MovieSoundtrack) -> str:
    return f"{soundtrack.film_title} ({soundtrack.year}) Soundtrack"


# ##################################################################
# queue artwork
# writes a job for the PlaylistArtwork helper and launches it detached
def queue_artwork(name: str, cover: Path) -> Path:
    ARTWORK_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job = ARTWORK_JOBS_DIR / f"{int(time.time())}-{slugify(name)}.json"
    job.write_text(json.dumps({"playlist_name": name, "image_path": str(cover)}, indent=2))
    launch_artwork_helper()
    return job


# ##################################################################
# launch artwork helper
# starts the signed helper app as its own process so macOS attributes the music permission to it
def launch_artwork_helper() -> None:
    if not ARTWORK_APP.exists():
        subprocess.run([str(ARTWORK_APP.parent / "build.sh")], check=True)
    running = subprocess.run(["pgrep", "-f", "PlaylistArtwork.app/Contents/MacOS/PlaylistArtwork"], capture_output=True)
    if running.returncode == 0:
        logger.info("PlaylistArtwork helper already running; it rescans the job queue on every pass")
        return
    result = subprocess.run(["open", "-g", "-a", str(ARTWORK_APP)], capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("Could not launch PlaylistArtwork helper: %s", result.stderr.strip())


# ##################################################################
# artwork status
# reads the helper's last status file
def artwork_status() -> dict:
    status = ARTWORK_JOBS_DIR / "status.json"
    return json.loads(status.read_text()) if status.exists() else {}


# ##################################################################
# create movie playlist
# full pipeline: songs -> matches -> poster -> playlist -> ordered tracks -> artwork -> report
def create_movie_playlist(client: AppleMusicClient, query: str, require: list[str] | None = None) -> dict:
    storefront = client.get_storefront()
    soundtrack = find_movie_soundtrack(query)
    logger.info("%s (%d): %d songs, order: %s", soundtrack.film_title, soundtrack.year, len(soundtrack.songs), soundtrack.order_basis)
    matches = [match_song(client, storefront, song, soundtrack.film_title) for song in soundtrack.songs]
    usable = [m for m in matches if m.status == "matched"]
    for needle in require or []:
        if not any(needle.lower() in f"{m.found_title} {m.found_artist}".lower() for m in usable):
            raise RuntimeError(f"Required track {needle!r} could not be matched; playlist not created")
    seen: set[str] = set()
    items: list[tuple[str, str]] = []
    for m in usable:
        key = f"{normalize(m.found_title)}|{normalize(m.found_artist)}"
        if m.item_id not in seen and key not in seen:
            seen.update({m.item_id, key})
            items.append((m.item_type, m.item_id))
    if not items:
        raise RuntimeError(f"No songs matched for {soundtrack.film_title}")

    cover = fetch_movie_cover(soundtrack.film_article, soundtrack.film_title, soundtrack.year)
    # apple's api only allows create + append (delete/rename/reorder return 401), so an existing
    # playlist cannot be replaced: pick an unused name and report the older one for manual deletion
    base_name = playlist_name(soundtrack)
    taken = {p.get("attributes", {}).get("name") for p in client.get_library_playlists()}
    name, n = base_name, 2
    while name in taken:
        name, n = f"{base_name} ({n})", n + 1
    superseded = sorted(t for t in taken if t and (t == base_name or t.startswith(f"{base_name} (")))
    description = (
        f"Songs from {soundtrack.film_title} ({soundtrack.year}). Order: {soundtrack.order_basis}. "
        f"Source: Wikipedia ({', '.join(soundtrack.source_articles)})."
    )
    created = client.create_library_playlist(name, description[:1000])
    if not created:
        raise RuntimeError(f"Apple Music refused to create playlist {name}")
    playlist_id = created["id"]
    if not client.add_items_to_playlist(playlist_id, items):
        raise RuntimeError(f"Apple Music refused to add tracks to {name}")
    time.sleep(3)
    tracks = client.get_library_playlist_tracks(playlist_id)
    job = queue_artwork(name, cover)

    report = {
        "query": query,
        "film": soundtrack.film_title,
        "year": soundtrack.year,
        "playlist_name": name,
        "playlist_id": playlist_id,
        "superseded_playlists": superseded,
        "order_basis": soundtrack.order_basis,
        "sources": soundtrack.source_articles,
        "cover": str(cover),
        "artwork_job": str(job),
        "tracks_in_playlist": len(tracks),
        "matches": [
            {
                "position": i,
                "wanted": f"{m.song.title} — {m.song.artist}",
                "status": m.status,
                "found": f"{m.found_title} — {m.found_artist} [{m.found_album}]" if m.found_title else "",
                "type": m.item_type,
                "score": round(m.score, 2),
                "note": m.song.note,
            }
            for i, m in enumerate(matches, 1)
        ],
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / f"{slugify(name)}.json").write_text(json.dumps(report, indent=2))
    return report


# ##################################################################
# format report
# human-readable summary of what matched
def format_report(report: dict) -> str:
    lines = [
        f"Playlist: {report['playlist_name']}  ({report['tracks_in_playlist']} tracks in Apple Music)",
        f"Order: {report['order_basis']}",
        f"Cover: {report['cover']}",
    ]
    for m in report["matches"]:
        mark = {"matched": "OK ", "ambiguous": "?? ", "missing": "-- "}[m["status"]]
        found = f" -> {m['found']}" if m["found"] and m["status"] != "missing" else ""
        lines.append(f"{mark}{m['position']:>2}. {m['wanted']}{found}")
    if report.get("superseded_playlists"):
        lines.append(f"Older playlists to delete manually in Music: {report['superseded_playlists']}")
    missing = [m for m in report["matches"] if m["status"] == "missing"]
    ambiguous = [m for m in report["matches"] if m["status"] == "ambiguous"]
    lines.append(f"Matched {len(report['matches']) - len(missing)}/{len(report['matches'])}; ambiguous {len(ambiguous)}; missing {len(missing)}")
    return "\n".join(lines)
