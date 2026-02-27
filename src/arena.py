import sqlite3
import random
import logging
from collections import deque

logger = logging.getLogger(__name__)

ARENA_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS arena_song (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song TEXT NOT NULL,
    artist TEXT NOT NULL,
    decade INTEGER NOT NULL,
    elo_score REAL DEFAULT 1000.0,
    appearances INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    UNIQUE(song, artist)
);

CREATE TABLE IF NOT EXISTS arena_match (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    winner_id INTEGER NOT NULL,
    loser_id INTEGER NOT NULL,
    winner_elo_before REAL NOT NULL,
    loser_elo_before REAL NOT NULL,
    winner_elo_after REAL NOT NULL,
    loser_elo_after REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (winner_id) REFERENCES arena_song(id),
    FOREIGN KEY (loser_id) REFERENCES arena_song(id)
);

CREATE TABLE IF NOT EXISTS arena_matchup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_lo_id INTEGER NOT NULL,
    song_hi_id INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(song_lo_id, song_hi_id)
);
"""

MIGRATE_ELIMINATED_SQL = """
ALTER TABLE arena_song ADD COLUMN eliminated INTEGER DEFAULT 0;
"""


# ##################################################################
# ensure arena schema
# creates arena tables if they do not exist, migrates eliminated column
def ensure_arena_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(ARENA_SCHEMA_SQL)
    conn.commit()
    # migrate: add eliminated column if missing
    cols = [row[1] for row in conn.execute("PRAGMA table_info(arena_song)").fetchall()]
    if "eliminated" not in cols:
        conn.execute(MIGRATE_ELIMINATED_SQL)
        conn.commit()


# ##################################################################
# seed arena
# populates arena_song from chart data via get_top_songs_for_decade
def seed_arena(conn: sqlite3.Connection) -> dict:
    from src.top_songs import get_top_songs_for_decade, get_all_decades_with_data

    ensure_arena_schema(conn)
    decades = get_all_decades_with_data(conn)
    added = 0
    skipped = 0
    for decade in decades:
        songs = get_top_songs_for_decade(conn, decade)
        for song in songs:
            try:
                conn.execute(
                    "INSERT INTO arena_song (song, artist, decade) VALUES (?, ?, ?)",
                    (song.song, song.artist, decade),
                )
                added += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
    logger.info("Arena seeded: added=%d skipped=%d decades=%d", added, skipped, len(decades))
    return {"added": added, "skipped": skipped, "decades": len(decades)}


# ##################################################################
# calculate elo (legacy, kept for historical compatibility)
def calculate_elo(winner_elo: float, loser_elo: float, k: float = 32) -> tuple[float, float]:
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_loser = 1 - expected_winner
    new_winner_elo = winner_elo + k * (1 - expected_winner)
    new_loser_elo = loser_elo + k * (0 - expected_loser)
    return new_winner_elo, new_loser_elo


# ##################################################################
# record matchup
# normalizes IDs to lo/hi order, inserts into arena_matchup
# outcome from caller: 'a_wins'|'b_wins'|'tie'
def record_matchup(conn: sqlite3.Connection, song_a_id: int, song_b_id: int, outcome: str) -> None:
    lo = min(song_a_id, song_b_id)
    hi = max(song_a_id, song_b_id)
    if outcome == "a_wins":
        stored = "lo_wins" if song_a_id == lo else "hi_wins"
    elif outcome == "b_wins":
        stored = "lo_wins" if song_b_id == lo else "hi_wins"
    elif outcome == "tie":
        stored = "tie"
    else:
        raise ValueError(f"Invalid outcome: {outcome}")
    conn.execute(
        "INSERT INTO arena_matchup (song_lo_id, song_hi_id, outcome) VALUES (?, ?, ?)",
        (lo, hi, stored),
    )
    conn.commit()


# ##################################################################
# eliminate song
# marks a song as eliminated
def eliminate_song(conn: sqlite3.Connection, song_id: int) -> None:
    conn.execute("UPDATE arena_song SET eliminated = 1 WHERE id = ?", (song_id,))
    conn.commit()


# ##################################################################
# get matchup
# returns two random non-eliminated songs with no existing matchup
def get_matchup(conn: sqlite3.Connection) -> tuple[dict, dict] | None:
    candidates = [
        dict(row)
        for row in conn.execute(
            "SELECT id, song, artist, decade FROM arena_song WHERE eliminated = 0"
        ).fetchall()
    ]
    if len(candidates) < 2:
        return None
    random.shuffle(candidates)
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a, b = candidates[i], candidates[j]
            lo = min(a["id"], b["id"])
            hi = max(a["id"], b["id"])
            existing = conn.execute(
                "SELECT 1 FROM arena_matchup WHERE song_lo_id = ? AND song_hi_id = ?",
                (lo, hi),
            ).fetchone()
            if not existing:
                return a, b
    return None


# ##################################################################
# get matchup for song
# returns a matchup where one side is the given song, paired with a random opponent
def get_matchup_for_song(conn: sqlite3.Connection, song_id: int) -> tuple[dict, dict] | None:
    song_row = conn.execute(
        "SELECT id, song, artist, decade FROM arena_song WHERE id = ? AND eliminated = 0",
        (song_id,),
    ).fetchone()
    if not song_row:
        return None
    song = dict(song_row)
    candidates = [
        dict(row)
        for row in conn.execute(
            "SELECT id, song, artist, decade FROM arena_song WHERE eliminated = 0 AND id != ?",
            (song_id,),
        ).fetchall()
    ]
    random.shuffle(candidates)
    for candidate in candidates:
        lo = min(song["id"], candidate["id"])
        hi = max(song["id"], candidate["id"])
        existing = conn.execute(
            "SELECT 1 FROM arena_matchup WHERE song_lo_id = ? AND song_hi_id = ?",
            (lo, hi),
        ).fetchone()
        if not existing:
            return song, candidate
    return None


# ##################################################################
# compute scores
# BFS transitive reachability: score = number of songs you transitively beat
def compute_scores(conn: sqlite3.Connection) -> dict[int, int]:
    rows = conn.execute(
        "SELECT song_lo_id, song_hi_id, outcome FROM arena_matchup WHERE outcome != 'tie'"
    ).fetchall()
    # build adjacency: winner -> [losers]
    graph: dict[int, list[int]] = {}
    nodes: set[int] = set()
    for row in rows:
        lo, hi, outcome = row["song_lo_id"], row["song_hi_id"], row["outcome"]
        nodes.add(lo)
        nodes.add(hi)
        if outcome == "lo_wins":
            graph.setdefault(lo, []).append(hi)
        else:  # hi_wins
            graph.setdefault(hi, []).append(lo)
    # BFS from each node
    scores: dict[int, int] = {}
    for node in nodes:
        visited: set[int] = {node}  # exclude self from reachability
        queue = deque(graph.get(node, []))
        while queue:
            cur = queue.popleft()
            if cur in visited:
                continue
            visited.add(cur)
            for neighbor in graph.get(cur, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        scores[node] = len(visited) - 1  # subtract self
    return scores


# ##################################################################
# get leaderboard
# computes graph scores, joins with song data, returns sorted list
def get_leaderboard(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    scores = compute_scores(conn)
    if not scores:
        return []
    song_ids = list(scores.keys())
    placeholders = ",".join("?" * len(song_ids))
    rows = conn.execute(
        f"SELECT id, song, artist, decade FROM arena_song WHERE id IN ({placeholders})",
        song_ids,
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["score"] = scores.get(d["id"], 0)
        result.append(d)
    result.sort(key=lambda x: x["score"], reverse=True)
    return result[:limit]


# ##################################################################
# get arena stats
# returns summary counts for the arena
def get_arena_stats(conn: sqlite3.Connection) -> dict:
    ensure_arena_schema(conn)
    total_songs = conn.execute("SELECT COUNT(*) as c FROM arena_song").fetchone()["c"]
    total_matchups = conn.execute("SELECT COUNT(*) as c FROM arena_matchup").fetchone()["c"]
    eliminated = conn.execute("SELECT COUNT(*) as c FROM arena_song WHERE eliminated = 1").fetchone()["c"]
    decades = conn.execute("SELECT DISTINCT decade FROM arena_song ORDER BY decade").fetchall()
    return {
        "total_songs": total_songs,
        "total_matches": total_matchups,
        "eliminated": eliminated,
        "decades": [row["decade"] for row in decades],
    }
