// ═══════════════════════════════════════════════
//  Config
// ═══════════════════════════════════════════════
const API_BASE          = 'http://localhost:8000';
const SESSION_KEY       = 'scenery_session_id';

// ═══════════════════════════════════════════════
//  State
// ═══════════════════════════════════════════════
let call            = null;
let callReady       = false;
let connecting      = false;
let sessionActive   = false;
let lastFinalText   = '';

// ═══════════════════════════════════════════════
//  DOM
// ═══════════════════════════════════════════════
const orbBtn    = document.getElementById('orbBtn');
const orbScene  = document.getElementById('orbScene');
const orbLabel  = document.getElementById('orbLabel');
const endBtn    = document.getElementById('endBtn');
const statusDot = document.getElementById('statusDot');
const statusText= document.getElementById('statusText');
const transcript= document.getElementById('transcript');

// ═══════════════════════════════════════════════
//  Boot
// ═══════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
    initConnection();
    orbBtn.addEventListener('click', handleOrbClick);
    endBtn.addEventListener('click', endSession);
});

// ═══════════════════════════════════════════════
//  Connection — create Daily room & join
// ═══════════════════════════════════════════════
async function initConnection() {
    if (connecting) return;
    connecting = true;
    setStatus('connecting', 'Connecting');
    setOrbState('idle');

    try {
        if (!callReady) {
            call = window.DailyIframe.createCallObject({
                audioSource: true,
                videoSource: false,
                subscribeToTracksAutomatically: true,
            });
            call.on('joined-meeting',        onJoined);
            call.on('left-meeting',          onLeft);
            call.on('error',                 onError);
            call.on('app-message',           onAppMessage);
            call.on('active-speaker-change', onActiveSpeaker);
            call.on('track-started',         onTrackStarted);
            callReady = true;
        }

        const state = call.meetingState();
        if (state === 'joined-meeting' || state === 'joining-meeting') {
            await call.leave();
            return;
        }

        const resp = await fetch(`${API_BASE}/voice/room`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: getSessionId() }),
        });
        if (!resp.ok) {
            const body = await resp.text();
            throw new Error(`Room error (${resp.status}): ${body}`);
        }
        const { room_url, token } = await resp.json();
        await call.join({ url: room_url, token });

    } catch (err) {
        console.error('[Voice] initConnection error:', err);
        setStatus('error', 'Retrying');
        setOrbState('idle');
        setTimeout(initConnection, 4000);
    } finally {
        connecting = false;
    }
}

// ═══════════════════════════════════════════════
//  Daily event handlers
// ═══════════════════════════════════════════════
function onJoined() {
    setStatus('connected', 'Ready');
    call.setLocalAudio(false);
    setOrbState('idle');
    orbBtn.disabled = false;
    orbLabel.textContent = 'Tap to speak';
}

function onLeft() {
    sessionActive = false;
    setStatus('disconnected', 'Reconnecting');
    setOrbState('idle');
    orbBtn.disabled = true;
    orbLabel.textContent = 'Reconnecting';
    endBtn.style.display = 'none';
    setTimeout(initConnection, 2500);
}

function onError(evt) {
    console.error('[Daily] error', evt);
    setStatus('error', 'Retrying');
    endBtn.style.display = 'none';
    sessionActive = false;
    if (call) { call.leave().catch(() => {}); }
    setTimeout(initConnection, 3000);
}

// ─── Audio track playback ───────────────────────
const audioElements = {};

function onTrackStarted(evt) {
    if (evt.track.kind !== 'audio') return;
    if (evt.participant.local) return;
    const pid = evt.participant.session_id;
    if (!audioElements[pid]) {
        const el = document.createElement('audio');
        el.autoplay = true;
        el.style.display = 'none';
        document.body.appendChild(el);
        audioElements[pid] = el;
    }
    const stream = new MediaStream([evt.track]);
    audioElements[pid].srcObject = stream;
    audioElements[pid].play().catch(() => {});
}

function onActiveSpeaker(evt) {
    const activePeer = evt?.activeSpeaker?.peerId;
    const localId    = call?.participants()?.local?.session_id;
    if (activePeer && activePeer !== localId) {
        setOrbState('speaking');
        orbLabel.textContent = 'Speaking';
    } else if (sessionActive) {
        setOrbState('listening');
        orbLabel.textContent = 'Listening';
    }
}

// ═══════════════════════════════════════════════
//  App messages from Pipecat bot
// ═══════════════════════════════════════════════
function onAppMessage(evt) {
    const data = evt?.data;
    if (!data?.type) return;

    switch (data.type) {
        case 'final_text':
            if (data.text && data.text !== lastFinalText) {
                clearPartial();
                addMsg('user', data.text);
                lastFinalText = data.text;
            }
            break;

        case 'partial_text':
            if (data.text) updatePartial(data.text);
            break;

        case 'processing':
            setOrbState('processing');
            orbLabel.textContent = 'Thinking';
            break;

        case 'assistant_response': {
            const r       = data.result || {};
            const ranking = (r.data && r.data.ranking) ? r.data.ranking : {};
            const text    = r.response || ranking.llm_response || r.message || '';
            const hotels  = r.hotels || ranking.ranked_hotels ||
                            (r.data && r.data.results) || [];

            if (text) addMsg('assistant', text);
            if (Array.isArray(hotels) && hotels.length) addHotels(hotels);

            if (sessionActive) {
                setOrbState('listening');
                orbLabel.textContent = 'Listening';
            }
            break;
        }

        case 'turn_end':
            lastFinalText = '';
            if (sessionActive) {
                setOrbState('listening');
                orbLabel.textContent = 'Listening';
            }
            break;

        case 'error':
            addMsg('system', data.message || 'Unknown error');
            if (sessionActive) {
                setOrbState('listening');
                orbLabel.textContent = 'Listening';
            }
            break;
    }
}

// ═══════════════════════════════════════════════
//  Orb button
// ═══════════════════════════════════════════════
function handleOrbClick() {
    if (!call || call.meetingState() !== 'joined-meeting') return;
    if (!sessionActive) startSession();
}

function startSession() {
    sessionActive = true;
    call.setLocalAudio(true);
    Object.entries(audioElements).forEach(([, el]) => {
        el.play().catch(() => {});
    });
    setOrbState('listening');
    orbLabel.textContent = 'Listening';
    endBtn.style.display = 'inline-block';
}

function endSession() {
    sessionActive = false;
    call.setLocalAudio(false);
    setOrbState('idle');
    orbLabel.textContent = 'Tap to speak';
    endBtn.style.display = 'none';
    lastFinalText = '';
}

// ═══════════════════════════════════════════════
//  Visual state helpers
// ═══════════════════════════════════════════════
const MIC_ICON = `<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
    <line x1="12" y1="19" x2="12" y2="23"/>
    <line x1="8" y1="23" x2="16" y2="23"/>`;

const SPIN_ICON = `<path d="M21 12a9 9 0 1 1-6.219-8.56"/>`;

function setOrbState(state) {
    orbBtn.dataset.state   = state;
    orbScene.dataset.state = state;
    orbLabel.dataset.state = state;

    const icon = document.getElementById('orbIcon');
    icon.innerHTML = (state === 'processing') ? SPIN_ICON : MIC_ICON;
}

function setStatus(type, text) {
    statusText.textContent = text;
    statusDot.className = 'status-dot' + (type === 'connected' ? ' connected' : type === 'error' ? ' error' : '');
}

// ═══════════════════════════════════════════════
//  Transcript
// ═══════════════════════════════════════════════
let partialEl = null;

function updatePartial(text) {
    if (!partialEl) {
        partialEl = document.createElement('div');
        partialEl.className = 'vmsg vmsg-user vmsg-partial';
        partialEl.innerHTML = `
            <div class="vmsg-avatar">You</div>
            <div class="vmsg-body">
                <div class="vmsg-role">You</div>
                <div class="vmsg-text"></div>
            </div>`;
        transcript.appendChild(partialEl);
    }
    partialEl.querySelector('.vmsg-text').textContent = text;
    transcript.scrollTop = transcript.scrollHeight;
}

function clearPartial() {
    if (partialEl) { partialEl.remove(); partialEl = null; }
}

function addMsg(role, text) {
    clearPartial();
    const el = document.createElement('div');
    el.className = `vmsg vmsg-${role}`;
    const avatar = role === 'user' ? 'You' : role === 'assistant' ? 'AI' : '!';
    const label  = role === 'user' ? 'You' : role === 'assistant' ? 'Scenery' : 'System';
    el.innerHTML = `
        <div class="vmsg-avatar">${avatar}</div>
        <div class="vmsg-body">
            <div class="vmsg-role">${label}</div>
            <div class="vmsg-text">${escHtml(text)}</div>
        </div>`;
    transcript.appendChild(el);
    transcript.scrollTop = transcript.scrollHeight;
}

function addHotels(hotels) {
    const el = document.createElement('div');
    el.className = 'vmsg vmsg-assistant';
    let cards = '<div class="v-hotels">';
    hotels.slice(0, 5).forEach(h => {
        const rating = h.rating ? `<span style="color:#d97706">&#9733;</span> ${h.rating}` : '';
        const loc    = h.location ? escHtml(h.location) : '';
        const meta   = [rating, loc].filter(Boolean).join(' &middot; ');
        cards += `
            <div class="v-hotel-card">
                <div>
                    <div class="v-hotel-name">${escHtml(h.name || 'Hotel')}</div>
                    ${meta ? `<div class="v-hotel-meta">${meta}</div>` : ''}
                </div>
                ${h.price ? `<div class="v-hotel-price">${escHtml(fmtPrice(h.price))}</div>` : ''}
            </div>`;
    });
    cards += '</div>';
    el.innerHTML = `
        <div class="vmsg-avatar">AI</div>
        <div class="vmsg-body">${cards}</div>`;
    transcript.appendChild(el);
    transcript.scrollTop = transcript.scrollHeight;
}

function clearTranscript() {
    transcript.innerHTML = `
        <div class="vmsg vmsg-assistant">
            <div class="vmsg-avatar">AI</div>
            <div class="vmsg-body">
                <div class="vmsg-role">Scenery</div>
                <div class="vmsg-text">Tap the microphone and ask me about hotels in Sri Lanka.</div>
            </div>
        </div>`;
}

// ═══════════════════════════════════════════════
//  Utils
// ═══════════════════════════════════════════════
function escHtml(t) {
    const d = document.createElement('div');
    d.textContent = String(t ?? '');
    return d.innerHTML;
}

function fmtPrice(p) {
    const s = String(p ?? '').trim();
    if (!s) return '';
    if (/(lkr|rs\.?|රු)/i.test(s)) return s;
    const n = Number(s.replace(/,/g, ''));
    return Number.isNaN(n) ? `LKR ${s}` : `LKR ${n.toLocaleString('en-US')}`;
}

function getSessionId() {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
        id = crypto.randomUUID ? crypto.randomUUID()
           : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        localStorage.setItem(SESSION_KEY, id);
    }
    return id;
}

window.addEventListener('beforeunload', () => {
    if (call) call.destroy().catch?.(() => {});
});
