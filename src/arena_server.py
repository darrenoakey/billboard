import hashlib
import http.server
import json
import logging
import re
import sqlite3
import socketserver
import webbrowser
from pathlib import Path

from src.arena import (
    ensure_arena_schema,
    seed_arena,
    get_matchup,
    get_matchup_for_song,
    record_matchup,
    eliminate_song,
    get_leaderboard,
    get_arena_stats,
    compute_scores,
)
from src.apple_music import load_config
from src.apple_music_api import AppleMusicConfig, generate_developer_token
from src.database import DatabaseConnection

logger = logging.getLogger(__name__)

PORT = 8780

STATIC_DIR = Path(__file__).parent.parent / "static"

_static_hashes: dict[str, str] = {}


def _build_static_hashes() -> None:
    """Scan static/ directory and compute SHA256 content hashes (once at startup)."""
    if _static_hashes:
        return
    if not STATIC_DIR.is_dir():
        return
    for f in STATIC_DIR.iterdir():
        if f.is_file():
            digest = hashlib.sha256(f.read_bytes()).hexdigest()[:12]
            _static_hashes[f.name] = digest


def resolve_static_tags(html: str) -> str:
    """Replace {{ static:filename }} tags with /static/filename?v=<hash>."""
    _build_static_hashes()

    def _replace(m: re.Match) -> str:
        name = m.group(1).strip()
        h = _static_hashes.get(name, "0")
        return f"/static/{name}?v={h}"

    return re.sub(r"\{\{\s*static:([^}]+)\}\}", _replace, html)


CONTENT_TYPES = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".html": "text/html",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".woff2": "font/woff2",
}

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Song Arena</title>
    <link rel="stylesheet" href="{{ static:arena.css }}">
</head>
<body>
    <div class="bg-glow"></div>

    <div class="hero">
        <img src="/images/logo" alt="" class="hero-logo" onerror="this.style.display='none'"><br>
        <h1>Song Arena</h1>
        <div class="tagline">Pick the better song. Build the ultimate ranking.</div>
    </div>

    <div class="stats-bar">
        <div>
            <div class="stat-value" id="statMatches">0</div>
            <div class="stat-label">Battles</div>
        </div>
        <div>
            <div class="stat-value" id="statSongs">0</div>
            <div class="stat-label">Songs</div>
        </div>
        <div>
            <div class="stat-value" id="statEliminated">0</div>
            <div class="stat-label">Eliminated</div>
        </div>
    </div>

    <div class="arena-container" id="arenaContainer">
        <div class="loading"><div class="spinner"></div><div>Loading matchup...</div></div>
    </div>

    <div class="tie-bar" id="tieBar" style="display:none;">
        <button class="tie-btn" onclick="recordTie()">Tie</button>
    </div>

    <div class="result-flash" id="resultFlash">
        <div class="result-content">
            <div class="winner-label" id="resultLabel">Winner</div>
            <div class="winner-song" id="resultSong"></div>
            <div class="winner-artist" id="resultArtist"></div>
            <div class="result-detail" id="resultDetail"></div>
        </div>
    </div>

    <div class="leaderboard-section">
        <div class="lb-header">
            <span class="trophy">&#127942;</span>
            <h2>Leaderboard</h2>
            <span class="trophy">&#127942;</span>
        </div>
        <div class="lb-divider"></div>
        <table class="lb-table">
            <tbody id="leaderboardBody">
                <tr><td class="lb-empty">Vote to see rankings appear here</td></tr>
            </tbody>
        </table>
    </div>

    <script src="https://js-cdn.music.apple.com/musickit/v3/musickit.js" async></script>
    <script>const DEV_TOKEN = '__DEV_TOKEN__';</script>
    <script src="{{ static:arena.js }}"></script>
</body>
</html>"""


# ##################################################################
# arena handler
# serves the arena spa and api endpoints
class ArenaHandler(http.server.BaseHTTPRequestHandler):
    db_conn: sqlite3.Connection | None = None
    dev_token: str | None = None

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_html()
        elif self.path == "/api/token":
            self._json_response({"token": ArenaHandler.dev_token})
        elif self.path == "/api/matchup" or self.path.startswith("/api/matchup?"):
            self._serve_matchup()
        elif self.path.startswith("/api/leaderboard"):
            self._serve_leaderboard()
        elif self.path == "/api/stats":
            self._serve_stats()
        elif self.path.startswith("/static/"):
            self._serve_static()
        elif self.path == "/images/logo":
            self._serve_image("arena_logo.png")
        elif self.path == "/images/banner":
            self._serve_image("arena_banner.jpg")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/matchup-result":
            self._handle_matchup_result()
        elif self.path == "/api/eliminate":
            self._handle_eliminate()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        html = HTML_PAGE.replace("__DEV_TOKEN__", ArenaHandler.dev_token or "")
        html = resolve_static_tags(html)
        self.wfile.write(html.encode())

    def _serve_static(self):
        # Strip query string, extract filename
        path = self.path.split("?")[0]
        name = path.removeprefix("/static/")
        # Prevent path traversal
        if "/" in name or name.startswith("."):
            self.send_response(404)
            self.end_headers()
            return
        file_path = STATIC_DIR / name
        if not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        ext = file_path.suffix.lower()
        content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _serve_matchup(self):
        conn = ArenaHandler.db_conn
        assert conn is not None
        # Parse query string for keep_song_id
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        keep_id = params.get("keep_song_id", [None])[0]
        if keep_id:
            result = get_matchup_for_song(conn, int(keep_id))
        else:
            result = get_matchup(conn)
        if result is None:
            self._json_response({"error": "No more matchups available"})
        else:
            a, b = result
            scores = compute_scores(conn)
            a["score"] = scores.get(a["id"], 0)
            b["score"] = scores.get(b["id"], 0)
            self._json_response({"song_a": a, "song_b": b})

    def _serve_leaderboard(self):
        conn = ArenaHandler.db_conn
        assert conn is not None
        self._json_response(get_leaderboard(conn))

    def _serve_stats(self):
        conn = ArenaHandler.db_conn
        assert conn is not None
        self._json_response(get_arena_stats(conn))

    def _handle_matchup_result(self):
        conn = ArenaHandler.db_conn
        assert conn is not None
        data = self._read_json()
        song_a_id = data["song_a_id"]
        song_b_id = data["song_b_id"]
        outcome = data["outcome"]
        record_matchup(conn, song_a_id, song_b_id, outcome)
        lb = get_leaderboard(conn)
        self._json_response({"leaderboard": lb})

    def _handle_eliminate(self):
        conn = ArenaHandler.db_conn
        assert conn is not None
        data = self._read_json()
        song_id = data["song_id"]
        eliminate_song(conn, song_id)
        self._json_response({"ok": True})

    def _read_json(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        return json.loads(body.decode())

    def _serve_image(self, filename: str):
        image_dir = Path(__file__).parent.parent / "arena_images"
        image_path = image_dir / filename
        if image_path.exists():
            ext = image_path.suffix.lower()
            content_type = "image/png" if ext == ".png" else "image/jpeg"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(image_path.read_bytes())
        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):  # noqa: A002
        pass


# ##################################################################
# generate token
# creates a developer token using project config
def make_developer_token() -> str:
    cfg = load_config()
    config = AppleMusicConfig(
        team_id=cfg["apple_music_team_id"],
        key_id=cfg["apple_music_key_id"],
        private_key_path=Path(cfg["apple_music_private_key_path"]).expanduser(),
        music_user_token="",
    )
    return generate_developer_token(config)


# ##################################################################
# run arena server
# seeds database, starts web server, opens browser
def run_arena_server() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db = DatabaseConnection()
    conn = db.connect()
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_arena_schema(conn)

    stats = get_arena_stats(conn)
    if stats["total_songs"] == 0:
        print("Seeding arena with chart data...")
        result = seed_arena(conn)
        print(f"Seeded: {result['added']} songs from {result['decades']} decades")
    else:
        print(f"Arena has {stats['total_songs']} songs, {stats['total_matches']} matches")

    print("Generating developer token...")
    ArenaHandler.dev_token = make_developer_token()
    ArenaHandler.db_conn = conn

    with socketserver.TCPServer(("", PORT), ArenaHandler) as httpd:
        httpd.allow_reuse_address = True
        print(f"Song Arena running at http://localhost:{PORT}")
        print("Opening browser...")
        webbrowser.open(f"http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            db.close()


if __name__ == "__main__":
    run_arena_server()
