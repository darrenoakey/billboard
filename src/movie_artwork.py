import io
import logging
import re
from pathlib import Path

import requests
from urllib.parse import unquote
from bs4 import BeautifulSoup
from PIL import Image, ImageFilter

from src.movie_soundtrack import USER_AGENT, WIKI_API

logger = logging.getLogger(__name__)

MOVIE_COVERS_DIR = Path(__file__).parent.parent / "playlist_covers" / "movies"
COVER_SIZE = 1400


# ##################################################################
# slugify
# filesystem-safe name for a film
def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ##################################################################
# poster url
# the lead (infobox) image of the film's wikipedia article is its theatrical release poster
def poster_url(film_article: str) -> str:
    headers = {"User-Agent": USER_AGENT}
    params = {"action": "parse", "page": film_article, "prop": "text", "format": "json", "redirects": 1}
    response = requests.get(WIKI_API, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.json()["parse"]["text"]["*"], "html.parser")
    infobox = soup.select_one("table.infobox")
    link = infobox.select_one("a.mw-file-description") if infobox else None
    if not link or not link.get("href", "").startswith("/wiki/File:"):
        raise LookupError(f"No infobox poster on Wikipedia article {film_article!r}")
    file_title = unquote(link["href"].removeprefix("/wiki/"))
    info_params = {"action": "query", "prop": "imageinfo", "iiprop": "url", "titles": file_title, "format": "json"}
    info = requests.get(WIKI_API, params=info_params, headers=headers, timeout=30)
    info.raise_for_status()
    for page in info.json().get("query", {}).get("pages", {}).values():
        for image in page.get("imageinfo", []):
            if image.get("url"):
                return image["url"]
    raise LookupError(f"Could not resolve poster file {file_title!r}")


# ##################################################################
# square cover
# fits the portrait poster onto a square canvas over a blurred fill of itself
def square_cover(poster: Image.Image, size: int = COVER_SIZE) -> Image.Image:
    poster = poster.convert("RGB")
    background = poster.resize((size, size), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
    scale = size / max(poster.width, poster.height)
    fitted = poster.resize((round(poster.width * scale), round(poster.height * scale)), Image.LANCZOS)
    background.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    return background


# ##################################################################
# fetch movie cover
# downloads the official poster and writes a square playlist cover jpeg
def fetch_movie_cover(film_article: str, film_title: str, year: int) -> Path:
    url = poster_url(film_article)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    poster = Image.open(io.BytesIO(response.content))
    MOVIE_COVERS_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(f"{film_title}-{year}")
    (MOVIE_COVERS_DIR / f"{slug}-poster{Path(url).suffix.lower() or '.jpg'}").write_bytes(response.content)
    cover_path = MOVIE_COVERS_DIR / f"{slug}.jpg"
    square_cover(poster).save(cover_path, "JPEG", quality=92)
    logger.info("Poster %s -> %s", url, cover_path)
    return cover_path
