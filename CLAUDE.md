# Billboard Project Guidelines

## Prohibited Technologies

- **AppleScript is NOT allowed** in this repository. Do not use osascript, .scpt files, or any AppleScript-based automation. All automation must be done through proper APIs.

## Apple Music Integration

- Use the Apple Music API (REST) for all interactions with Apple Music
- Authentication uses JWT developer tokens and Music User Tokens
- API base URL: `https://api.music.apple.com/v1`

## Credentials & Configuration

- Apple Music credentials (team ID, key ID, private key path) live in `~/.config/billboard/config.json` — never hardcode them in source
- Music User Token lives in `~/.config/billboard/music_user_token`
- Private key file referenced by path in config, stored at `~/keys/apple music/`
- `src/apple_music.py:load_config()` is the canonical config loader — tests and tools should use it (or read config.json directly for standalone scripts)

## Code Standards

- Python codebase
- Follow existing patterns in `src/` directory
- Tests should be included for new functionality
- Run tests: `./run test src/<file>_test.py`
- Run lint: `./run lint`
- Full quality gate: `./run check` (requires `dazpycheck`)
