import http.server
import json
import socketserver
import threading
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

from tools.music_auth_server import (
    generate_developer_token,
    save_token,
    HTML_PAGE,
    TokenHandler,
    PORT,
)


# ##################################################################
# test generate developer token returns valid jwt
# verifies token generation produces valid jwt format
def test_generate_developer_token_returns_jwt() -> None:
    token = generate_developer_token()
    assert token is not None
    assert isinstance(token, str)
    parts = token.split(".")
    assert len(parts) == 3


# ##################################################################
# test generate developer token repeatable
# verifies multiple calls return consistent format
def test_generate_developer_token_repeatable() -> None:
    token1 = generate_developer_token()
    token2 = generate_developer_token()
    assert token1 is not None
    assert token2 is not None
    parts1 = token1.split(".")
    parts2 = token2.split(".")
    assert parts1[0] == parts2[0]


# ##################################################################
# test save token creates file
# verifies token is saved to correct location
def test_save_token_creates_file() -> None:
    test_token = "test_token_value_12345"
    save_token(test_token)

    config_dir = Path.home() / ".config" / "billboard"
    token_file = config_dir / "music_user_token"
    assert token_file.exists()
    content = token_file.read_text()
    assert content == test_token


# ##################################################################
# test html page contains musickit script
# verifies html template includes musickit js
def test_html_page_contains_musickit_script() -> None:
    assert "musickit.js" in HTML_PAGE
    assert "__DEV_TOKEN__" in HTML_PAGE
    assert "MusicKit.configure" in HTML_PAGE


# ##################################################################
# test html page contains authorization function
# verifies html template includes authorize functionality
def test_html_page_contains_authorization() -> None:
    assert "authorize" in HTML_PAGE
    assert "music.authorize()" in HTML_PAGE
    assert "/save_token" in HTML_PAGE


# ##################################################################
# test port constant
# verifies port is correctly configured
def test_port_constant() -> None:
    assert PORT == 8766


# ##################################################################
# test token handler class exists
# verifies handler class is defined correctly
def test_token_handler_class_exists() -> None:
    assert issubclass(TokenHandler, http.server.SimpleHTTPRequestHandler)
    assert hasattr(TokenHandler, "token_received")
    assert hasattr(TokenHandler, "do_GET")
    assert hasattr(TokenHandler, "do_POST")
    assert hasattr(TokenHandler, "log_message")


# ##################################################################
# test html page structure
# verifies html contains expected elements
def test_html_page_structure() -> None:
    assert "<!DOCTYPE html>" in HTML_PAGE
    assert "<html>" in HTML_PAGE
    assert "</html>" in HTML_PAGE
    assert "<head>" in HTML_PAGE
    assert "<body>" in HTML_PAGE
    assert "Apple Music Authorization" in HTML_PAGE


TEST_PORT = 18766


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


# ##################################################################
# test handler get returns html
# verifies handler serves html page on root path
def test_handler_get_returns_html() -> None:
    TokenHandler.token_received = None

    with ReusableTCPServer(("", TEST_PORT), TokenHandler) as httpd:
        server_thread = threading.Thread(target=httpd.handle_request)
        server_thread.start()

        response = urlopen(f"http://localhost:{TEST_PORT}/")
        content = response.read().decode()

        server_thread.join(timeout=5)

    assert "Apple Music Authorization" in content
    assert "MusicKit" in content


# ##################################################################
# test handler get index returns html
# verifies handler serves html page on index.html path
def test_handler_get_index_returns_html() -> None:
    TokenHandler.token_received = None

    with ReusableTCPServer(("", TEST_PORT + 1), TokenHandler) as httpd:
        server_thread = threading.Thread(target=httpd.handle_request)
        server_thread.start()

        response = urlopen(f"http://localhost:{TEST_PORT + 1}/index.html")
        content = response.read().decode()

        server_thread.join(timeout=5)

    assert "Apple Music Authorization" in content


# ##################################################################
# test handler get 404 for unknown path
# verifies handler returns 404 for unknown paths
def test_handler_get_unknown_path() -> None:
    TokenHandler.token_received = None

    with ReusableTCPServer(("", TEST_PORT + 2), TokenHandler) as httpd:
        server_thread = threading.Thread(target=httpd.handle_request)
        server_thread.start()

        try:
            urlopen(f"http://localhost:{TEST_PORT + 2}/unknown")
            assert False, "Should have raised HTTPError"
        except URLError as e:
            assert hasattr(e, "code") and e.code == 404

        server_thread.join(timeout=5)


# ##################################################################
# test handler post saves token
# verifies handler saves token on save_token path
def test_handler_post_saves_token() -> None:
    TokenHandler.token_received = None
    test_token = "test_token_from_post"

    with ReusableTCPServer(("", TEST_PORT + 3), TokenHandler) as httpd:
        server_thread = threading.Thread(target=httpd.handle_request)
        server_thread.start()

        data = json.dumps({"token": test_token}).encode()
        req = Request(
            f"http://localhost:{TEST_PORT + 3}/save_token",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        response = urlopen(req)
        content = response.read().decode()

        server_thread.join(timeout=5)

    assert '"status": "ok"' in content
    assert TokenHandler.token_received == test_token


# ##################################################################
# test handler post 400 for missing token
# verifies handler returns 400 when token is missing
def test_handler_post_missing_token() -> None:
    TokenHandler.token_received = None

    with ReusableTCPServer(("", TEST_PORT + 4), TokenHandler) as httpd:
        server_thread = threading.Thread(target=httpd.handle_request)
        server_thread.start()

        data = json.dumps({}).encode()
        req = Request(
            f"http://localhost:{TEST_PORT + 4}/save_token",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(req)
            assert False, "Should have raised HTTPError"
        except URLError as e:
            assert hasattr(e, "code") and e.code == 400

        server_thread.join(timeout=5)


# ##################################################################
# test handler post 404 for unknown path
# verifies handler returns 404 for unknown post paths
def test_handler_post_unknown_path() -> None:
    TokenHandler.token_received = None

    with ReusableTCPServer(("", TEST_PORT + 5), TokenHandler) as httpd:
        server_thread = threading.Thread(target=httpd.handle_request)
        server_thread.start()

        data = json.dumps({"token": "test"}).encode()
        req = Request(
            f"http://localhost:{TEST_PORT + 5}/unknown",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(req)
            assert False, "Should have raised HTTPError"
        except URLError as e:
            assert hasattr(e, "code") and e.code == 404

        server_thread.join(timeout=5)
