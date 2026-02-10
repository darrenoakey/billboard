from src.playlist_generator import (
    create_decade_playlist,
    decade_playlist_name,
    PlaylistGenerationResult,
    print_generation_summary,
)
from io import StringIO
import sys


# ##################################################################
# test decade playlist name format
# verifies playlist name generation for various decades
def test_decade_playlist_name_format() -> None:
    assert decade_playlist_name(1950) == "1950s Top Hits"
    assert decade_playlist_name(1960) == "1960s Top Hits"
    assert decade_playlist_name(2020) == "2020s Top Hits"


# ##################################################################
# test print generation summary created
# verifies summary output for created playlists
def test_print_generation_summary_created() -> None:
    results = [
        PlaylistGenerationResult(
            decade=1960,
            playlist_name="1960s Top Hits",
            created=True,
            already_existed=False,
            songs_added=80,
            songs_not_found=20,
            total_songs=100,
        ),
    ]
    captured = StringIO()
    sys.stdout = captured
    try:
        print_generation_summary(results)
    finally:
        sys.stdout = sys.__stdout__
    output = captured.getvalue()
    assert "1960s Top Hits" in output
    assert "CREATED" in output
    assert "80/100" in output


# ##################################################################
# test print generation summary existing
# verifies summary output for existing playlists
def test_print_generation_summary_existing() -> None:
    results = [
        PlaylistGenerationResult(
            decade=1970,
            playlist_name="1970s Top Hits",
            created=False,
            already_existed=True,
            songs_added=0,
            songs_not_found=0,
            total_songs=0,
        ),
    ]
    captured = StringIO()
    sys.stdout = captured
    try:
        print_generation_summary(results)
    finally:
        sys.stdout = sys.__stdout__
    output = captured.getvalue()
    assert "1970s Top Hits" in output
    assert "EXISTING" in output


# ##################################################################
# test print generation summary totals
# verifies summary totals are calculated correctly
def test_print_generation_summary_totals() -> None:
    results = [
        PlaylistGenerationResult(
            decade=1960,
            playlist_name="1960s Top Hits",
            created=True,
            already_existed=False,
            songs_added=80,
            songs_not_found=20,
            total_songs=100,
        ),
        PlaylistGenerationResult(
            decade=1970,
            playlist_name="1970s Top Hits",
            created=True,
            already_existed=False,
            songs_added=90,
            songs_not_found=10,
            total_songs=100,
        ),
    ]
    captured = StringIO()
    sys.stdout = captured
    try:
        print_generation_summary(results)
    finally:
        sys.stdout = sys.__stdout__
    output = captured.getvalue()
    assert "Playlists created: 2" in output
    assert "Total songs added: 170" in output
    assert "Songs not in library: 30" in output


# ##################################################################
# test create decade playlist delegates
# verifies create_decade_playlist calls generate_decade_playlist
def test_create_decade_playlist_delegates(monkeypatch) -> None:
    sentinel = PlaylistGenerationResult(
        decade=1970,
        playlist_name="1970s Top Hits",
        created=True,
        already_existed=False,
        songs_added=100,
        songs_not_found=0,
        total_songs=100,
    )

    def fake_generate(conn, decade):
        assert conn == "conn"
        assert decade == 1970
        return sentinel

    monkeypatch.setattr("src.playlist_generator.generate_decade_playlist", fake_generate)
    result = create_decade_playlist("conn", 1970)
    assert result is sentinel
