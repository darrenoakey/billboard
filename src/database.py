import sqlite3
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_PATH = Path(__file__).parent.parent / "billboard.db"


# ##################################################################
# database connection
# provides connection management and schema initialization for the billboard database
class DatabaseConnection:
    def __init__(self, path: Path = DEFAULT_DATABASE_PATH) -> None:
        self.path = path
        self.connection: Optional[sqlite3.Connection] = None

    # ##################################################################
    # connect
    # opens the database connection and ensures schema exists
    def connect(self) -> sqlite3.Connection:
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row
        self._ensure_schema()
        return self.connection

    # ##################################################################
    # close
    # closes the database connection if open
    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None

    # ##################################################################
    # ensure schema
    # creates all tables if they do not exist
    def _ensure_schema(self) -> None:
        assert self.connection is not None
        cursor = self.connection.cursor()
        cursor.executescript(SCHEMA_SQL)
        self.connection.commit()

    # ##################################################################
    # enter
    # context manager entry
    def __enter__(self) -> sqlite3.Connection:
        return self.connect()

    # ##################################################################
    # exit
    # context manager exit
    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        self.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chart (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chart_week (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chart_id INTEGER NOT NULL,
    chart_date TEXT NOT NULL,
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chart_id) REFERENCES chart(id),
    UNIQUE(chart_id, chart_date)
);

CREATE TABLE IF NOT EXISTS entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chart_week_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    song TEXT NOT NULL,
    artist TEXT NOT NULL,
    last_week INTEGER,
    peak_position INTEGER,
    weeks_on_chart INTEGER,
    FOREIGN KEY (chart_week_id) REFERENCES chart_week(id)
);

CREATE INDEX IF NOT EXISTS idx_chart_week_date ON chart_week(chart_date);
CREATE INDEX IF NOT EXISTS idx_entry_song ON entry(song);
CREATE INDEX IF NOT EXISTS idx_entry_artist ON entry(artist);
"""


# ##################################################################
# chart repository
# data access methods for chart operations
class ChartRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    # ##################################################################
    # get or create chart
    # retrieves existing chart by name or creates it if not found
    def get_or_create_chart(self, name: str, display_name: str, source: str) -> int:
        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM chart WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            return row["id"]
        cursor.execute(
            "INSERT INTO chart (name, display_name, source) VALUES (?, ?, ?)",
            (name, display_name, source),
        )
        self.connection.commit()
        result = cursor.lastrowid
        assert result is not None
        return result

    # ##################################################################
    # chart week exists
    # checks if a chart week has already been downloaded
    def chart_week_exists(self, chart_id: int, chart_date: str) -> bool:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT 1 FROM chart_week WHERE chart_id = ? AND chart_date = ?",
            (chart_id, chart_date),
        )
        return cursor.fetchone() is not None

    # ##################################################################
    # insert chart week
    # creates a new chart week record and returns its id
    def insert_chart_week(self, chart_id: int, chart_date: str) -> int:
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT INTO chart_week (chart_id, chart_date) VALUES (?, ?)",
            (chart_id, chart_date),
        )
        self.connection.commit()
        result = cursor.lastrowid
        assert result is not None
        return result

    # ##################################################################
    # insert entries
    # bulk inserts chart entries for a given chart week
    def insert_entries(self, chart_week_id: int, entries: list[dict]) -> None:
        cursor = self.connection.cursor()
        cursor.executemany(
            """INSERT INTO entry
               (chart_week_id, position, song, artist, last_week, peak_position, weeks_on_chart)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    chart_week_id,
                    e["position"],
                    e["song"],
                    e["artist"],
                    e.get("last_week"),
                    e.get("peak_position"),
                    e.get("weeks_on_chart"),
                )
                for e in entries
            ],
        )
        self.connection.commit()

    # ##################################################################
    # get downloaded dates
    # returns set of all dates already downloaded for a chart
    def get_downloaded_dates(self, chart_id: int) -> set[str]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT chart_date FROM chart_week WHERE chart_id = ?", (chart_id,))
        return {row["chart_date"] for row in cursor.fetchall()}

    # ##################################################################
    # get statistics
    # returns counts of charts, weeks, and entries in database
    def get_statistics(self) -> dict:
        cursor = self.connection.cursor()
        stats = {}
        cursor.execute("SELECT COUNT(*) as count FROM chart")
        stats["charts"] = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM chart_week")
        stats["chart_weeks"] = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM entry")
        stats["entries"] = cursor.fetchone()["count"]
        cursor.execute(
            """SELECT c.name, c.display_name, COUNT(cw.id) as weeks
               FROM chart c
               LEFT JOIN chart_week cw ON c.id = cw.chart_id
               GROUP BY c.id"""
        )
        stats["by_chart"] = [dict(row) for row in cursor.fetchall()]
        return stats
