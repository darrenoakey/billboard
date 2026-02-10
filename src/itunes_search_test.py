from src.itunes_search import (
    search_itunes,
    find_best_match,
    ItunesTrack,
)


# ##################################################################
# test itunes track dataclass
# verifies dataclass fields are set correctly
def test_itunes_track_dataclass() -> None:
    track = ItunesTrack(
        track_id=12345,
        track_name="Test Song",
        artist_name="Test Artist",
        collection_name="Test Album",
    )
    assert track.track_id == 12345
    assert track.track_name == "Test Song"
    assert track.artist_name == "Test Artist"
    assert track.collection_name == "Test Album"


# ##################################################################
# test find best match exact
# verifies exact match is found first
def test_find_best_match_exact() -> None:
    results = [
        {"trackName": "Other Song", "artistName": "Other Artist"},
        {"trackName": "My Song", "artistName": "My Artist"},
    ]
    match = find_best_match(results, "My Song", "My Artist")
    assert match is not None
    assert match["trackName"] == "My Song"


# ##################################################################
# test find best match song only
# verifies song title match when artist differs
def test_find_best_match_song_only() -> None:
    results = [
        {"trackName": "My Song", "artistName": "Different Artist"},
    ]
    match = find_best_match(results, "My Song", "Original Artist")
    assert match is not None
    assert match["trackName"] == "My Song"


# ##################################################################
# test find best match first result
# verifies first result is returned when no exact match
def test_find_best_match_first_result() -> None:
    results = [
        {"trackName": "Completely Different", "artistName": "Unknown"},
    ]
    match = find_best_match(results, "My Song", "My Artist")
    assert match is not None
    assert match["trackName"] == "Completely Different"


# ##################################################################
# test find best match empty
# verifies none is returned for empty results
def test_find_best_match_empty() -> None:
    match = find_best_match([], "My Song", "My Artist")
    assert match is None


# ##################################################################
# test search itunes real
# verifies real itunes api search works
def test_search_itunes_real() -> None:
    result = search_itunes("Bohemian Rhapsody", "Queen")
    assert result is not None
    assert result.track_id > 0
    assert "bohemian" in result.track_name.lower() or "queen" in result.artist_name.lower()


# ##################################################################
# test search itunes not found
# verifies none is returned for nonsense query
def test_search_itunes_not_found() -> None:
    result = search_itunes("xyzabc123notarealsongtitle", "notarealartist999")
    assert result is None
