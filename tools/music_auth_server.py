import http.server
import socketserver
import webbrowser
from pathlib import Path

PORT = 8766

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>Apple Music Authorization</title>
    <style>
        body { font-family: -apple-system, sans-serif; padding: 40px; text-align: center; }
        button { padding: 20px 40px; font-size: 18px; cursor: pointer; background: #fa243c; color: white; border: none; border-radius: 8px; }
        button:hover { background: #d91e35; }
        #status { margin-top: 20px; padding: 20px; }
        #token { word-break: break-all; background: #f0f0f0; padding: 10px; margin: 10px; font-family: monospace; font-size: 12px; max-height: 200px; overflow-y: auto; }
        .success { color: green; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>Apple Music Authorization</h1>
    <p>Click the button below to authorize access to Apple Music</p>
    <button id="authBtn" onclick="authorize()">Authorize Apple Music</button>
    <div id="status"></div>
    <script src="https://js-cdn.music.apple.com/musickit/v3/musickit.js" async></script>
    <script>
        const devToken = '__DEV_TOKEN__';
        let music;

        document.addEventListener('musickitloaded', async () => {
            try {
                await MusicKit.configure({
                    developerToken: devToken,
                    app: {
                        name: 'Billboard Playlists',
                        build: '1.0'
                    }
                });
                music = MusicKit.getInstance();
                document.getElementById('status').innerHTML = '<p>MusicKit loaded. Click button to authorize.</p>';
            } catch (err) {
                document.getElementById('status').innerHTML = '<p class="error">Error loading MusicKit: ' + err.message + '</p>';
            }
        });

        async function authorize() {
            if (!music) {
                document.getElementById('status').innerHTML = '<p class="error">MusicKit not loaded yet. Please wait.</p>';
                return;
            }

            document.getElementById('status').innerHTML = '<p>Authorizing...</p>';

            try {
                const token = await music.authorize();
                document.getElementById('status').innerHTML =
                    '<p class="success">Authorization successful!</p>' +
                    '<p>Your Music User Token:</p>' +
                    '<div id="token">' + token + '</div>' +
                    '<p>Saving token...</p>';

                // Send token to server
                const response = await fetch('/save_token', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({token: token})
                });

                if (response.ok) {
                    document.getElementById('status').innerHTML +=
                        '<p class="success">Token saved! You can close this window.</p>';
                } else {
                    document.getElementById('status').innerHTML +=
                        '<p class="error">Failed to save token</p>';
                }
            } catch (err) {
                document.getElementById('status').innerHTML =
                    '<p class="error">Authorization failed: ' + err.message + '</p>';
            }
        }
    </script>
</body>
</html>"""


class TokenHandler(http.server.SimpleHTTPRequestHandler):
    token_received = None

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            dev_token = generate_developer_token()
            html = HTML_PAGE.replace("__DEV_TOKEN__", dev_token)
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/save_token":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            import json

            data = json.loads(post_data.decode())
            token = data.get("token")

            if token:
                save_token(token)
                TokenHandler.token_received = token
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            else:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, _format, *_args):
        pass


def generate_developer_token():
    import json
    import jwt
    import time

    config_path = Path.home() / ".config" / "billboard" / "config.json"
    cfg = json.loads(config_path.read_text())
    key_path = Path(cfg["apple_music_private_key_path"]).expanduser()
    private_key = key_path.read_text()
    now = int(time.time())

    payload = {
        "iss": cfg["apple_music_team_id"],
        "iat": now,
        "exp": now + 3600 * 12,
    }
    headers = {
        "alg": "ES256",
        "kid": cfg["apple_music_key_id"],
    }

    return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


def save_token(token):
    config_dir = Path.home() / ".config" / "billboard"
    config_dir.mkdir(parents=True, exist_ok=True)
    token_file = config_dir / "music_user_token"
    token_file.write_text(token)
    print(f"Token saved to {token_file}")


def run_server():
    with socketserver.TCPServer(("", PORT), TokenHandler) as httpd:
        print(f"Server running at http://localhost:{PORT}")
        print("Opening browser for authorization...")
        webbrowser.open(f"http://localhost:{PORT}")

        def check_token():
            while TokenHandler.token_received is None:
                httpd.handle_request()
            print("Token received, shutting down server...")

        check_token()


if __name__ == "__main__":
    print("Apple Music Authorization Server")
    print("=" * 40)
    run_server()
