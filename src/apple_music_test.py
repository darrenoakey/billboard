from src.apple_music import (
    TrackSearchResult,
    get_existing_playlists,
    playlist_exists,
    load_apple_music_client,
)


# ##################################################################
# test track search result found
# verifies dataclass fields for found track
def test_track_search_result_found() -> None:
    result = TrackSearchResult(
        song="Test Song",
        artist="Test Artist",
        found=True,
        track_id="12345",
    )
    assert result.song == "Test Song"
    assert result.artist == "Test Artist"
    assert result.found is True
    assert result.track_id == "12345"


# ##################################################################
# test track search result not found
# verifies dataclass fields for not found track
def test_track_search_result_not_found() -> None:
    result = TrackSearchResult(
        song="Missing Song",
        artist="Unknown Artist",
        found=False,
        track_id=None,
    )
    assert result.song == "Missing Song"
    assert result.artist == "Unknown Artist"
    assert result.found is False
    assert result.track_id is None


# ##################################################################
# test load client
# verifies client can be loaded with credentials
def test_load_client() -> None:
    client = load_apple_music_client()
    assert client is not None
    assert client.developer_token is not None
    assert client.config.music_user_token is not None


# ##################################################################
# test get existing playlists
# verifies playlists can be retrieved from library
def test_get_existing_playlists() -> None:
    playlists = get_existing_playlists()
    assert isinstance(playlists, list)
    assert all(isinstance(name, str) for name in playlists)


# ##################################################################
# test playlist exists known playlist
# verifies known playlist is found
def test_playlist_exists_known() -> None:
    playlists = get_existing_playlists()
    if playlists:
        assert playlist_exists(playlists[0]) is True


# ##################################################################
# test playlist exists unknown playlist
# verifies unknown playlist is not found
def test_playlist_exists_unknown() -> None:
    assert playlist_exists("__this_playlist_definitely_does_not_exist__12345__") is False
