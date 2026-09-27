from PIL import Image

from src.movie_artwork import poster_url, square_cover
from src.movie_playlist import artist_similarity, normalize, score_candidate, similarity
from src.movie_soundtrack import SongEntry, musicbrainz_soundtracks, wiki_session


def test_normalize_strips_qualifiers():
    assert normalize("Lovefool (Radio Edit)") == "lovefool"
    assert normalize("Everybody's Free (To Feel Good)") == "everybody s free to feel good"


def test_similarity_requires_word_boundary_containment():
    assert similarity("Lovefool", "Lovefool (2019 Remaster)") == 1.0
    assert similarity("iu", "marius de vries") < 0.9


def test_artist_similarity_matches_any_credit():
    assert artist_similarity("Nellee Hooper, Craig Armstrong & Marius de Vries", "Craig Armstrong") >= 0.9


def test_score_candidate_splits_various_artists_filenames():
    song = SongEntry(title="Everybody's Free (To Feel Good)", artist="Quindon Tarver", source="", note="")
    attrs = {"name": "Quindon Tarver - Everybody's Free (To Feel Good)", "artistName": "Various Artists", "albumName": ""}
    assert score_candidate(song, attrs, "Romeo + Juliet") >= 0.85


def test_score_candidate_penalises_karaoke():
    song = SongEntry(title="Kissing You", artist="Des'ree", source="", note="")
    attrs = {"name": "Kissing You", "artistName": "Des'ree", "albumName": "Karaoke Hits"}
    assert score_candidate(song, attrs, "Romeo + Juliet") < 0.85


def test_square_cover_is_square():
    poster = Image.new("RGB", (400, 600), (200, 30, 30))
    cover = square_cover(poster, size=300)
    assert cover.size == (300, 300)


def test_poster_url_real_wikipedia():
    url = poster_url("Romeo + Juliet")
    assert url.startswith("https://upload.wikimedia.org/")


def test_musicbrainz_real_tracklist():
    sources = musicbrainz_soundtracks(wiki_session(), "Young Einstein", 1988, limit=1)
    assert any("Dumb Things" in text for text in sources.values())
