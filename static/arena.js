let music = null;
let currentMatchup = null;
let nextMatchup = null;
let playingCard = null;
let voting = false;

document.addEventListener('musickitloaded', async () => {
    try {
        await MusicKit.configure({
            developerToken: DEV_TOKEN,
            app: { name: 'Song Arena', build: '1.0' }
        });
        music = MusicKit.getInstance();
    } catch (err) {
        console.warn('MusicKit init failed:', err);
    }
    loadMatchup();
    loadStats();
    loadLeaderboard();
});

async function loadStats() {
    try {
        const r = await fetch('/api/stats');
        const d = await r.json();
        document.getElementById('statMatches').textContent = d.total_matches;
        document.getElementById('statSongs').textContent = d.total_songs;
        document.getElementById('statEliminated').textContent = d.eliminated;
    } catch (e) { console.error(e); }
}

async function loadLeaderboard() {
    try {
        const r = await fetch('/api/leaderboard');
        const d = await r.json();
        renderLeaderboard(d);
    } catch (e) { console.error(e); }
}

function renderLeaderboard(songs) {
    const body = document.getElementById('leaderboardBody');
    if (!songs || !songs.length) {
        body.innerHTML = '<tr><td class="lb-empty">Vote to see rankings appear here</td></tr>';
        return;
    }
    body.innerHTML = songs.map((s, i) => {
        const rc = i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : '';
        return `<tr>
            <td class="lb-rank ${rc}">${i + 1}</td>
            <td>
                <div class="lb-song">${esc(s.song)}</div>
                <div class="lb-artist">${esc(s.artist)} <span class="lb-decade">${s.decade}s</span></div>
            </td>
            <td class="lb-score">${s.score}</td>
        </tr>`;
    }).join('');
}

async function prefetchMatchup() {
    try {
        const r = await fetch('/api/matchup');
        nextMatchup = await r.json();
    } catch (e) { nextMatchup = null; }
}

async function loadMatchup() {
    const container = document.getElementById('arenaContainer');
    const tieBar = document.getElementById('tieBar');
    let data = nextMatchup;
    nextMatchup = null;
    if (!data) {
        tieBar.style.display = 'none';
        container.innerHTML = '<div class="loading"><div class="spinner"></div><div>Loading...</div></div>';
        try {
            const r = await fetch('/api/matchup');
            data = await r.json();
        } catch (e) {
            container.innerHTML = '<div class="loading">Failed to load</div>';
            return;
        }
    }
    if (data.error) {
        container.innerHTML = '<div class="loading">' + esc(data.error) + '</div>';
        tieBar.style.display = 'none';
        return;
    }
    currentMatchup = data;
    voting = false;
    renderMatchup(data.song_a, data.song_b);
    tieBar.style.display = 'flex';
    document.querySelectorAll('.tie-btn').forEach(b => b.disabled = false);
    prefetchMatchup();
}

function renderMatchup(a, b) {
    document.getElementById('arenaContainer').innerHTML =
        songCard(a, 'a') +
        '<div class="vs-badge">VS</div>' +
        songCard(b, 'b');
}

function songCard(song, side) {
    const scoreText = song.score !== undefined ? 'Score: ' + song.score : '';
    return '<div class="song-card" id="card-' + side + '">' +
        '<button class="eliminate-btn" onclick="eliminateSong(\'' + side + '\')" title="Eliminate">&times;</button>' +
        '<div class="decade-badge">' + song.decade + 's</div>' +
        '<div class="song-title">' + esc(song.song) + '</div>' +
        '<div class="song-artist">' + esc(song.artist) + '</div>' +
        (scoreText ? '<div class="song-score">' + scoreText + '</div>' : '<div class="song-score">&nbsp;</div>') +
        '<div class="play-row">' +
            '<button class="play-btn" id="play-' + side + '" onclick="togglePlay(\'' + side + '\', 0)">' +
                '<span>&#9654;</span>' +
            '</button>' +
            '<button class="play-btn skip-btn" id="skip-' + side + '" onclick="togglePlay(\'' + side + '\', 60)" title="Play from 1:00">' +
                '<span>1:00</span>' +
            '</button>' +
        '</div>' +
        '<button class="pick-btn" onclick="pickWinner(\'' + side + '\')">Pick This</button>' +
    '</div>';
}

async function togglePlay(side, startTime) {
    if (!music) { alert('MusicKit not ready'); return; }
    const song = side === 'a' ? currentMatchup.song_a : currentMatchup.song_b;
    const btn = document.getElementById('play-' + side);
    const skipBtn = document.getElementById('skip-' + side);
    const other = side === 'a' ? 'b' : 'a';
    const otherBtn = document.getElementById('play-' + other);
    const otherSkipBtn = document.getElementById('skip-' + other);

    if (playingCard === side) {
        await music.stop();
        btn.classList.remove('playing');
        skipBtn.classList.remove('playing');
        btn.innerHTML = '<span>&#9654;</span>';
        playingCard = null;
        return;
    }

    if (playingCard) {
        await music.stop();
        if (otherBtn) {
            otherBtn.classList.remove('playing');
            otherBtn.innerHTML = '<span>&#9654;</span>';
        }
        if (otherSkipBtn) otherSkipBtn.classList.remove('playing');
    }

    btn.innerHTML = '<span>...</span>';
    try {
        const results = await music.api.music('/v1/catalog/us/search', {
            term: song.song + ' ' + song.artist,
            types: ['songs'],
            limit: 1
        });
        const tracks = results?.data?.results?.songs?.data;
        if (tracks && tracks.length > 0) {
            await music.setQueue({ song: tracks[0].id, startPlaying: true });
            if (startTime > 0) {
                // Wait for playback to actually start before seeking
                await new Promise(resolve => {
                    const check = () => {
                        if (music.playbackState === MusicKit.PlaybackStates.playing) {
                            resolve();
                        } else {
                            setTimeout(check, 100);
                        }
                    };
                    check();
                    // Safety timeout
                    setTimeout(resolve, 3000);
                });
                await music.seekToTime(startTime);
            }
            btn.classList.add('playing');
            if (startTime > 0) skipBtn.classList.add('playing');
            btn.innerHTML = '<span>&#9646;&#9646;</span>';
            playingCard = side;
        } else {
            btn.innerHTML = '<span>&#10007;</span>';
            setTimeout(() => { btn.innerHTML = '<span>&#9654;</span>'; }, 1200);
        }
    } catch (e) {
        console.error(e);
        btn.innerHTML = '<span>&#9654;</span>';
    }
}

async function stopMusic() {
    if (music) { try { await music.stop(); } catch(e) {} }
    playingCard = null;
}

function disableAllButtons() {
    voting = true;
    document.querySelectorAll('.pick-btn, .tie-btn, .eliminate-btn').forEach(b => b.disabled = true);
}

function showFlash(label, songName, artist, detail) {
    document.getElementById('resultLabel').textContent = label;
    document.getElementById('resultSong').textContent = songName;
    document.getElementById('resultArtist').textContent = artist;
    document.getElementById('resultDetail').textContent = detail;
    const flash = document.getElementById('resultFlash');
    flash.classList.add('show');
    setTimeout(() => {
        flash.classList.remove('show');
        loadMatchup();
    }, 600);
}

async function pickWinner(side) {
    if (!currentMatchup || voting) return;
    disableAllButtons();
    await stopMusic();

    const a = currentMatchup.song_a;
    const b = currentMatchup.song_b;
    const outcome = side === 'a' ? 'a_wins' : 'b_wins';
    const winner = side === 'a' ? a : b;

    try {
        const r = await fetch('/api/matchup-result', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ song_a_id: a.id, song_b_id: b.id, outcome: outcome })
        });
        const data = await r.json();
        renderLeaderboard(data.leaderboard);
        loadStats();
        showFlash('Winner', winner.song, winner.artist, '');
    } catch (e) {
        console.error(e);
        loadMatchup();
    }
}

async function recordTie() {
    if (!currentMatchup || voting) return;
    disableAllButtons();
    await stopMusic();

    const a = currentMatchup.song_a;
    const b = currentMatchup.song_b;

    try {
        const r = await fetch('/api/matchup-result', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ song_a_id: a.id, song_b_id: b.id, outcome: 'tie' })
        });
        const data = await r.json();
        renderLeaderboard(data.leaderboard);
        loadStats();
        showFlash('Tie', a.song + ' & ' + b.song, '', '');
    } catch (e) {
        console.error(e);
        loadMatchup();
    }
}

async function eliminateSong(side) {
    if (!currentMatchup || voting) return;
    const song = side === 'a' ? currentMatchup.song_a : currentMatchup.song_b;
    const keeper = side === 'a' ? currentMatchup.song_b : currentMatchup.song_a;
    if (!confirm('Eliminate "' + song.song + '" from the arena?')) return;
    disableAllButtons();
    await stopMusic();

    try {
        await fetch('/api/eliminate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ song_id: song.id })
        });
        loadStats();
        // Load a new matchup keeping the surviving song
        loadMatchupKeeping(keeper.id);
    } catch (e) {
        console.error(e);
        loadMatchup();
    }
}

async function loadMatchupKeeping(keepSongId) {
    const container = document.getElementById('arenaContainer');
    const tieBar = document.getElementById('tieBar');
    tieBar.style.display = 'none';
    container.innerHTML = '<div class="loading"><div class="spinner"></div><div>Loading...</div></div>';
    try {
        const r = await fetch('/api/matchup?keep_song_id=' + keepSongId);
        const data = await r.json();
        if (data.error) {
            container.innerHTML = '<div class="loading">' + esc(data.error) + '</div>';
            return;
        }
        currentMatchup = data;
        voting = false;
        renderMatchup(data.song_a, data.song_b);
        tieBar.style.display = 'flex';
        document.querySelectorAll('.tie-btn').forEach(b => b.disabled = false);
        prefetchMatchup();
    } catch (e) {
        console.error(e);
        container.innerHTML = '<div class="loading">Failed to load</div>';
    }
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
