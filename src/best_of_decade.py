import sqlite3
import logging
from dataclasses import dataclass

from src.top_songs import get_all_decades_with_data

logger = logging.getLogger(__name__)


@dataclass
class BestSongScore:
    song: str
    artist: str
    decade: int
    total_score: float
    weeks_on_chart: int
    peak_position: int


# ##################################################################
# get best songs for decade
# queries database using cubic position scoring to find top songs for a decade
def get_best_songs_for_decade(
    connection: sqlite3.Connection,
    decade_start: int,
    limit: int = 10,
) -> list[BestSongScore]:
    decade_end = decade_start + 10
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT
            e.song,
            e.artist,
            SUM((100 - e.position) * (100 - e.position) * (100 - e.position)) as total_score,
            COUNT(*) as weeks_on_chart,
            MIN(e.position) as peak_position
        FROM entry e
        JOIN chart_week cw ON e.chart_week_id = cw.id
        WHERE cw.chart_date >= ? AND cw.chart_date < ?
        GROUP BY e.song, e.artist
        ORDER BY total_score DESC
        LIMIT ?
        """,
        (f"{decade_start}-01-01", f"{decade_end}-01-01", limit),
    )
    results = []
    for row in cursor.fetchall():
        results.append(
            BestSongScore(
                song=row["song"],
                artist=row["artist"],
                decade=decade_start,
                total_score=row["total_score"],
                weeks_on_chart=row["weeks_on_chart"],
                peak_position=row["peak_position"],
            )
        )
    return results


# ##################################################################
# get best songs all decades
# returns dict mapping decade start year to list of top 10 songs
def get_best_songs_all_decades(
    connection: sqlite3.Connection,
    limit: int = 10,
) -> dict[int, list[BestSongScore]]:
    decades = get_all_decades_with_data(connection)
    result = {}
    for decade in decades:
        songs = get_best_songs_for_decade(connection, decade, limit=limit)
        if songs:
            result[decade] = songs
            logger.info("Decade %ds: found %d best songs", decade, len(songs))
    return result
