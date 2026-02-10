![](banner.jpg)

# Billboard Hot 100 Charts & Apple Music Playlists

Download every Billboard Hot 100 chart since 1958 and automatically generate decade-based playlists in Apple Music featuring each era's biggest hits.

## What It Does

- Downloads 3,500+ weeks of Billboard Hot 100 chart data into a local database
- Ranks songs using a composite scoring algorithm based on chart performance
- Searches the Apple Music catalog and builds decade playlists (1950s through 2020s) with the top 10 songs from each year
- Manages playlists: detects duplicates, removes incomplete playlists, and regenerates them

## Prerequisites

- Python 3
- An [Apple Music developer account](https://developer.apple.com) with a MusicKit private key
- An Apple Music subscription (for playlist creation)

## Installation

```bash
pip install -r requirements.txt
```

### Apple Music Authentication

1. Place your MusicKit private key at `~/keys/apple music/AuthKey_<YOUR_KEY_ID>.p8`
2. Run the authentication server to obtain your Music User Token:
   ```bash
   python tools/music_auth_server.py
   ```
3. Authorize in the browser window that opens. Your token is saved to `~/.config/billboard/music_user_token`.

## Usage

### Download Chart Data

Download all Billboard Hot 100 charts from August 1958 to present:

```bash
./run download
```

Download a limited number of weeks (useful for testing):

```bash
./run download --limit 10
```

Downloads are idempotent — running the command again only fetches new data.

### View Database Statistics

```bash
./run stats
```

```
Total charts: 1
Total chart weeks: 3520
Total entries: 352000

By chart:
  Billboard Hot 100: 3520 weeks
```

### View Top Songs

Top 10 songs for a specific year:

```bash
./run top --year 1985
```

Top 20 songs for a specific year:

```bash
./run top --year 1985 --limit 20
```

Top songs for an entire decade (top 10 per year):

```bash
./run top --decade 1980
```

```
Top songs for the 1980s:
============================================================
  1. Olivia Newton-John - Physical
      Weeks #1: 10, Top 10: 17, Peak: 1
  2. Kim Carnes - Bette Davis Eyes
      Weeks #1: 9, Top 10: 16, Peak: 1
  ...
```

### Generate Apple Music Playlists

Generate playlists for all decades:

```bash
./run playlists
```

Generate a playlist for a single decade:

```bash
./run playlists --decade 1980
```

This creates a playlist called "1980s Top Hits" in your Apple Music library containing the top 10 songs from each year of the decade, ordered chronologically.

### Clean Up Duplicate Playlists

Preview what would be removed:

```bash
./run cleanup
```

Actually remove duplicates (keeps the playlist with the most tracks):

```bash
./run cleanup --execute
```

### Refresh Incomplete Playlists

Preview which playlists would be deleted and regenerated:

```bash
./run refresh-playlists
```

Delete playlists with fewer than 50 tracks and regenerate all decade playlists:

```bash
./run refresh-playlists --execute
```

Use a custom minimum track threshold:

```bash
./run refresh-playlists --min-tracks 80 --execute
```

### Development

Run a specific test file:

```bash
./run test src/database_test.py
```

Run the linter:

```bash
./run lint
```

Run the full test suite and quality gates:

```bash
./run check
```