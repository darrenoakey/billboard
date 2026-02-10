import requests
import sqlite3
import logging
from typing import Optional

from src.database import ChartRepository

logger = logging.getLogger(__name__)

BASE_URL = "https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main"
VALID_DATES_URL = f"{BASE_URL}/valid_dates.json"
CHART_DATE_URL_TEMPLATE = f"{BASE_URL}/date/{{date}}.json"

CHART_NAME = "hot-100"
CHART_DISPLAY_NAME = "Billboard Hot 100"
CHART_SOURCE = "mhollingshead/billboard-hot-100"


# ##################################################################
# fetch valid dates
# retrieves the list of all available chart dates from the repository
def fetch_valid_dates() -> list[str]:
    response = requests.get(VALID_DATES_URL, timeout=30)
    response.raise_for_status()
    return response.json()


# ##################################################################
# fetch chart data
# downloads chart data for a specific date from the repository
def fetch_chart_data(date: str) -> dict:
    url = CHART_DATE_URL_TEMPLATE.format(date=date)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


# ##################################################################
# transform entry
# converts raw json entry to database entry format
def transform_entry(raw_entry: dict) -> dict:
    return {
        "position": raw_entry["this_week"],
        "song": raw_entry["song"],
        "artist": raw_entry["artist"],
        "last_week": raw_entry.get("last_week"),
        "peak_position": raw_entry.get("peak_position"),
        "weeks_on_chart": raw_entry.get("weeks_on_chart"),
    }


# ##################################################################
# hot 100 downloader
# orchestrates downloading hot 100 charts with idempotency
class Hot100Downloader:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.repository = ChartRepository(connection)
        self.chart_id: Optional[int] = None

    # ##################################################################
    # initialize chart
    # ensures the hot 100 chart exists in database
    def initialize_chart(self) -> int:
        self.chart_id = self.repository.get_or_create_chart(CHART_NAME, CHART_DISPLAY_NAME, CHART_SOURCE)
        return self.chart_id

    # ##################################################################
    # get pending dates
    # returns dates that have not yet been downloaded
    def get_pending_dates(self) -> list[str]:
        if self.chart_id is None:
            self.initialize_chart()
        assert self.chart_id is not None
        all_dates = fetch_valid_dates()
        downloaded = self.repository.get_downloaded_dates(self.chart_id)
        pending = [d for d in all_dates if d not in downloaded]
        logger.info(
            "Hot 100: %d total dates, %d downloaded, %d pending",
            len(all_dates),
            len(downloaded),
            len(pending),
        )
        return pending

    # ##################################################################
    # download date
    # fetches and stores a single chart date
    def download_date(self, date: str) -> bool:
        if self.chart_id is None:
            self.initialize_chart()
        assert self.chart_id is not None
        if self.repository.chart_week_exists(self.chart_id, date):
            logger.debug("Already downloaded date: %s", date)
            return False
        try:
            data = fetch_chart_data(date)
            entries = [transform_entry(e) for e in data["data"]]
            chart_week_id = self.repository.insert_chart_week(self.chart_id, date)
            self.repository.insert_entries(chart_week_id, entries)
            logger.info("Downloaded Hot 100 for %s (%d entries)", date, len(entries))
            return True
        except Exception as err:
            logger.error("Failed to download Hot 100 for %s: %s", date, err)
            raise

    # ##################################################################
    # download all
    # downloads all pending chart dates with progress reporting
    def download_all(self, limit: Optional[int] = None) -> dict:
        pending = self.get_pending_dates()
        if limit:
            pending = pending[:limit]
        downloaded = 0
        existing = 0
        failed = 0
        for i, date in enumerate(pending):
            try:
                if self.download_date(date):
                    downloaded += 1
                else:
                    existing += 1
                if (i + 1) % 100 == 0:
                    logger.info("Progress: %d/%d dates processed", i + 1, len(pending))
            except Exception as err:
                logger.error("download_all failed date=%s err=%s", date, err)
                failed += 1
                continue
        return {"downloaded": downloaded, "existing": existing, "failed": failed}
