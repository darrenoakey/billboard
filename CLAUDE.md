# Billboard Project Guidelines

## Prohibited Technologies

- **AppleScript is NOT allowed** in this repository. Do not use osascript, .scpt files, or any AppleScript-based automation. All automation must be done through proper APIs.
- **Single exception — playlist artwork:** the Apple Music REST API (and the music.apple.com web player) has no way to set playlist artwork. `tools/PlaylistArtwork` (signed Swift .app, ScriptingBridge Apple Events to Music.app) is the only sanctioned Music.app automation, and only for artwork. It needs a one-time macOS grant: System Settings > Privacy & Security > Automation > PlaylistArtwork > Music. Agents cannot grant it (TCC; SIP on).

## Apple Music Integration

- Use the Apple Music API (REST) for all interactions with Apple Music
- Authentication uses JWT developer tokens and Music User Tokens
- API base URL: `https://api.music.apple.com/v1`

## Credentials & Configuration

- Apple Music credentials (team ID, key ID, private key path) live in `~/.config/billboard/config.json` — never hardcode them in source
- Music User Token lives in `~/.config/billboard/music_user_token`
- Private key file referenced by path in config, stored at `~/keys/apple music/`
- `src/apple_music.py:load_config()` is the canonical config loader — tests and tools should use it (or read config.json directly for standalone scripts)

## Movie Soundtrack Playlists

- `./run movie "movie: romeo + juliet 1996"` (also `~/bin/movie:` wrapper) — `src/movie_soundtrack.py` resolves the film via Wikipedia search, reads the film + soundtrack articles and MusicBrainz soundtrack tracklists, and asks OpenAI (`gpt-5.1`, key `daz-secrets get openai api_key`) for the ordered song list. `daz-agent-sdk` was broken on this machine (Claude CLI error -> gemini without key), hence the direct call.
- `src/movie_playlist.py` matches each song in the user's storefront catalog, then falls back to the user's own library (`library-songs`), creates `"<Film> (<year>) Soundtrack"` (replacing an existing one), adds matched tracks in order, and writes `output/movie_playlists/<slug>.json`. Ambiguous matches (score 0.72-0.85) are reported but NOT added.
- Songs missing from the Apple Music catalog can be added by dropping correctly tagged audio into `~/Music/Music/Media.localized/Automatically Add to Music.localized/`; after iCloud upload (a few minutes) they are found as library songs on the next run.
- Poster: the Wikipedia infobox image of the film article, padded to a square in `playlist_covers/movies/`. Artwork is applied asynchronously by the PlaylistArtwork helper from `~/.config/billboard/artwork_jobs/`; `./run movie-artwork` re-launches it and shows its status.
- A full `movie` run takes 2-4 minutes (LLM + ~2 catalog searches per song); run it detached from agent turns.
- Music user tokens expire (Jan 2026 token was dead by Sep 2026). Re-auth with `tools/music_auth_server.py` (MusicKit JS authorize flow).

## Song Arena

- Web UI on port 8780, managed by `auto` as `song-arena`
- Arena uses graph-based scoring (BFS transitive wins), not ELO
- `get_matchup_for_song()` finds a new opponent for a specific song (used after eliminate to keep survivor)
- MusicKit v3 `seekToTime()` requires waiting for `PlaybackStates.playing` before seeking — otherwise silently fails
- Static files use content-hash cache busting via `{{ static:filename }}` template tags

## Code Standards

- Python codebase
- Follow existing patterns in `src/` directory
- Tests should be included for new functionality
- Run tests: `./run test src/<file>_test.py`
- Run lint: `./run lint`
- Full quality gate: `./run check` (requires `dazpycheck`)
