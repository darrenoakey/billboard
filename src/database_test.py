import tempfile
from pathlib import Path

from src.database import DatabaseConnection, ChartRepository


# ##################################################################
# test database connection creates schema
# verifies that connecting to a new database creates all required tables
def test_database_connection_creates_schema() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row["name"] for row in cursor.fetchall()]
            assert "chart" in tables
            assert "chart_week" in tables
            assert "entry" in tables
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test get or create chart creates new
# verifies that a new chart is created when it does not exist
def test_get_or_create_chart_creates_new() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("test-chart", "Test Chart", "test")
            assert chart_id == 1
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chart WHERE id = ?", (chart_id,))
            row = cursor.fetchone()
            assert row["name"] == "test-chart"
            assert row["display_name"] == "Test Chart"
            assert row["source"] == "test"
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test get or create chart returns existing
# verifies that an existing chart id is returned when chart already exists
def test_get_or_create_chart_returns_existing() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id1 = repo.get_or_create_chart("test-chart", "Test Chart", "test")
            chart_id2 = repo.get_or_create_chart("test-chart", "Test Chart", "test")
            assert chart_id1 == chart_id2
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test chart week exists returns false for missing
# verifies chart_week_exists returns false when date not in database
def test_chart_week_exists_returns_false_for_missing() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("test-chart", "Test Chart", "test")
            assert not repo.chart_week_exists(chart_id, "2024-01-01")
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test insert chart week and check exists
# verifies inserting a chart week makes it findable via chart_week_exists
def test_insert_chart_week_and_check_exists() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("test-chart", "Test Chart", "test")
            week_id = repo.insert_chart_week(chart_id, "2024-01-01")
            assert week_id > 0
            assert repo.chart_week_exists(chart_id, "2024-01-01")
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test insert entries
# verifies entries are correctly stored and retrievable
def test_insert_entries() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("test-chart", "Test Chart", "test")
            week_id = repo.insert_chart_week(chart_id, "2024-01-01")
            entries = [
                {
                    "position": 1,
                    "song": "Test Song 1",
                    "artist": "Test Artist 1",
                    "last_week": None,
                    "peak_position": 1,
                    "weeks_on_chart": 1,
                },
                {
                    "position": 2,
                    "song": "Test Song 2",
                    "artist": "Test Artist 2",
                    "last_week": 1,
                    "peak_position": 1,
                    "weeks_on_chart": 5,
                },
            ]
            repo.insert_entries(week_id, entries)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM entry WHERE chart_week_id = ? ORDER BY position",
                (week_id,),
            )
            rows = cursor.fetchall()
            assert len(rows) == 2
            assert rows[0]["song"] == "Test Song 1"
            assert rows[0]["artist"] == "Test Artist 1"
            assert rows[1]["song"] == "Test Song 2"
            assert rows[1]["last_week"] == 1
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test get downloaded dates
# verifies get_downloaded_dates returns correct set of dates
def test_get_downloaded_dates() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("test-chart", "Test Chart", "test")
            repo.insert_chart_week(chart_id, "2024-01-01")
            repo.insert_chart_week(chart_id, "2024-01-08")
            repo.insert_chart_week(chart_id, "2024-01-15")
            dates = repo.get_downloaded_dates(chart_id)
            assert dates == {"2024-01-01", "2024-01-08", "2024-01-15"}
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test get statistics
# verifies statistics returns correct counts
def test_get_statistics() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            repo = ChartRepository(conn)
            chart_id = repo.get_or_create_chart("test-chart", "Test Chart", "test")
            week_id = repo.insert_chart_week(chart_id, "2024-01-01")
            entries = [
                {
                    "position": i,
                    "song": f"Song {i}",
                    "artist": f"Artist {i}",
                    "last_week": None,
                    "peak_position": i,
                    "weeks_on_chart": 1,
                }
                for i in range(1, 11)
            ]
            repo.insert_entries(week_id, entries)
            stats = repo.get_statistics()
            assert stats["charts"] == 1
            assert stats["chart_weeks"] == 1
            assert stats["entries"] == 10
            assert len(stats["by_chart"]) == 1
            assert stats["by_chart"][0]["name"] == "test-chart"
            assert stats["by_chart"][0]["weeks"] == 1
    finally:
        db_path.unlink(missing_ok=True)
