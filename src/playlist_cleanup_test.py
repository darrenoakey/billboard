import io
import sys

from src.playlist_cleanup import (
    PlaylistInfo,
    find_duplicates,
    find_decade_playlists_below_track_count,
    is_decade_top_hits_playlist,
    parse_decade_playlist_name,
    print_cleanup_report,
    print_decade_cleanup_report,
    get_all_playlists,
    cleanup_duplicate_playlists,
)


# ##################################################################
# test playlist info dataclass
# verifies dataclass fields are correct
def test_playlist_info_dataclass() -> None:
    info = PlaylistInfo(name="Test", index=1, track_count=10, playlist_id="p.test")
    assert info.name == "Test"
    assert info.index == 1
    assert info.track_count == 10
    assert info.playlist_id == "p.test"


# ##################################################################
# test parse decade playlist name valid
# verifies decade parsing for matching playlist names
def test_parse_decade_playlist_name_valid() -> None:
    assert parse_decade_playlist_name("1960s Top Hits") == 1960
    assert parse_decade_playlist_name("1980s top hits") == 1980
    assert parse_decade_playlist_name(" 2000s Top Hits ") == 2000


# ##################################################################
# test parse decade playlist name invalid
# verifies non-decade names return none
def test_parse_decade_playlist_name_invalid() -> None:
    assert parse_decade_playlist_name("1995s Top Hits") is None
    assert parse_decade_playlist_name("Top Hits 1990s") is None
    assert parse_decade_playlist_name("1990s Top Hits Extra") is None
    assert parse_decade_playlist_name("1990s Top Hit") is None


# ##################################################################
# test is decade top hits playlist
# verifies decade pattern detection
def test_is_decade_top_hits_playlist() -> None:
    assert is_decade_top_hits_playlist("1970s Top Hits") is True
    assert is_decade_top_hits_playlist("1970s top hits") is True
    assert is_decade_top_hits_playlist("1975s Top Hits") is False


# ##################################################################
# test find duplicates with no duplicates
# verifies empty result when all names unique
def test_find_duplicates_no_duplicates() -> None:
    playlists = [
        PlaylistInfo(name="A", index=1, track_count=10, playlist_id="p.a1"),
        PlaylistInfo(name="B", index=2, track_count=20, playlist_id="p.b1"),
        PlaylistInfo(name="C", index=3, track_count=30, playlist_id="p.c1"),
    ]
    result = find_duplicates(playlists)
    assert result == {}


# ##################################################################
# test find duplicates with duplicates
# verifies duplicates are grouped correctly
def test_find_duplicates_with_duplicates() -> None:
    playlists = [
        PlaylistInfo(name="A", index=1, track_count=10, playlist_id="p.a1"),
        PlaylistInfo(name="A", index=2, track_count=20, playlist_id="p.a2"),
        PlaylistInfo(name="B", index=3, track_count=30, playlist_id="p.b1"),
        PlaylistInfo(name="A", index=4, track_count=5, playlist_id="p.a3"),
    ]
    result = find_duplicates(playlists)
    assert "A" in result
    assert "B" not in result
    assert len(result["A"]) == 3


# ##################################################################
# test find duplicates empty list
# verifies empty input returns empty result
def test_find_duplicates_empty() -> None:
    result = find_duplicates([])
    assert result == {}


# ##################################################################
# test find duplicates all duplicates
# verifies all items with same name grouped together
def test_find_duplicates_all_same_name() -> None:
    playlists = [
        PlaylistInfo(name="Same", index=1, track_count=10, playlist_id="p.s1"),
        PlaylistInfo(name="Same", index=2, track_count=20, playlist_id="p.s2"),
    ]
    result = find_duplicates(playlists)
    assert "Same" in result
    assert len(result["Same"]) == 2


# ##################################################################
# test playlist info equality
# verifies dataclass equality works correctly
def test_playlist_info_equality() -> None:
    a = PlaylistInfo(name="Test", index=1, track_count=10, playlist_id="p.same")
    b = PlaylistInfo(name="Test", index=1, track_count=10, playlist_id="p.same")
    assert a == b


# ##################################################################
# test playlist info different values
# verifies dataclass inequality for different values
def test_playlist_info_inequality() -> None:
    a = PlaylistInfo(name="Test", index=1, track_count=10, playlist_id="p.a")
    b = PlaylistInfo(name="Test", index=1, track_count=20, playlist_id="p.b")
    assert a != b


# ##################################################################
# test print cleanup report no duplicates
# verifies report output when no duplicates found
def test_print_cleanup_report_no_duplicates() -> None:
    results = {
        "duplicates_found": 0,
        "playlists_deleted": 0,
        "playlists_kept": 0,
        "details": [],
    }
    captured = io.StringIO()
    sys.stdout = captured
    try:
        print_cleanup_report(results, dry_run=True)
    finally:
        sys.stdout = sys.__stdout__
    output = captured.getvalue()
    assert "No duplicate playlists found" in output


# ##################################################################
# test print cleanup report with duplicates
# verifies report output shows duplicate details
def test_print_cleanup_report_with_duplicates() -> None:
    results = {
        "duplicates_found": 2,
        "playlists_deleted": 3,
        "playlists_kept": 2,
        "details": [
            {
                "name": "Test Playlist",
                "kept_track_count": 50,
                "kept_playlist_id": "p.keep",
                "deleted_count": 2,
                "deleted_track_counts": [10, 0],
                "deleted_playlist_ids": ["p.d1", "p.d2"],
            },
        ],
    }
    captured = io.StringIO()
    sys.stdout = captured
    try:
        print_cleanup_report(results, dry_run=True)
    finally:
        sys.stdout = sys.__stdout__
    output = captured.getvalue()
    assert "DRY RUN" in output
    assert "Test Playlist" in output
    assert "Keeping: 50 tracks" in output


# ##################################################################
# test print cleanup report execute mode
# verifies report output does not show dry run in execute mode
def test_print_cleanup_report_execute_mode() -> None:
    results = {
        "duplicates_found": 1,
        "playlists_deleted": 1,
        "playlists_kept": 1,
        "details": [
            {
                "name": "Test",
                "kept_track_count": 10,
                "kept_playlist_id": "p.keep",
                "deleted_count": 1,
                "deleted_track_counts": [0],
                "deleted_playlist_ids": ["p.d1"],
            },
        ],
    }
    captured = io.StringIO()
    sys.stdout = captured
    try:
        print_cleanup_report(results, dry_run=False)
    finally:
        sys.stdout = sys.__stdout__
    output = captured.getvalue()
    assert "DRY RUN" not in output


# ##################################################################
# test print decade cleanup report empty
# verifies report output when no decade playlists found
def test_print_decade_cleanup_report_empty() -> None:
    results = {
        "min_tracks": 50,
        "playlists_found": 0,
        "playlists_deleted": 0,
        "playlists_failed": 0,
        "details": [],
    }
    captured = io.StringIO()
    sys.stdout = captured
    try:
        print_decade_cleanup_report(results, dry_run=True)
    finally:
        sys.stdout = sys.__stdout__
    output = captured.getvalue()
    assert "No decade playlists below the minimum track count were found" in output


# ##################################################################
# test print decade cleanup report with results
# verifies report output shows details
def test_print_decade_cleanup_report_with_results() -> None:
    results = {
        "min_tracks": 50,
        "playlists_found": 2,
        "playlists_deleted": 1,
        "playlists_failed": 1,
        "details": [
            {"name": "1960s Top Hits", "track_count": 40, "action": "DELETED"},
            {"name": "1970s Top Hits", "track_count": 30, "action": "FAILED"},
        ],
    }
    captured = io.StringIO()
    sys.stdout = captured
    try:
        print_decade_cleanup_report(results, dry_run=False)
    finally:
        sys.stdout = sys.__stdout__
    output = captured.getvalue()
    assert "1960s Top Hits" in output
    assert "DELETED" in output
    assert "FAILED" in output


# ##################################################################
# test find decade playlists below track count
# verifies filtering for decade playlists under threshold
def test_find_decade_playlists_below_track_count() -> None:
    playlists = [
        PlaylistInfo(name="1960s Top Hits", index=1, track_count=49, playlist_id="p.1960"),
        PlaylistInfo(name="1970s Top Hits", index=2, track_count=50, playlist_id="p.1970"),
        PlaylistInfo(name="1980s Top Hits", index=3, track_count=10, playlist_id="p.1980"),
        PlaylistInfo(name="Not A Match", index=4, track_count=0, playlist_id="p.na"),
        PlaylistInfo(name="1995s Top Hits", index=5, track_count=1, playlist_id="p.1995"),
    ]
    result = find_decade_playlists_below_track_count(playlists, min_tracks=50)
    names = {p.name for p in result}
    assert names == {"1960s Top Hits", "1980s Top Hits"}


# ##################################################################
# test cleanup duplicate playlists picks one with most tracks
# verifies only one playlist kept when duplicates share top count
def test_cleanup_duplicate_playlists_tie_break(monkeypatch) -> None:
    playlists = [
        PlaylistInfo(name="Tie", index=1, track_count=20, playlist_id="p.keep"),
        PlaylistInfo(name="Tie", index=2, track_count=20, playlist_id="p.del1"),
        PlaylistInfo(name="Tie", index=3, track_count=10, playlist_id="p.del2"),
    ]

    monkeypatch.setattr("src.playlist_cleanup.get_all_playlists", lambda: playlists)
    deleted = []

    def fake_delete(playlist_id: str) -> bool:
        deleted.append(playlist_id)
        return True

    monkeypatch.setattr("src.playlist_cleanup.delete_playlist_by_id", fake_delete)

    results = cleanup_duplicate_playlists(dry_run=False)
    assert results["playlists_kept"] == 1
    assert results["playlists_deleted"] == 2
    assert "p.keep" not in deleted
    assert set(deleted) == {"p.del1", "p.del2"}


# ##################################################################
# test get all playlists returns list
# verifies function returns list of playlist info from music app
def test_get_all_playlists_returns_list() -> None:
    playlists = get_all_playlists()
    assert isinstance(playlists, list)
    if playlists:
        assert isinstance(playlists[0], PlaylistInfo)
        assert isinstance(playlists[0].name, str)
        assert isinstance(playlists[0].index, int)
        assert isinstance(playlists[0].track_count, int)


# ##################################################################
# test cleanup duplicate playlists dry run
# verifies dry run mode does not delete anything
def test_cleanup_duplicate_playlists_dry_run() -> None:
    results = cleanup_duplicate_playlists(dry_run=True)
    assert "duplicates_found" in results
    assert "playlists_deleted" in results
    assert "playlists_kept" in results
    assert "details" in results
    assert isinstance(results["details"], list)
