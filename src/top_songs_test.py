import tempfile
from pathlib import Path

from src.database import DatabaseConnection, ChartRepository
from src.top_songs import (
    calculate_song_score,
    get_top_songs_for_year,
    get_available_years,
    get_decade_years,
    get_top_songs_for_decade,
    get_all_decades_with_data,
)


# ##################################################################
# helper to seed test data
# inserts chart weeks and entries for testing
def seed_test_data(conn, chart_id: int, year: int, songs: list[dict]) -> None:
    repo = ChartRepository(conn)
    for week_num, song_data in enumerate(songs):
        date = f"{year}-{(week_num % 12) + 1:02d}-{(week_num % 28) + 1:02d}"
        week_id = repo.insert_chart_week(chart_id, date)
        entries = [
            {
                "position": song_data.get("position", 1),
                "song": song_data["song"],
                "artist": song_data["artist"],
                "last_week": None,
                "peak_position": song_data.get("position", 1),
                "weeks_on_chart": 1,
            }
        ]
        repo.insert_entries(week_id, entries)


# ##################################################################
# test calculate song score basic
# verifies scoring formula gives expected results
def test_calculate_song_score_basic() -> None:
    score = calculate_song_score(
        weeks_at_one=10,
        weeks_in_top_ten=20,
        peak_position=1,
        total_weeks=30,
    )
    expected = 10 * 100 + 20 * 20 + 100 + 30 * 2
    assert score == expected


# ##################################################################
# test calculate song score no number one
# verifies songs without number one weeks score correctly
def test_calculate_song_score_no_number_one() -> None:
    score = calculate_song_score(
        weeks_at_one=0,
        weeks_in_top_ten=15,
        peak_position=2,
        total_weeks=20,
    )
    expected = 0 + 15 * 20 + 90 + 20 * 2
    assert score == expected


# ##################################################################
# test get available years
# verifies available years extraction from database
def test_get_available_years() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            repo.insert_chart_week(chart_id, "1960-01-01")
            repo.insert_chart_week(chart_id, "1965-06-15")
            repo.insert_chart_week(chart_id, "1970-12-31")
            years = get_available_years(conn)
            assert years == [1960, 1965, 1970]
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test get decade years
# verifies filtering of years by decade
def test_get_decade_years() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            repo.insert_chart_week(chart_id, "1958-08-01")
            repo.insert_chart_week(chart_id, "1962-06-15")
            repo.insert_chart_week(chart_id, "1965-12-31")
            repo.insert_chart_week(chart_id, "1970-01-01")
            sixties = get_decade_years(conn, 1960)
            assert sixties == [1962, 1965]
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test get all decades with data
# verifies decade extraction from available years
def test_get_all_decades_with_data() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            repo.insert_chart_week(chart_id, "1958-08-01")
            repo.insert_chart_week(chart_id, "1965-06-15")
            repo.insert_chart_week(chart_id, "1975-12-31")
            repo.insert_chart_week(chart_id, "1985-01-01")
            decades = get_all_decades_with_data(conn)
            assert decades == [1950, 1960, 1970, 1980]
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test get top songs for year
# verifies top songs ranking for a single year
def test_get_top_songs_for_year() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            for week in range(10):
                week_id = repo.insert_chart_week(chart_id, f"1965-{week + 1:02d}-15")
                entries = [
                    {
                        "position": 1,
                        "song": "Hit Song",
                        "artist": "Big Artist",
                        "last_week": None,
                        "peak_position": 1,
                        "weeks_on_chart": week + 1,
                    },
                    {
                        "position": 5,
                        "song": "Other Song",
                        "artist": "Other Artist",
                        "last_week": 6,
                        "peak_position": 5,
                        "weeks_on_chart": week + 1,
                    },
                ]
                repo.insert_entries(week_id, entries)
            top = get_top_songs_for_year(conn, 1965, limit=10)
            assert len(top) == 2
            assert top[0].song == "Hit Song"
            assert top[0].weeks_at_one == 10
            assert top[1].song == "Other Song"
            assert top[1].weeks_at_one == 0
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test get top songs for decade
# verifies decade aggregation returns songs in correct order
def test_get_top_songs_for_decade() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("hot-100", "Hot 100", "test")
            for year in [1960, 1961]:
                week_id = repo.insert_chart_week(chart_id, f"{year}-06-15")
                entries = [
                    {
                        "position": 1,
                        "song": f"Top Hit {year}",
                        "artist": f"Artist {year}",
                        "last_week": None,
                        "peak_position": 1,
                        "weeks_on_chart": 1,
                    },
                ]
                repo.insert_entries(week_id, entries)
            decade_songs = get_top_songs_for_decade(conn, 1960)
            assert len(decade_songs) == 2
            assert decade_songs[0].year == 1960
            assert decade_songs[1].year == 1961
    finally:
        db_path.unlink(missing_ok=True)
