import tempfile
from pathlib import Path

from src.database import DatabaseConnection, ChartRepository
from src.hot100_downloader import (
    Hot100Downloader,
    fetch_valid_dates,
    fetch_chart_data,
    transform_entry,
    CHART_NAME,
)


# ##################################################################
# test fetch valid dates returns list
# verifies the mhollingshead api returns a list of valid chart dates
def test_fetch_valid_dates_returns_list() -> None:
    dates = fetch_valid_dates()
    assert isinstance(dates, list)
    assert len(dates) > 3000  # should have 3500+ dates
    assert dates[0] == "1958-08-04"  # first Hot 100 chart date
    assert all(isinstance(d, str) for d in dates)


# ##################################################################
# test fetch chart data returns valid structure
# verifies chart data for a specific date has expected fields
def test_fetch_chart_data_returns_valid_structure() -> None:
    data = fetch_chart_data("2024-01-06")
    assert "date" in data
    assert "data" in data
    assert data["date"] == "2024-01-06"
    assert len(data["data"]) == 100
    first_entry = data["data"][0]
    assert "song" in first_entry
    assert "artist" in first_entry
    assert "this_week" in first_entry


# ##################################################################
# test transform entry maps fields correctly
# verifies raw json entry is transformed to database format
def test_transform_entry_maps_fields_correctly() -> None:
    raw = {
        "song": "Test Song",
        "artist": "Test Artist",
        "this_week": 5,
        "last_week": 3,
        "peak_position": 1,
        "weeks_on_chart": 10,
    }
    result = transform_entry(raw)
    assert result["position"] == 5
    assert result["song"] == "Test Song"
    assert result["artist"] == "Test Artist"
    assert result["last_week"] == 3
    assert result["peak_position"] == 1
    assert result["weeks_on_chart"] == 10


# ##################################################################
# test transform entry handles null last week
# verifies null last_week for new entries is handled
def test_transform_entry_handles_null_last_week() -> None:
    raw = {
        "song": "New Song",
        "artist": "New Artist",
        "this_week": 1,
        "last_week": None,
        "peak_position": 1,
        "weeks_on_chart": 1,
    }
    result = transform_entry(raw)
    assert result["last_week"] is None


# ##################################################################
# test hot100 downloader initializes chart
# verifies downloader creates chart record in database
def test_hot100_downloader_initializes_chart() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            downloader = Hot100Downloader(conn)
            chart_id = downloader.initialize_chart()
            assert chart_id > 0
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chart WHERE name = ?", (CHART_NAME,))
            row = cursor.fetchone()
            assert row is not None
            assert row["display_name"] == "Billboard Hot 100"
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test hot100 downloader downloads single date
# verifies downloader can download and store a single chart date
def test_hot100_downloader_downloads_single_date() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            downloader = Hot100Downloader(conn)
            downloader.initialize_chart()
            result = downloader.download_date("2024-01-06")
            assert result is True
            repo = ChartRepository(conn)
            assert repo.chart_week_exists(downloader.chart_id, "2024-01-06")
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(*) as count FROM entry e
                   JOIN chart_week cw ON e.chart_week_id = cw.id
                   WHERE cw.chart_date = ?""",
                ("2024-01-06",),
            )
            count = cursor.fetchone()["count"]
            assert count == 100
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test hot100 downloader idempotent
# verifies downloading same date twice does not duplicate
def test_hot100_downloader_idempotent() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            downloader = Hot100Downloader(conn)
            downloader.initialize_chart()
            result1 = downloader.download_date("2024-01-06")
            assert result1 is True
            result2 = downloader.download_date("2024-01-06")
            assert result2 is False
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM chart_week WHERE chart_date = ?",
                ("2024-01-06",),
            )
            count = cursor.fetchone()["count"]
            assert count == 1
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test hot100 downloader get pending dates
# verifies pending dates excludes already downloaded dates
def test_hot100_downloader_get_pending_dates() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            downloader = Hot100Downloader(conn)
            downloader.initialize_chart()
            all_dates = fetch_valid_dates()
            downloader.download_date(all_dates[0])
            downloader.download_date(all_dates[1])
            pending = downloader.get_pending_dates()
            assert all_dates[0] not in pending
            assert all_dates[1] not in pending
            assert len(pending) == len(all_dates) - 2
    finally:
        db_path.unlink(missing_ok=True)


# ##################################################################
# test hot100 downloader download all with limit
# verifies download_all respects limit parameter
def test_hot100_downloader_download_all_with_limit() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        with DatabaseConnection(db_path) as conn:
            downloader = Hot100Downloader(conn)
            result = downloader.download_all(limit=3)
            assert result["downloaded"] == 3
            assert result["existing"] == 0
            assert result["failed"] == 0
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM chart_week")
            count = cursor.fetchone()["count"]
            assert count == 3
    finally:
        db_path.unlink(missing_ok=True)
