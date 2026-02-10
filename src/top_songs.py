import sqlite3
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SongScore:
    song: str
    artist: str
    year: int
    weeks_at_one: int
    weeks_in_top_ten: int
    peak_position: int
    total_weeks: int
    score: float


# ##################################################################
# calculate song score
# computes ranking score based on chart performance metrics
def calculate_song_score(
    weeks_at_one: int,
    weeks_in_top_ten: int,
    peak_position: int,
    total_weeks: int,
) -> float:
    position_bonus = max(0, 11 - peak_position) * 10
    return weeks_at_one * 100 + weeks_in_top_ten * 20 + position_bonus + total_weeks * 2


# ##################################################################
# get top songs for year
# queries database and returns top n songs for a specific year
def get_top_songs_for_year(
    connection: sqlite3.Connection,
    year: int,
    limit: int = 10,
) -> list[SongScore]:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT
            e.song,
            e.artist,
            COUNT(CASE WHEN e.position = 1 THEN 1 END) as weeks_at_one,
            COUNT(CASE WHEN e.position <= 10 THEN 1 END) as weeks_in_top_ten,
            MIN(e.position) as peak_position,
            COUNT(*) as total_weeks
        FROM entry e
        JOIN chart_week cw ON e.chart_week_id = cw.id
        WHERE strftime('%Y', cw.chart_date) = ?
        GROUP BY e.song, e.artist
        ORDER BY
            weeks_at_one DESC,
            weeks_in_top_ten DESC,
            peak_position ASC,
            total_weeks DESC
        """,
        (str(year),),
    )
    results = []
    for row in cursor.fetchall():
        score = calculate_song_score(
            row["weeks_at_one"],
            row["weeks_in_top_ten"],
            row["peak_position"],
            row["total_weeks"],
        )
        results.append(
            SongScore(
                song=row["song"],
                artist=row["artist"],
                year=year,
                weeks_at_one=row["weeks_at_one"],
                weeks_in_top_ten=row["weeks_in_top_ten"],
                peak_position=row["peak_position"],
                total_weeks=row["total_weeks"],
                score=score,
            )
        )
    results.sort(key=lambda x: -x.score)
    return results[:limit]


# ##################################################################
# get available years
# returns list of years that have chart data in database
def get_available_years(connection: sqlite3.Connection) -> list[int]:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT DISTINCT strftime('%Y', chart_date) as year
        FROM chart_week
        ORDER BY year
        """
    )
    return [int(row["year"]) for row in cursor.fetchall()]


# ##################################################################
# get decade years
# returns list of years in a decade that have data
def get_decade_years(connection: sqlite3.Connection, decade_start: int) -> list[int]:
    available = get_available_years(connection)
    return [y for y in available if decade_start <= y < decade_start + 10]


# ##################################################################
# get top songs for decade
# returns top 10 songs for each year in a decade, ordered for playlist
def get_top_songs_for_decade(
    connection: sqlite3.Connection,
    decade_start: int,
) -> list[SongScore]:
    years = get_decade_years(connection, decade_start)
    if not years:
        return []
    all_songs = []
    for year in sorted(years):
        year_songs = get_top_songs_for_year(connection, year, limit=10)
        year_songs_reversed = list(reversed(year_songs))
        all_songs.extend(year_songs_reversed)
        logger.debug("Year %d: found %d top songs", year, len(year_songs))
    return all_songs


# ##################################################################
# get all decades with data
# returns list of decade start years that have chart data
def get_all_decades_with_data(connection: sqlite3.Connection) -> list[int]:
    years = get_available_years(connection)
    decades = set((y // 10) * 10 for y in years)
    return sorted(decades)
