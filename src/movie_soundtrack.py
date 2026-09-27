import difflib
import html
import json
import subprocess
import time
import logging
import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel


logger = logging.getLogger(__name__)

WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "billboard-movie-playlist/1.0 (darren@insidemind.com.au)"
MAX_SOURCE_CHARS = 60000
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
LLM_MODEL = "gpt-5.1"


# ##################################################################
# ask json
# one llm call returning a parsed json object (openai key comes from daz-secrets)
def ask_json(prompt: str) -> dict:
    key = subprocess.run(
        ["daz-secrets", "get", "openai", "api_key"], capture_output=True, text=True, check=True
    ).stdout.strip()
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }
    response = requests.post(OPENAI_URL, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=240)
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


# ##################################################################
# llm schemas
# structured outputs for film resolution and song list extraction
class FilmChoice(BaseModel):
    film_article: str
    film_title: str
    year: int
    soundtrack_articles: list[str]
    reasoning: str


class SongEntry(BaseModel):
    title: str
    artist: str
    source: str
    note: str


class SongList(BaseModel):
    order_basis: str
    songs: list[SongEntry]


@dataclass
class MovieSoundtrack:
    film_title: str
    year: int
    film_article: str
    source_articles: list[str]
    order_basis: str
    songs: list[SongEntry] = field(default_factory=list)


# ##################################################################
# wikipedia session
# shared http session with a descriptive user agent
def wiki_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


# ##################################################################
# wiki search
# full-text wikipedia search returning page titles with snippets
def wiki_search(session: requests.Session, query: str, limit: int = 8) -> list[dict]:
    params = {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": limit}
    response = session.get(WIKI_API, params=params, timeout=30)
    response.raise_for_status()
    results = response.json().get("query", {}).get("search", [])
    return [{"title": r["title"], "snippet": re.sub(r"<[^>]+>", "", r.get("snippet", ""))} for r in results]


# ##################################################################
# wiki page text
# renders a wikipedia page to plain text, keeping track-listing tables as rows
def wiki_page_text(session: requests.Session, title: str) -> tuple[str, str, list[str]]:
    params = {"action": "parse", "page": title, "prop": "text|links", "format": "json", "redirects": 1}
    response = session.get(WIKI_API, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise LookupError(f"Wikipedia page not found: {title}")
    parse = data["parse"]
    soup = BeautifulSoup(parse["text"]["*"], "html.parser")
    for tag in soup.select("sup.reference, style, script, .mw-editsection, .navbox, .reflist, .metadata"):
        tag.decompose()
    for row in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
        row.replace_with(soup.new_string(" | ".join(cells) + "\n"))
    for item in soup.find_all("li"):
        item.insert_before(soup.new_string("\n- "))
    for heading in soup.find_all(["h2", "h3", "h4"]):
        heading.insert_before(soup.new_string("\n\n## "))
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text())
    links = [link["*"] for link in parse.get("links", []) if link.get("ns") == 0]
    return parse["title"], text, links


# ##################################################################
# closest title
# snaps an llm-returned article title onto a real candidate title
def closest_title(title: str, candidates: list[str]) -> str:
    title = html.unescape(title).strip()
    if title in candidates:
        return title
    ranked = difflib.get_close_matches(title, candidates, n=1, cutoff=0.0)
    logger.info("Snapped article title %r -> %r", title, ranked[0] if ranked else title)
    return ranked[0] if ranked else title


# ##################################################################
# resolve film
# uses wikipedia search plus an llm to pick the intended film and its soundtrack articles
def resolve_film(session: requests.Session, query: str) -> FilmChoice:
    candidates: dict[str, str] = {}
    for search in (f"{query} film", f"{query} soundtrack", query):
        for hit in wiki_search(session, search):
            candidates.setdefault(hit["title"], html.unescape(hit["snippet"]))
    listing = "\n".join(f"- {title}: {snippet}" for title, snippet in candidates.items())
    choice = FilmChoice.model_validate(ask_json(
        "A user wants an Apple Music playlist of the songs from a movie. Their request: "
        f"{query!r}.\nWikipedia search results:\n{listing}\n\n"
        "Pick the Wikipedia article for the film they most plausibly mean (prefer the best-known film "
        "matching any year/director hints). film_article must be an exact title from the list. "
        "soundtrack_articles: exact titles from the list that are soundtrack albums for THAT film "
        "(may be empty). Reply with ONLY a JSON object with keys film_article, film_title, year (int), "
        "soundtrack_articles (list of str), reasoning."
    ))
    choice.film_article = closest_title(choice.film_article, list(candidates))
    _, film_text, links = wiki_page_text(session, choice.film_article)
    linked = [t for t in links if re.search(r"soundtrack|music from|volume 2|score", t, re.I)]
    if linked:
        choice = FilmChoice.model_validate(ask_json(
            f"Film: {choice.film_title} ({choice.year}), article {choice.film_article!r}.\n"
            f"Already chosen soundtrack articles: {choice.soundtrack_articles}.\n"
            f"Articles linked from the film page that look soundtrack-related: {linked}.\n"
            "Return the same film fields, with soundtrack_articles = the complete list of exact article "
            "titles (from either list) that are soundtrack albums of THIS film (all volumes). Exclude "
            "other films, singles and unrelated albums. Reply with ONLY a JSON object with keys film_article, "
            "film_title, year (int), soundtrack_articles (list of str), reasoning."
        ))
    film_words = {w for w in re.findall(r"[a-z0-9]+", choice.film_title.lower()) if len(w) >= 4}
    choice.soundtrack_articles = [
        t for t in choice.soundtrack_articles if film_words & set(re.findall(r"[a-z0-9]+", t.lower()))
    ]
    logger.info("Resolved %r -> %s (%d); soundtracks=%s", query, choice.film_article, choice.year, choice.soundtrack_articles)
    return choice


# ##################################################################
# extract songs
# asks the llm to build the ordered song list from the fetched source texts
def extract_songs(film: FilmChoice, sources: dict[str, str]) -> SongList:
    budget = MAX_SOURCE_CHARS // max(1, len(sources))
    blocks = "\n\n".join(f"===== SOURCE: {title} =====\n{text[:budget]}" for title, text in sources.items())
    prompt = (
        f"Build the song list for an Apple Music playlist of the film {film.film_title} ({film.year}).\n"
        "Use ONLY the sources below (Wikipedia film/soundtrack articles and MusicBrainz soundtrack tracklists). Rules:\n"
        "- Include every distinct song (vocal/pop songs and notable instrumental tracks) that the sources "
        "say is on the film's soundtrack album(s) or is featured in the film. Include every volume.\n"
        "- Skip dialogue-only tracks, bonus remixes/alternate versions of a song already listed, and pure "
        "score cues unless the soundtrack album is primarily score (then include the score tracks).\n"
        "- artist = the performer of the version used in the film/album (not the songwriter).\n"
        "- ORDER: if the sources describe the order songs appear in the film, use film order; otherwise use "
        "soundtrack album order (volume 1 then volume 2, etc.). State which in order_basis.\n"
        "- source = the source article the song came from; note = anything useful (e.g. 'Volume 2 track 3').\n"
        "- Never invent songs that are not in the sources.\n"
        'Reply with ONLY a JSON object: {"order_basis": str, "songs": [{"title": str, "artist": str, '
        '"source": str, "note": str}]}\n\n'
        f"{blocks}"
    )
    return SongList.model_validate(ask_json(prompt))


# ##################################################################
# musicbrainz soundtracks
# tracklists of soundtrack releases whose title matches the film (musicbrainz is keyless)
def musicbrainz_soundtracks(session: requests.Session, film_title: str, year: int, limit: int = 2) -> dict[str, str]:
    query = f'release:"{film_title}" AND secondarytype:soundtrack'
    response = session.get(MUSICBRAINZ_API + "/release/", params={"query": query, "fmt": "json", "limit": 10}, timeout=30)
    if response.status_code != 200:
        logger.warning("MusicBrainz search failed: %s", response.status_code)
        return {}
    releases = [r for r in response.json().get("releases", []) if r.get("score", 0) >= 90]
    releases.sort(key=lambda r: (abs(int((r.get("date") or "0")[:4] or 0) - year) > 2, -(r.get("track-count") or 0)))
    sources: dict[str, str] = {}
    seen_groups: set[str] = set()
    for release in releases:
        group = release.get("release-group", {}).get("id", "")
        if group in seen_groups or len(sources) >= limit:
            continue
        seen_groups.add(group)
        time.sleep(1)
        detail = session.get(
            f"{MUSICBRAINZ_API}/release/{release['id']}",
            params={"inc": "recordings artist-credits", "fmt": "json"},
            timeout=30,
        )
        if detail.status_code != 200:
            continue
        lines = [f"MusicBrainz soundtrack release: {release['title']} ({release.get('date', '?')}, {release.get('country', '?')})"]
        for medium in detail.json().get("media", []):
            for track in medium.get("tracks", []):
                artist = "".join(a["name"] + a.get("joinphrase", "") for a in track.get("artist-credit", []))
                lines.append(f"{medium.get('position', 1)}-{track['position']}. {track['title']} | {artist}")
        sources[f"MusicBrainz: {release['title']} ({release.get('date', '?')})"] = "\n".join(lines)
    return sources


# ##################################################################
# music sections
# keeps the lead plus sections about music/soundtrack/songs from a film article
def music_sections(text: str) -> str:
    parts = text.split("\n\n## ")
    keep = [parts[0][:4000]]
    for part in parts[1:]:
        heading = part.split("\n", 1)[0].lower()
        if re.search(r"music|soundtrack|song|score", heading):
            keep.append("## " + part)
    return "\n\n".join(keep)


# ##################################################################
# find movie soundtrack
# end-to-end: resolve the film, gather sources, return ordered songs
def find_movie_soundtrack(query: str) -> MovieSoundtrack:
    session = wiki_session()
    film = resolve_film(session, query)
    sources: dict[str, str] = {}
    for title in [*film.soundtrack_articles, film.film_article]:
        try:
            resolved, text, _ = wiki_page_text(session, title)
        except LookupError as exc:
            logger.warning("%s", exc)
            continue
        if title == film.film_article:
            text = music_sections(text)
        sources.setdefault(resolved, text)
    for title, text in musicbrainz_soundtracks(session, film.film_title, film.year).items():
        sources.setdefault(title, text)
    if not sources:
        raise LookupError(f"No Wikipedia sources found for {query!r}")
    song_list = extract_songs(film, sources)
    return MovieSoundtrack(
        film_title=film.film_title,
        year=film.year,
        film_article=film.film_article,
        source_articles=list(sources),
        order_basis=song_list.order_basis,
        songs=song_list.songs,
    )
