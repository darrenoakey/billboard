# Billboard Project Guidelines

## Prohibited Technologies

- **AppleScript is NOT allowed** in this repository. Do not use osascript, .scpt files, or any AppleScript-based automation. All automation must be done through proper APIs.

## Apple Music Integration

- Use the Apple Music API (REST) for all interactions with Apple Music
- Authentication uses JWT developer tokens and Music User Tokens
- API base URL: `https://api.music.apple.com/v1`

## Code Standards

- Python codebase
- Follow existing patterns in `src/` directory
- Tests should be included for new functionality
