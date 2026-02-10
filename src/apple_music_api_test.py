from pathlib import Path

from src.apple_music import load_config
from src.apple_music_api import (
    AppleMusicConfig,
    AppleMusicClient,
    generate_developer_token,
    search_song_in_catalog,
)


# ##################################################################
# load real config for integration tests
# reads credentials from config file
def _make_config() -> AppleMusicConfig:
    cfg = load_config()
    user_token_path = Path.home() / ".config" / "billboard" / "music_user_token"
    user_token = user_token_path.read_text().strip()
    return AppleMusicConfig(
        team_id=cfg["apple_music_team_id"],
        key_id=cfg["apple_music_key_id"],
        private_key_path=Path(cfg["apple_music_private_key_path"]).expanduser(),
        music_user_token=user_token,
    )


# ##################################################################
# test apple music config fields
# verifies dataclass holds configuration values
def test_apple_music_config_fields() -> None:
    config = AppleMusicConfig(
        team_id="TEST_TEAM",
        key_id="TEST_KEY",
        private_key_path=Path("/test/path"),
        music_user_token="TEST_TOKEN",
    )
    assert config.team_id == "TEST_TEAM"
    assert config.key_id == "TEST_KEY"
    assert config.private_key_path == Path("/test/path")
    assert config.music_user_token == "TEST_TOKEN"


# ##################################################################
# test generate developer token format
# verifies token is valid jwt structure
def test_generate_developer_token_format() -> None:
    config = _make_config()
    token = generate_developer_token(config)
    assert token is not None
    assert isinstance(token, str)
    parts = token.split(".")
    assert len(parts) == 3


# ##################################################################
# test apple music client initialization
# verifies client is created with valid token
def test_apple_music_client_initialization() -> None:
    config = _make_config()
    client = AppleMusicClient(config)
    assert client.developer_token is not None
    assert "Authorization" in client.session.headers
    assert "Music-User-Token" in client.session.headers


# ##################################################################
# test search catalog returns results
# verifies catalog search returns songs
def test_search_catalog_returns_results() -> None:
    config = _make_config()
    client = AppleMusicClient(config)
    results = client.search_catalog("Bohemian Rhapsody Queen")
    assert isinstance(results, list)
    assert len(results) > 0
    assert "id" in results[0]
    assert "attributes" in results[0]


# ##################################################################
# test search song in catalog finds match
# verifies specific song search returns id
def test_search_song_in_catalog_finds_match() -> None:
    config = _make_config()
    client = AppleMusicClient(config)
    track_id = search_song_in_catalog(client, "Bohemian Rhapsody", "Queen")
    assert track_id is not None
    assert isinstance(track_id, str)


# ##################################################################
# test get library playlists returns list
# verifies library playlists retrieval
def test_get_library_playlists_returns_list() -> None:
    config = _make_config()
    client = AppleMusicClient(config)
    playlists = client.get_library_playlists()
    assert isinstance(playlists, list)
