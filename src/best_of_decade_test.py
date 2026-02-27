import tempfile
from pathlib import Path

from src.database import DatabaseConnection, ChartRepository
from src.best_of_decade import (
    BestSongScore,
    get_best_songs_for_decade,
    get_best_songs_all_decades,
)


# ##################################################################
# helper to seed chart entries
# inserts a song at a given position for multiple weeks
def seed_song_weeks(
    conn,
    chart_id: int,
    song: str,
    artist: str,
    position: int,
    year: int,
    num_weeks: int,
) -> None:
    repo = ChartRepository(conn)
    for week in range(num_weeks):
        date = f"{year}-{(week % 12) + 1:02d}-{(week % 28) + 1:02d}"
        try:
            week_id = repo.insert_chart_week(chart_id, date)
        except Exception:
            # week already exists, find it
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM chart_week WHERE chart_id = ? AND chart_date = ?",
                (chart_id, date),
            )
            week_id = cursor.fetchone()["id"]
        repo.insert_entries(
            week_id,
            [
                {
                    "position": position,
                    "song": song,
                    "artist": artist,
                    "last_week": None,
                    "peak_position": position,
                    "weeks_on_chart": week + 1,
                }
            ],
        )


# ##################################################################
# test scoring formula values
# verifies cubic scoring gives expected results for known positions
def test_scoring_formula_values() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            # Song at #1 for 1 week: score = (100-1)^3 = 970299
            seed_song_weeks(conn, chart_id, "Number One Hit", "Artist A", 1, 1960, 1)
            songs = get_best_songs_for_decade(conn, 1960, limit=10)
            assert len(songs) == 1
            assert songs[0].total_score == 99 ** 3
            assert songs[0].total_score == 970299
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test scoring rewards longevity
# verifies that more weeks on chart produces higher total score
def test_scoring_rewards_longevity() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            # Song A at #1 for 5 weeks
            for w in range(5):
                week_id = repo.insert_chart_week(chart_id, f"1970-01-{w + 1:02d}")
                repo.insert_entries(week_id, [{"position": 1, "song": "Long Hit", "artist": "Artist A",
                                               "last_week": None, "peak_position": 1, "weeks_on_chart": w + 1}])
            # Song B at #1 for 2 weeks
            for w in range(2):
                week_id = repo.insert_chart_week(chart_id, f"1970-02-{w + 1:02d}")
                repo.insert_entries(week_id, [{"position": 1, "song": "Short Hit", "artist": "Artist B",
                                               "last_week": None, "peak_position": 1, "weeks_on_chart": w + 1}])
            songs = get_best_songs_for_decade(conn, 1970, limit=10)
            assert songs[0].song == "Long Hit"
            assert songs[0].total_score == 5 * (99 ** 3)
            assert songs[1].song == "Short Hit"
            assert songs[1].total_score == 2 * (99 ** 3)
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test scoring rewards higher position
# verifies that higher chart positions score more than lower ones
def test_scoring_rewards_higher_position() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            # Song A at #1 for 1 week
            week_id = repo.insert_chart_week(chart_id, "1980-01-01")
            repo.insert_entries(week_id, [{"position": 1, "song": "Top Song", "artist": "Artist A",
                                           "last_week": None, "peak_position": 1, "weeks_on_chart": 1}])
            # Song B at #50 for 1 week
            repo.insert_entries(week_id, [{"position": 50, "song": "Mid Song", "artist": "Artist B",
                                           "last_week": None, "peak_position": 50, "weeks_on_chart": 1}])
            songs = get_best_songs_for_decade(conn, 1980, limit=10)
            assert songs[0].song == "Top Song"
            assert songs[0].total_score == 99 ** 3  # 970299
            assert songs[1].song == "Mid Song"
            assert songs[1].total_score == 50 ** 3  # 125000
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test position 100 scores zero
# verifies that position 100 contributes zero to score
def test_position_100_scores_zero() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            week_id = repo.insert_chart_week(chart_id, "1990-01-01")
            repo.insert_entries(week_id, [{"position": 100, "song": "Bottom Song", "artist": "Artist Z",
                                           "last_week": None, "peak_position": 100, "weeks_on_chart": 1}])
            songs = get_best_songs_for_decade(conn, 1990, limit=10)
            assert len(songs) == 1
            assert songs[0].total_score == 0
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test decade filtering
# verifies songs from other decades are excluded
def test_decade_filtering() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            # Song in 1960s
            week_id = repo.insert_chart_week(chart_id, "1965-06-01")
            repo.insert_entries(week_id, [{"position": 1, "song": "60s Hit", "artist": "60s Artist",
                                           "last_week": None, "peak_position": 1, "weeks_on_chart": 1}])
            # Song in 1970s
            week_id = repo.insert_chart_week(chart_id, "1975-06-01")
            repo.insert_entries(week_id, [{"position": 1, "song": "70s Hit", "artist": "70s Artist",
                                           "last_week": None, "peak_position": 1, "weeks_on_chart": 1}])
            sixties = get_best_songs_for_decade(conn, 1960, limit=10)
            assert len(sixties) == 1
            assert sixties[0].song == "60s Hit"
            seventies = get_best_songs_for_decade(conn, 1970, limit=10)
            assert len(seventies) == 1
            assert seventies[0].song == "70s Hit"
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test limit parameter
# verifies that limit restricts number of results
def test_limit_parameter() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            for i in range(15):
                week_id = repo.insert_chart_week(chart_id, f"1960-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}")
                repo.insert_entries(week_id, [{"position": i + 1, "song": f"Song {i}", "artist": f"Artist {i}",
                                               "last_week": None, "peak_position": i + 1, "weeks_on_chart": 1}])
            songs = get_best_songs_for_decade(conn, 1960, limit=5)
            assert len(songs) == 5
            songs_all = get_best_songs_for_decade(conn, 1960, limit=10)
            assert len(songs_all) == 10
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test get best songs all decades
# verifies multi-decade aggregation
def test_get_best_songs_all_decades() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            for decade in [1960, 1970, 1980]:
                week_id = repo.insert_chart_week(chart_id, f"{decade + 5}-06-01")
                repo.insert_entries(week_id, [{"position": 1, "song": f"Hit {decade}s", "artist": f"Artist {decade}",
                                               "last_week": None, "peak_position": 1, "weeks_on_chart": 1}])
            result = get_best_songs_all_decades(conn)
            assert set(result.keys()) == {1960, 1970, 1980}
            for decade in [1960, 1970, 1980]:
                assert len(result[decade]) == 1
                assert result[decade][0].decade == decade
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test best song score dataclass
# verifies dataclass fields are accessible
def test_best_song_score_dataclass() -> None:
    score = BestSongScore(
        song="Test Song",
        artist="Test Artist",
        decade=1980,
        total_score=5000000,
        weeks_on_chart=30,
        peak_position=1,
    )
    assert score.song == "Test Song"
    assert score.artist == "Test Artist"
    assert score.decade == 1980
    assert score.total_score == 5000000
    assert score.weeks_on_chart == 30
    assert score.peak_position == 1
