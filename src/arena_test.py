import sqlite3
import pytest
from src.arena import (
    ensure_arena_schema,
    record_matchup,
    eliminate_song,
    get_matchup,
    compute_scores,
    get_leaderboard,
    get_arena_stats,
    seed_arena,
    calculate_elo,
)
from src.database import SCHEMA_SQL


def make_test_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    ensure_arena_schema(conn)
    return conn


def insert_song(conn, song, artist, decade):
    conn.execute(
        "INSERT INTO arena_song (song, artist, decade) VALUES (?, ?, ?)",
        (song, artist, decade),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


class TestRecordMatchup:
    def test_normalizes_ids(self):
        conn = make_test_db()
        id_a = insert_song(conn, "Song A", "Artist A", 1980)
        id_b = insert_song(conn, "Song B", "Artist B", 1980)
        # pass b first, a second — should still store lo=min, hi=max
        record_matchup(conn, id_b, id_a, "a_wins")
        row = conn.execute("SELECT * FROM arena_matchup").fetchone()
        assert row["song_lo_id"] == min(id_a, id_b)
        assert row["song_hi_id"] == max(id_a, id_b)

    def test_a_wins_stored_correctly(self):
        conn = make_test_db()
        id_a = insert_song(conn, "Song A", "Artist A", 1980)  # id=1
        id_b = insert_song(conn, "Song B", "Artist B", 1980)  # id=2
        # a is lo (id=1), a wins → lo_wins
        record_matchup(conn, id_a, id_b, "a_wins")
        row = conn.execute("SELECT * FROM arena_matchup").fetchone()
        assert row["outcome"] == "lo_wins"

    def test_b_wins_stored_correctly(self):
        conn = make_test_db()
        id_a = insert_song(conn, "Song A", "Artist A", 1980)  # id=1
        id_b = insert_song(conn, "Song B", "Artist B", 1980)  # id=2
        # b is hi (id=2), b wins → hi_wins
        record_matchup(conn, id_a, id_b, "b_wins")
        row = conn.execute("SELECT * FROM arena_matchup").fetchone()
        assert row["outcome"] == "hi_wins"

    def test_no_duplicate_matchups(self):
        conn = make_test_db()
        id_a = insert_song(conn, "Song A", "Artist A", 1980)
        id_b = insert_song(conn, "Song B", "Artist B", 1980)
        record_matchup(conn, id_a, id_b, "a_wins")
        with pytest.raises(sqlite3.IntegrityError):
            record_matchup(conn, id_a, id_b, "b_wins")

    def test_no_duplicate_reversed_order(self):
        conn = make_test_db()
        id_a = insert_song(conn, "Song A", "Artist A", 1980)
        id_b = insert_song(conn, "Song B", "Artist B", 1980)
        record_matchup(conn, id_a, id_b, "a_wins")
        with pytest.raises(sqlite3.IntegrityError):
            record_matchup(conn, id_b, id_a, "b_wins")


class TestComputeScores:
    def test_chain(self):
        """A>B>C → A=2, B=1, C=0"""
        conn = make_test_db()
        a = insert_song(conn, "A", "X", 1980)
        b = insert_song(conn, "B", "X", 1980)
        c = insert_song(conn, "C", "X", 1980)
        record_matchup(conn, a, b, "a_wins")
        record_matchup(conn, b, c, "a_wins")
        scores = compute_scores(conn)
        assert scores[a] == 2
        assert scores[b] == 1
        assert scores[c] == 0

    def test_diamond(self):
        """A>B, A>C, B>D, C>D → A=3, B=1, C=1, D=0"""
        conn = make_test_db()
        a = insert_song(conn, "A", "X", 1980)
        b = insert_song(conn, "B", "X", 1980)
        c = insert_song(conn, "C", "X", 1980)
        d = insert_song(conn, "D", "X", 1980)
        record_matchup(conn, a, b, "a_wins")
        record_matchup(conn, a, c, "a_wins")
        record_matchup(conn, b, d, "a_wins")
        record_matchup(conn, c, d, "a_wins")
        scores = compute_scores(conn)
        assert scores[a] == 3
        assert scores[b] == 1
        assert scores[c] == 1
        assert scores[d] == 0

    def test_tie_no_edge(self):
        """Ties create no edges — don't affect scores"""
        conn = make_test_db()
        a = insert_song(conn, "A", "X", 1980)
        b = insert_song(conn, "B", "X", 1980)
        record_matchup(conn, a, b, "tie")
        scores = compute_scores(conn)
        # no non-tie matchups, so no nodes in graph
        assert scores.get(a, 0) == 0
        assert scores.get(b, 0) == 0

    def test_cycle_handling(self):
        """A>B>C>A → each reaches 2"""
        conn = make_test_db()
        a = insert_song(conn, "A", "X", 1980)
        b = insert_song(conn, "B", "X", 1980)
        c = insert_song(conn, "C", "X", 1980)
        record_matchup(conn, a, b, "a_wins")
        record_matchup(conn, b, c, "a_wins")
        record_matchup(conn, c, a, "a_wins")
        scores = compute_scores(conn)
        assert scores[a] == 2
        assert scores[b] == 2
        assert scores[c] == 2

    def test_empty(self):
        conn = make_test_db()
        scores = compute_scores(conn)
        assert scores == {}


class TestEliminateSong:
    def test_eliminate_excludes_from_matchup(self):
        conn = make_test_db()
        a = insert_song(conn, "A", "X", 1980)
        insert_song(conn, "B", "X", 1980)
        insert_song(conn, "C", "X", 1980)
        eliminate_song(conn, a)
        # try many times — a should never appear
        for _ in range(20):
            result = get_matchup(conn)
            assert result is not None
            s1, s2 = result
            assert s1["id"] != a
            assert s2["id"] != a


class TestGetMatchup:
    def test_returns_two_songs(self):
        conn = make_test_db()
        insert_song(conn, "Song A", "Artist A", 1980)
        insert_song(conn, "Song B", "Artist B", 1980)
        result = get_matchup(conn)
        assert result is not None
        a, b = result
        assert a["id"] != b["id"]

    def test_returns_none_when_insufficient(self):
        conn = make_test_db()
        insert_song(conn, "Only Song", "Only Artist", 1980)
        assert get_matchup(conn) is None

    def test_avoids_existing_matchup(self):
        conn = make_test_db()
        a = insert_song(conn, "A", "X", 1980)
        b = insert_song(conn, "B", "X", 1980)
        record_matchup(conn, a, b, "a_wins")
        # only 2 songs, already matched — should return None
        assert get_matchup(conn) is None

    def test_returns_unmatched_pair(self):
        conn = make_test_db()
        a = insert_song(conn, "A", "X", 1980)
        b = insert_song(conn, "B", "X", 1980)
        c = insert_song(conn, "C", "X", 1980)
        record_matchup(conn, a, b, "a_wins")
        # should still find a pair involving c
        result = get_matchup(conn)
        assert result is not None
        ids = {result[0]["id"], result[1]["id"]}
        assert c in ids


class TestGetLeaderboard:
    def test_sorted_by_score(self):
        conn = make_test_db()
        a = insert_song(conn, "A", "X", 1980)
        b = insert_song(conn, "B", "X", 1980)
        c = insert_song(conn, "C", "X", 1980)
        record_matchup(conn, a, b, "a_wins")
        record_matchup(conn, b, c, "a_wins")
        lb = get_leaderboard(conn)
        assert lb[0]["song"] == "A"
        assert lb[0]["score"] == 2
        assert lb[1]["song"] == "B"
        assert lb[1]["score"] == 1
        assert lb[2]["song"] == "C"
        assert lb[2]["score"] == 0

    def test_respects_limit(self):
        conn = make_test_db()
        songs = []
        for i in range(10):
            s = insert_song(conn, f"S{i}", "X", 1980)
            songs.append(s)
        # chain: s0 > s1 > s2 > ... > s9
        for i in range(9):
            record_matchup(conn, songs[i], songs[i + 1], "a_wins")
        lb = get_leaderboard(conn, limit=3)
        assert len(lb) == 3

    def test_empty(self):
        conn = make_test_db()
        assert get_leaderboard(conn) == []


class TestGetArenaStats:
    def test_empty_arena(self):
        conn = make_test_db()
        stats = get_arena_stats(conn)
        assert stats["total_songs"] == 0
        assert stats["total_matches"] == 0
        assert stats["eliminated"] == 0

    def test_with_data(self):
        conn = make_test_db()
        a = insert_song(conn, "A", "X", 1980)
        b = insert_song(conn, "B", "X", 1990)
        record_matchup(conn, a, b, "a_wins")
        eliminate_song(conn, b)
        stats = get_arena_stats(conn)
        assert stats["total_songs"] == 2
        assert stats["total_matches"] == 1
        assert stats["eliminated"] == 1
        assert 1980 in stats["decades"]
        assert 1990 in stats["decades"]


class TestSeedArena:
    def test_seed_from_chart_data(self):
        conn = make_test_db()
        conn.execute("INSERT INTO chart (id, name, display_name, source) VALUES (1, 'hot-100', 'Hot 100', 'billboard')")
        conn.execute("INSERT INTO chart_week (id, chart_id, chart_date) VALUES (1, 1, '1980-06-01')")
        for i in range(1, 11):
            conn.execute(
                "INSERT INTO entry (chart_week_id, position, song, artist, peak_position, weeks_on_chart) VALUES (?, ?, ?, ?, ?, ?)",
                (1, i, f"Song {i}", f"Artist {i}", i, 20 - i),
            )
        conn.commit()
        result = seed_arena(conn)
        assert result["added"] > 0
        assert result["decades"] == 1
        count = conn.execute("SELECT COUNT(*) as c FROM arena_song").fetchone()["c"]
        assert count == result["added"]


class TestCalculateElo:
    def test_equal_players(self):
        new_w, new_l = calculate_elo(1000, 1000)
        assert abs(new_w - 1016) < 0.1
        assert abs(new_l - 984) < 0.1
