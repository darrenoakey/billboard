let music = null;
let currentMatchup = null;
let nextMatchup = null;
let playingCard = null;
let voting = false;
let arenaMode = 'random';
let gridSongs = [];
let gridPicks = [];

document.addEventListener('musickitloaded', async () => {
    try {
        await MusicKit.configure({
            developerToken: DEV_TOKEN,
            app: { name: 'Song Arena', build: '1.0' }
        });
        music = MusicKit.getInstance();
        music.addEventListener('playbackTimeDidChange', updateScrubber);
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
    if (arenaMode === 'random') prefetchMatchup();
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
        '</div>' +
        '<div class="scrubber-row" id="scrubber-' + side + '">' +
            '<span class="scrubber-time" id="scrubber-cur-' + side + '">0:00</span>' +
            '<input type="range" class="scrubber-range" id="scrubber-range-' + side + '" min="0" max="0" value="0" step="1" oninput="seekTo(\'' + side + '\', this.value)">' +
            '<span class="scrubber-time" id="scrubber-dur-' + side + '">0:00</span>' +
        '</div>' +
        '<button class="pick-btn" onclick="pickWinner(\'' + side + '\')">Pick This</button>' +
    '</div>';
}

function formatTime(seconds) {
    const s = Math.floor(seconds);
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

function seekTo(side, value) {
    if (music && playingCard === side) {
        music.seekToTime(parseFloat(value));
    }
}

function resetScrubber(side) {
    const cur = document.getElementById('scrubber-cur-' + side);
    const dur = document.getElementById('scrubber-dur-' + side);
    const range = document.getElementById('scrubber-range-' + side);
    if (cur) cur.textContent = '0:00';
    if (dur) dur.textContent = '0:00';
    if (range) { range.max = 0; range.value = 0; }
}

function updateScrubber() {
    if (!music || !playingCard) return;
    const side = playingCard;
    const cur = document.getElementById('scrubber-cur-' + side);
    const dur = document.getElementById('scrubber-dur-' + side);
    const range = document.getElementById('scrubber-range-' + side);
    if (!cur || !dur || !range) return;
    const duration = music.currentPlaybackDuration || 0;
    const currentTime = music.currentPlaybackTime || 0;
    range.max = duration;
    range.value = currentTime;
    cur.textContent = formatTime(currentTime);
    dur.textContent = formatTime(duration);
}

function getSongForSide(side) {
    if (side.startsWith('g')) {
        return gridSongs[parseInt(side.substring(1))];
    }
    return side === 'a' ? currentMatchup.song_a : currentMatchup.song_b;
}

async function togglePlay(side, startTime) {
    if (!music) { alert('MusicKit not ready'); return; }
    const song = getSongForSide(side);
    const btn = document.getElementById('play-' + side);

    if (playingCard === side) {
        await music.stop();
        btn.classList.remove('playing');
        btn.innerHTML = '<span>&#9654;</span>';
        resetScrubber(side);
        playingCard = null;
        return;
    }

    if (playingCard) {
        const prevBtn = document.getElementById('play-' + playingCard);
        await music.stop();
        if (prevBtn) {
            prevBtn.classList.remove('playing');
            prevBtn.innerHTML = '<span>&#9654;</span>';
        }
        resetScrubber(playingCard);
        playingCard = null;
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
                await new Promise(resolve => {
                    const check = () => {
                        if (music.playbackState === MusicKit.PlaybackStates.playing) {
                            resolve();
                        } else {
                            setTimeout(check, 100);
                        }
                    };
                    check();
                    setTimeout(resolve, 3000);
                });
                await music.seekToTime(startTime);
            }
            btn.classList.add('playing');
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
    if (playingCard) {
        const btn = document.getElementById('play-' + playingCard);
        if (btn) { btn.classList.remove('playing'); btn.innerHTML = '<span>&#9654;</span>'; }
        resetScrubber(playingCard);
    }
    playingCard = null;
}

function disableAllButtons() {
    voting = true;
    document.querySelectorAll('.pick-btn, .tie-btn, .eliminate-btn').forEach(b => b.disabled = true);
}

function toggleMode(mode) {
    arenaMode = mode;
    document.getElementById('modeRandom').classList.toggle('active', arenaMode === 'random');
    document.getElementById('modeKoth').classList.toggle('active', arenaMode === 'koth');
    document.getElementById('modeTop4').classList.toggle('active', arenaMode === 'top4');

    const arenaContainer = document.getElementById('arenaContainer');
    const tieBar = document.getElementById('tieBar');
    const gridView = document.getElementById('gridView');

    if (arenaMode === 'top4') {
        arenaContainer.style.display = 'none';
        tieBar.style.display = 'none';
        gridView.style.display = 'block';
        stopMusic();
        loadGrid();
    } else {
        arenaContainer.style.display = '';
        gridView.style.display = 'none';
        loadMatchup();
    }
}

async function loadGrid() {
    const container = document.getElementById('gridContainer');
    container.innerHTML = '<div class="loading"><div class="spinner"></div><div>Loading songs...</div></div>';
    gridPicks = [];
    updateGridSubmitBtn();
    try {
        const r = await fetch('/api/grid-songs');
        const data = await r.json();
        gridSongs = data.songs;
        renderGrid();
    } catch (e) {
        container.innerHTML = '<div class="loading">Failed to load</div>';
    }
}

function renderGrid() {
    const container = document.getElementById('gridContainer');
    const side = (i) => 'g' + i;
    container.innerHTML = gridSongs.map((s, i) => {
        return '<div class="grid-tile" id="grid-tile-' + i + '" onclick="gridTileClick(' + s.id + ')">' +
            '<div class="grid-decade">' + s.decade + 's</div>' +
            '<div class="grid-song">' + esc(s.song) + '</div>' +
            '<div class="grid-artist">' + esc(s.artist) + '</div>' +
            '<div class="grid-play-row">' +
                '<button class="grid-play-btn" id="play-' + side(i) + '" onclick="event.stopPropagation(); togglePlay(\'' + side(i) + '\', 0)">' +
                    '<span>&#9654;</span>' +
                '</button>' +
            '</div>' +
            '<div class="scrubber-row grid-scrubber" id="scrubber-' + side(i) + '">' +
                '<span class="scrubber-time" id="scrubber-cur-' + side(i) + '">0:00</span>' +
                '<input type="range" class="scrubber-range" id="scrubber-range-' + side(i) + '" min="0" max="0" value="0" step="1" onclick="event.stopPropagation()" oninput="event.stopPropagation(); seekTo(\'' + side(i) + '\', this.value)">' +
                '<span class="scrubber-time" id="scrubber-dur-' + side(i) + '">0:00</span>' +
            '</div>' +
        '</div>';
    }).join('');
    updateGridOverlays();
}

function gridTileClick(songId) {
    const idx = gridPicks.indexOf(songId);
    if (idx !== -1) {
        gridPicks.splice(idx, 1);
    } else {
        gridPicks.push(songId);
    }
    updateGridOverlays();
    updateGridSubmitBtn();
}

function updateGridOverlays() {
    const colors = ['gold', 'silver', 'bronze', 'blue'];
    gridSongs.forEach((s, i) => {
        const tile = document.getElementById('grid-tile-' + i);
        if (!tile) return;
        const pickIdx = gridPicks.indexOf(s.id);
        const picked = pickIdx !== -1;
        tile.classList.toggle('picked', picked);
        const existing = tile.querySelector('.pick-overlay');
        if (existing) existing.remove();
        if (picked) {
            const overlay = document.createElement('div');
            const colorClass = pickIdx < 4 ? colors[pickIdx] : 'numbered';
            overlay.className = 'pick-overlay ' + colorClass;
            overlay.textContent = pickIdx + 1;
            tile.prepend(overlay);
        }
    });
}

function updateGridSubmitBtn() {
    const btn = document.getElementById('gridSubmitBtn');
    if (!btn) return;
    const n = gridPicks.length;
    btn.disabled = n < 1;
    if (n === 0) {
        btn.textContent = 'Submit';
    } else {
        const battles = n * (n - 1) / 2 + n * (gridSongs.length - n);
        btn.textContent = 'Submit ' + n + ' ranked (' + battles + ' battles)';
    }
}

async function submitTop4() {
    if (gridPicks.length < 1) return;
    const others = gridSongs.map(s => s.id).filter(id => !gridPicks.includes(id));
    const n = gridPicks.length;
    const battles = n * (n - 1) / 2 + n * others.length;
    document.getElementById('gridSubmitBtn').disabled = true;
    try {
        const r = await fetch('/api/grid-result', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ rankings: gridPicks, others: others })
        });
        const data = await r.json();
        renderLeaderboard(data.leaderboard);
        loadStats();
        showFlash('Submitted', n + ' ranked, ' + battles + ' battles', '', '', loadGrid);
    } catch (e) {
        console.error(e);
        loadGrid();
    }
}

function resetTop4() {
    gridPicks = [];
    renderGrid();
    updateGridSubmitBtn();
}

function showFlash(label, songName, artist, detail, afterFn) {
    document.getElementById('resultLabel').textContent = label;
    document.getElementById('resultSong').textContent = songName;
    document.getElementById('resultArtist').textContent = artist;
    document.getElementById('resultDetail').textContent = detail;
    const flash = document.getElementById('resultFlash');
    flash.classList.add('show');
    const next = afterFn || loadMatchup;
    setTimeout(() => {
        flash.classList.remove('show');
        next();
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
        const afterFn = arenaMode === 'koth'
            ? () => loadMatchupKeeping(winner.id)
            : null;
        showFlash('Winner', winner.song, winner.artist, '', afterFn);
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
        if (arenaMode === 'random') prefetchMatchup();
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
