// ═══════════════════════════════════════════════
//  Configuration
// ═══════════════════════════════════════════════
const WS_URL = 'ws://localhost:8000/voice/stream';
const SESSION_STORAGE_KEY = 'scenery_session_id';
const PING_INTERVAL_MS = 25000;   // keepalive ping every 25s
const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 10000]; // exponential backoff

// Debug logging that persists across page refreshes
const DEBUG_LOG_KEY = 'voice_debug_log';
function debugLog(msg) {
    try {
        const timestamp = new Date().toISOString().split('T')[1].slice(0, -1);
        const entry = `${timestamp} ${msg}`;
        console.log(entry);
        const logs = JSON.parse(localStorage.getItem(DEBUG_LOG_KEY) || '[]');
        logs.push(entry);
        // Keep last 100 entries (increased from 50)
        while (logs.length > 100) logs.shift();
        localStorage.setItem(DEBUG_LOG_KEY, JSON.stringify(logs));
    } catch(e) {
        // If localStorage fails, still log to console
        console.error('[DEBUG] localStorage error:', e);
    }
}
window.viewDebugLogs = function() {
    const logs = JSON.parse(localStorage.getItem(DEBUG_LOG_KEY) || '[]');
    console.log('===== DEBUG LOGS (last ' + logs.length + ' entries) =====');
    logs.forEach(log => console.log(log));
    console.log('===== END DEBUG LOGS =====');
};
window.clearDebugLogs = function() {
    localStorage.removeItem(DEBUG_LOG_KEY);
    console.log('Debug logs cleared');
};

// ═══════════════════════════════════════════════
//  State
// ═══════════════════════════════════════════════
let websocket = null;
let mediaStream = null;
let scriptProcessor = null;
let audioContext = null;
let isRecording = false;
let isProcessing = false;
let reconnectTimer = null;
let reconnectAttempt = 0;
let pingTimer = null;

// Track sent messages to prevent duplicates
let audioEndSent = false;
let lastFinalText = '';
let processingStartTime = 0;

// TTS
let ttsAudioChunks = [];
let isSpeaking = false;
let ttsAudioContext = null;

// Mode state (mirrors chat.js)
let currentMode = 'standard';
let livePricesPresets = null;
let livePricesResults = null;

// ═══════════════════════════════════════════════
//  DOM Elements
// ═══════════════════════════════════════════════
const micButton = document.getElementById('micButton');
const micStatus = document.getElementById('micStatus');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const transcript = document.getElementById('transcript');
const audioWaves = document.getElementById('audioWaves');

// ═══════════════════════════════════════════════
//  Initialization
// ═══════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
    debugLog('[INIT] Page loaded');
    
    // Track navigation/refresh attempts - TRY TO PREVENT THEM
    window.addEventListener('beforeunload', (e) => {
        debugLog('[NAV] beforeunload triggered');
    });
    
    // Catch any unhandled errors
    window.addEventListener('error', (e) => {
        debugLog('[ERROR] Unhandled error: ' + e.message + ' at ' + e.filename + ':' + e.lineno);
    });
    
    // Catch unhandled promise rejections
    window.addEventListener('unhandledrejection', (e) => {
        debugLog('[ERROR] Unhandled rejection: ' + e.reason);
    });
    
    // Track ALL navigation attempts
    window.addEventListener('pagehide', (e) => {
        debugLog('[NAV] pagehide - persisted: ' + e.persisted);
    });
    
    // Track keyboard events that might trigger navigation
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT')) {
            debugLog('[KEY] Preventing Enter on ' + e.target.tagName + ' id=' + e.target.id);
            e.preventDefault();
            return false;
        }
    });
    
    connectWebSocket();

    // Mode toggle handlers
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => handleModeToggle(btn));
    });

    // Live prices start search
    const startSearchBtn = document.getElementById('voiceStartSearchBtn');
    if (startSearchBtn) {
        startSearchBtn.addEventListener('click', handleStartSearch);
    }
});

// ═══════════════════════════════════════════════
//  WebSocket – persistent multi-turn connection
// ═══════════════════════════════════════════════
function connectWebSocket() {
    if (websocket && (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING)) {
        return; // already connected
    }

    try {
        const sessionId = getOrCreateSessionId();
        const wsUrl = `${WS_URL}?session_id=${encodeURIComponent(sessionId)}`;
        websocket = new WebSocket(wsUrl);

        websocket.onopen = () => {
            debugLog('[WS] Connected');
            reconnectAttempt = 0;
            startPing();
        };

        websocket.onmessage = (event) => {
            try {
                debugLog('[WS] onmessage START');
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
                debugLog('[WS] onmessage END - no errors');
            } catch (error) {
                debugLog('[WS] Error parsing message: ' + error + ' stack: ' + error.stack);
            }
        };

        websocket.onerror = (error) => {
            debugLog('[WS] Error: ' + error);
            updateStatus('error', 'Error');
        };

        websocket.onclose = (event) => {
            debugLog('[WS] Closed - code: ' + event.code + ', reason: ' + event.reason + ', wasClean: ' + event.wasClean + ', duringProcessing: ' + isProcessing);
            stopPing();
            updateStatus('disconnected', 'Disconnected');
            micButton.disabled = true;
            
            // Maintain processing state across reconnects
            if (isProcessing) {
                micStatus.textContent = 'Processing (reconnecting)...';
                debugLog('[WS] Disconnect during processing - maintaining state');
            } else {
                micStatus.textContent = 'Reconnecting...';
            }
            
            scheduleReconnect();
        };
    } catch (error) {
        debugLog('[WS] Error connecting: ' + error);
        updateStatus('error', 'Error');
        addTranscript('system', 'Failed to connect. Make sure backend is running on port 8000.');
    }
}

function scheduleReconnect() {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    const delay = RECONNECT_DELAYS[Math.min(reconnectAttempt, RECONNECT_DELAYS.length - 1)];
    reconnectAttempt++;
    console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempt})`);
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWebSocket();
    }, delay);
}

function startPing() {
    stopPing();
    pingTimer = setInterval(() => {
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            websocket.send(JSON.stringify({ type: 'ping' }));
        }
    }, PING_INTERVAL_MS);
}

function stopPing() {
    if (pingTimer) {
        clearInterval(pingTimer);
        pingTimer = null;
    }
}

// ═══════════════════════════════════════════════
//  WebSocket message handler
// ═══════════════════════════════════════════════
function handleWebSocketMessage(data) {
    debugLog('[WS] << ' + data.type + ' (len: ' + JSON.stringify(data).length + ', processing: ' + isProcessing + ', speaking: ' + isSpeaking + ')');

    const extractAssistantPayload = (result) => {
        const ranking = result?.data?.ranking || {};
        const text = result?.response || ranking.llm_response || result?.message || '';
        const hotels = result?.hotels || ranking.ranked_hotels || result?.data?.results || [];
        return { text, hotels: Array.isArray(hotels) ? hotels : [] };
    };

    switch (data.type) {
        // ── Connection lifecycle ──
        case 'ready':
            updateStatus('connected', 'Connected');
            debugLog('[WS] Ready - processing: ' + isProcessing);
            // Enable mic only if not in live_prices mode needing form
            updateMicState();
            if (!isProcessing) {
                micStatus.textContent = 'Click to speak';
            }
            break;

        case 'pong':
            break; // keepalive ack

        case 'turn_ready':
            // Server acknowledged turn_start – safe to stream audio
            break;

        // ── STT events ──
        case 'partial_text':
            if (data.text) {
                updatePartialTranscript(data.text);
            }
            break;

        case 'final_text':
            if (data.text) {
                // Deduplicate - prevent adding same text twice
                if (data.text !== lastFinalText) {
                    console.log('[Transcript] User:', data.text);
                    clearPartialTranscript();
                    addTranscript('user', data.text);
                    lastFinalText = data.text;
                } else {
                    console.warn('[Transcript] Duplicate final_text ignored:', data.text);
                }
            }
            break;

        // ── Assistant response ──
        case 'assistant_response': {
            isProcessing = false;
            const payload = extractAssistantPayload(data.result || {});
            if (payload.text) {
                addTranscript('assistant', payload.text);
            }
            if (payload.hotels.length > 0) {
                // Store for re-ranking in live prices mode
                if (currentMode === 'live_prices') {
                    livePricesResults = payload.hotels;
                }
                addHotelsToTranscript(payload.hotels);
            }
            if (data.meta) {
                console.log('voice_timing', data.meta);
            }
            break;
        }

        case 'processing':
            debugLog('[STATE] Processing started');
            isProcessing = true;
            processingStartTime = Date.now();
            micStatus.textContent = 'Processing...';
            debugLog('[STATE] Processing case complete - no errors');
            break;

        // ── TTS events ──
        case 'tts_start':
            console.log('TTS: Starting');
            ttsAudioChunks = [];
            isSpeaking = true;
            micButton.classList.add('speaking');
            micStatus.textContent = '🔊 Assistant speaking...';
            audioWaves.classList.add('active');
            break;

        case 'tts_audio':
            if (data.audio) {
                const audio = data.audio;
                debugLog('[TTS] Received chunk ' + (ttsAudioChunks.length + 1) + ' - type: ' + typeof audio + ', sample: ' + JSON.stringify(audio).substring(0, 100));
                ttsAudioChunks.push(audio);
            }
            break;

        case 'tts_end':
            console.log('[TTS] End signal received - chunks:', ttsAudioChunks.length);
            if (ttsAudioChunks.length > 0) {
                playTTSAudio();
            } else {
                console.warn('[TTS] No audio chunks received - skipping playback');
                resetSpeakingState();
            }
            break;

        case 'tts_error':
            console.error('[TTS] Error:', data.error);
            if (data.error && data.error.includes('payment_required')) {
                addTranscript('system', '⚠️ TTS quota exhausted. Voice responses are text-only.');
            } else {
                addTranscript('system', `Audio playback error: ${data.error}`);
            }
            resetSpeakingState();
            break;

        // ── Turn lifecycle ──
        case 'turn_end':
            const duration = processingStartTime ? ((Date.now() - processingStartTime) / 1000).toFixed(1) : '?';
            console.log('[STATE] Turn ended - duration:', duration + 's');
            isProcessing = false;
            processingStartTime = 0;
            audioEndSent = false;  // Reset for next turn
            lastFinalText = '';    // Reset for next turn
            if (!isSpeaking) {
                micStatus.textContent = 'Click to speak';
                updateMicState();
            }
            break;

        // ── Errors ──
        case 'error':
            isProcessing = false;
            const errMsg = data.message || 'Unknown error';
            debugLog('[Server] Error: ' + data.code + ' - ' + errMsg);
            addTranscript('system', errMsg);
            resetSpeakingState();
            updateMicState();
            break;

        default:
            console.log('Unknown message type:', data);
    }
    debugLog('[WS] handleWebSocketMessage complete - type was: ' + data.type);
}

// ═══════════════════════════════════════════════
//  Mode Toggle (Standard / Live Prices)
// ═══════════════════════════════════════════════
function handleModeToggle(button) {
    const mode = button.dataset.mode;
    currentMode = mode;

    document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
    button.classList.add('active');

    const livePricesForm = document.getElementById('livePricesForm');
    const searchInfo = document.getElementById('voiceSearchInfo');

    if (mode === 'live_prices') {
        livePricesForm.style.display = 'block';
        livePricesPresets = null;
        livePricesResults = null;
        searchInfo.style.display = 'none';
        micButton.disabled = true;
        micStatus.textContent = 'Fill in search details above';
    } else {
        livePricesForm.style.display = 'none';
        livePricesPresets = null;
        livePricesResults = null;
        searchInfo.style.display = 'none';
        updateMicState();
        micStatus.textContent = 'Click to speak';
    }
}

// ═══════════════════════════════════════════════
//  Live Prices Form Search
// ═══════════════════════════════════════════════
function handleStartSearch() {
    const city = document.getElementById('voiceCitySelect').value;
    const checkIn = document.getElementById('voiceCheckInDate').value;
    const checkOut = document.getElementById('voiceCheckOutDate').value;
    const preferences = document.getElementById('voicePreferencesInput').value.trim();

    if (!city || !checkIn || !checkOut) {
        alert('Please select a city, check-in date, and check-out date.');
        return;
    }

    livePricesPresets = {
        location: city,
        dates: { check_in: checkIn, check_out: checkOut }
    };

    const btn = document.getElementById('voiceStartSearchBtn');
    btn.disabled = true;
    btn.textContent = 'Searching...';
    isProcessing = true;
    micStatus.textContent = 'Searching for hotels...';

    const query = preferences || `Show me hotels in ${city}`;

    // Send form_search message over WebSocket (no audio needed)
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            type: 'form_search',
            force_mode: 'live_prices',
            preset_location: city,
            preset_dates: { check_in: checkIn, check_out: checkOut },
            query: query,
        }));
    } else {
        addTranscript('system', 'Not connected. Please wait for reconnection.');
        btn.disabled = false;
        btn.textContent = 'Start Search';
        isProcessing = false;
        return;
    }

    // Wait for turn_end to finalize UI
    const origHandler = handleWebSocketMessage;
    const onceHandler = (rawData) => {
        // We intercept turn_end to finalize the form
        if (rawData.type === 'turn_end') {
            // Hide form, show search info
            document.getElementById('livePricesForm').style.display = 'none';
            const searchInfo = document.getElementById('voiceSearchInfo');
            searchInfo.innerHTML = `<strong>Active Search:</strong> ${city} | ${checkIn} to ${checkOut} <button type="button" onclick="resetLivePricesSearch()" class="voice-new-search-btn">New Search</button>`;
            searchInfo.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Start Search';
            micButton.disabled = false;
            micStatus.textContent = 'Speak to re-rank hotels';
        }
    };

    // Temporarily augment the message handler
    const _origOnMessage = websocket.onmessage;
    websocket.onmessage = (event) => {
        try {
            debugLog('[WS-AUGMENTED] onmessage START');
            const d = JSON.parse(event.data);
            handleWebSocketMessage(d);
            onceHandler(d);
            debugLog('[WS-AUGMENTED] onmessage END');
        } catch (e) {
            debugLog('[WS-AUGMENTED] Error: ' + e + ' stack: ' + e.stack);
        }
    };

    // Restore after timeout safety
    setTimeout(() => {
        if (websocket) {
            websocket.onmessage = _origOnMessage;
            debugLog('[WS-AUGMENTED] Handler restored after timeout');
        }
        btn.disabled = false;
        btn.textContent = 'Start Search';
    }, 30000);
}

function resetLivePricesSearch() {
    livePricesResults = null;
    livePricesPresets = null;

    document.getElementById('livePricesForm').style.display = 'block';
    document.getElementById('voiceSearchInfo').style.display = 'none';
    micButton.disabled = true;
    micStatus.textContent = 'Fill in search details above';

    document.getElementById('voiceCitySelect').value = '';
    document.getElementById('voiceCheckInDate').value = '';
    document.getElementById('voiceCheckOutDate').value = '';
    document.getElementById('voicePreferencesInput').value = '';
}

// ═══════════════════════════════════════════════
//  Mic state helper
// ═══════════════════════════════════════════════
function updateMicState() {
    if (currentMode === 'live_prices' && !livePricesPresets) {
        micButton.disabled = true;
        return;
    }
    // Enable mic only when WS is open and not processing/speaking
    const wsReady = websocket && websocket.readyState === WebSocket.OPEN;
    micButton.disabled = !wsReady || isProcessing || isSpeaking;
}

// ═══════════════════════════════════════════════
//  Status indicator
// ═══════════════════════════════════════════════
function updateStatus(status, text) {
    statusText.textContent = text;
    statusDot.className = 'status-dot';
    if (status === 'connected') {
        statusDot.style.background = 'var(--success-gradient)';
    } else if (status === 'error') {
        statusDot.style.background = 'var(--secondary-gradient)';
    } else {
        statusDot.style.background = 'var(--text-tertiary)';
    }
}

// ═══════════════════════════════════════════════
//  Recording
// ═══════════════════════════════════════════════
micButton.addEventListener('click', async (e) => {
    debugLog('[MIC] Button clicked - isRecording:' + isRecording + ' isSpeaking:' + isSpeaking + ' type:' + e.target.type);
    e.preventDefault(); // Explicitly prevent any default behavior
    e.stopPropagation(); // Stop event bubbling
    
    if (isSpeaking) {
        debugLog('[MIC] Ignoring click - speaking');
        return;
    }
    if (isRecording) {
        debugLog('[MIC] Stopping recording');
        stopRecording();
    } else {
        debugLog('[MIC] Starting recording');
        try {
            await startRecording();
        } catch (err) {
            debugLog('[MIC] startRecording error: ' + err.message);
            addTranscript('system', `Error starting recording: ${err.message}`);
        }
    }
});

async function startRecording() {
    debugLog('[Recording] startRecording called');
    if (!websocket || websocket.readyState !== WebSocket.OPEN) {
        debugLog('[Recording] Cannot start - not connected');
        addTranscript('system', 'Not connected to server. Please wait...');
        return;
    }
    
    debugLog('[Recording] Getting media stream...');
    audioEndSent = false;  // Reset for new turn

    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true }
        });

        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        const source = audioContext.createMediaStreamSource(mediaStream);
        scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
        source.connect(scriptProcessor);
        scriptProcessor.connect(audioContext.destination);

        // Send turn_start with mode context before audio
        debugLog('[WS] >> turn_start - mode: ' + currentMode);
        const turnStartMsg = { type: 'turn_start', force_mode: currentMode };
        if (currentMode === 'live_prices' && livePricesResults && livePricesResults.length > 0) {
            turnStartMsg.rerank_hotels = livePricesResults;
            if (livePricesPresets) {
                turnStartMsg.preset_location = livePricesPresets.location;
                turnStartMsg.preset_dates = livePricesPresets.dates;
            }
        }
        websocket.send(JSON.stringify(turnStartMsg));

        scriptProcessor.onaudioprocess = (e) => {
            if (!isRecording) return;
            const float32 = e.inputBuffer.getChannelData(0);
            const pcm16 = new Int16Array(float32.length);
            for (let i = 0; i < float32.length; i++) {
                const s = Math.max(-1, Math.min(1, float32[i]));
                pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(pcm16.buffer);
            }
        };

        isRecording = true;
        micButton.classList.add('recording');
        micStatus.textContent = '🔴 Recording... Click to stop';
        audioWaves.classList.add('active');
    } catch (error) {
        debugLog('[Recording] Error starting: ' + error);
        addTranscript('system', 'Microphone access denied. Please allow microphone permissions.');
        micStatus.textContent = 'Microphone access denied';
    }
}

function stopRecording() {
    debugLog('[Recording] Stopping...');
    isRecording = false;
    isProcessing = true;

    if (scriptProcessor) { scriptProcessor.disconnect(); scriptProcessor = null; }
    if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
    if (audioContext && audioContext.state !== 'closed') { 
        audioContext.close().catch(e => debugLog('[Audio] Context close error: ' + e)); 
        audioContext = null; 
    }

    // Signal end of audio (prevent double-send)
    if (!audioEndSent && websocket && websocket.readyState === WebSocket.OPEN) {
        debugLog('[WS] >> audio_end');
        websocket.send(JSON.stringify({ type: 'audio_end' }));
        audioEndSent = true;
    } else if (audioEndSent) {
        debugLog('[WS] audio_end already sent - skipping');
    } else {
        debugLog('[WS] Cannot send audio_end - not connected');
    }

    micButton.classList.remove('recording');
    micButton.disabled = true;
    micStatus.textContent = 'Processing...';
    audioWaves.classList.remove('active');
    debugLog('[Recording] Stop complete');
}

// ═══════════════════════════════════════════════
//  Transcript
// ═══════════════════════════════════════════════
let partialDiv = null;

function updatePartialTranscript(text) {
    if (!partialDiv) {
        partialDiv = document.createElement('div');
        partialDiv.className = 'transcript-message user partial';
        partialDiv.innerHTML = `<strong>You:</strong> <span class="partial-text"></span>`;
        transcript.appendChild(partialDiv);
    }
    partialDiv.querySelector('.partial-text').textContent = text;
    transcript.scrollTop = transcript.scrollHeight;
}

function clearPartialTranscript() {
    if (partialDiv) {
        partialDiv.remove();
        partialDiv = null;
    }
}

function addTranscript(role, text) {
    clearPartialTranscript();
    const messageDiv = document.createElement('div');
    messageDiv.className = `transcript-message ${role}`;
    let label = role === 'user' ? 'You' : role === 'assistant' ? 'Assistant' : 'System';
    messageDiv.innerHTML = `<strong>${label}:</strong> ${escapeHtml(text)}`;
    transcript.appendChild(messageDiv);
    transcript.scrollTop = transcript.scrollHeight;
}

function addHotelsToTranscript(hotels) {
    const hotelsDiv = document.createElement('div');
    hotelsDiv.className = 'transcript-hotels';

    let html = '<div class="hotels-response"><div class="hotels-grid">';
    hotels.slice(0, 6).forEach(hotel => {
        html += `
            <div class="hotel-card glass-morphism">
                <div class="hotel-header">
                    <h4 class="hotel-name">${escapeHtml(hotel.name || 'Unnamed Hotel')}</h4>
                    ${hotel.rating ? `<span class="hotel-rating">⭐ ${hotel.rating}</span>` : ''}
                </div>
                ${hotel.location ? `<p class="hotel-location">📍 ${escapeHtml(hotel.location)}</p>` : ''}
                ${hotel.price ? `<p class="hotel-price">💰 ${escapeHtml(formatPriceLkr(hotel.price))}</p>` : ''}
                ${hotel.description ? `<p class="hotel-description">${escapeHtml(hotel.description)}</p>` : ''}
            </div>`;
    });
    html += '</div></div>';

    hotelsDiv.innerHTML = html;
    transcript.appendChild(hotelsDiv);
    transcript.scrollTop = transcript.scrollHeight;
}

function clearTranscript() {
    transcript.innerHTML = `
        <div class="transcript-message assistant">
            <strong>Assistant:</strong> Hi! Click the microphone and speak to start searching for hotels.
        </div>`;
}

// ═══════════════════════════════════════════════
//  TTS Audio Playback
// ═══════════════════════════════════════════════
async function playTTSAudio() {
    if (ttsAudioChunks.length === 0) {
        debugLog('[TTS] No audio chunks to play');
        resetSpeakingState();
        return;
    }

    try {
        debugLog('[TTS] Playing ' + ttsAudioChunks.length + ' chunks');
        debugLog('[TTS] Processing ' + ttsAudioChunks.length + ' chunks');
        
        // Decode each chunk individually to bytes, then concatenate
        // This avoids base64 alignment issues from concatenating encoded strings
        const allByteArrays = [];
        let totalBytes = 0;
        
        for (let i = 0; i < ttsAudioChunks.length; i++) {
            try {
                const chunk = ttsAudioChunks[i];
                const binaryString = atob(chunk);
                const chunkBytes = new Uint8Array(binaryString.length);
                for (let j = 0; j < binaryString.length; j++) {
                    chunkBytes[j] = binaryString.charCodeAt(j);
                }
                allByteArrays.push(chunkBytes);
                totalBytes += chunkBytes.length;
            } catch (err) {
                debugLog('[TTS] Failed to decode chunk ' + (i + 1) + ': ' + err.message);
                throw new Error('Chunk ' + (i + 1) + ' decode failed: ' + err.message);
            }
        }
        
        debugLog('[TTS] Decoded ' + ttsAudioChunks.length + ' chunks -> ' + totalBytes + ' total bytes');
        
        // Concatenate all byte arrays into one
        const bytes = new Uint8Array(totalBytes);
        let offset = 0;
        for (let i = 0; i < allByteArrays.length; i++) {
            bytes.set(allByteArrays[i], offset);
            offset += allByteArrays[i].length;
        }
        debugLog('[TTS] Decoded ' + bytes.length + ' bytes');
        
        if (bytes.length === 0) {
            throw new Error('No audio data after decoding');
        }

        // Use a dedicated audio context for TTS playback (don't reuse recording context)
        // Don't force 16kHz - let browser use native rate and it will resample automatically
        if (!ttsAudioContext || ttsAudioContext.state === 'closed') {
            ttsAudioContext = new (window.AudioContext || window.webkitAudioContext)();
            debugLog('[TTS] Created new AudioContext at native rate: ' + ttsAudioContext.sampleRate + 'Hz');
        }
        
        // Resume audio context (required by Chrome's autoplay policy)
        if (ttsAudioContext.state === 'suspended') {
            await ttsAudioContext.resume();
            debugLog('[TTS] Resumed AudioContext');
        }

        // Decode PCM at 16kHz - browser will auto-resample to context rate
        const audioBuffer = decodePCMAudio(bytes.buffer, 16000);
        debugLog('[TTS] AudioBuffer: ' + audioBuffer.duration.toFixed(2) + 's, buffer@' + audioBuffer.sampleRate + 'Hz, context@' + ttsAudioContext.sampleRate + 'Hz');
        
        const source = ttsAudioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ttsAudioContext.destination);
        source.onended = () => {
            debugLog('[TTS] Playback finished');
            resetSpeakingState();
        };
        source.start(0);
        debugLog('[TTS] Playback started - browser will auto-resample if needed');
    } catch (error) {
        debugLog('[TTS] Playback error: ' + error.message);
        debugLog('[TTS] Error stack: ' + error.stack);
        addTranscript('system', 'Audio playback failed - check console logs');
        resetSpeakingState();
    }
}

function decodePCMAudio(arrayBuffer, sampleRate) {
    debugLog('[PCM] Input: ' + arrayBuffer.byteLength + ' bytes');
    
    // PCM16 MUST have even byte length (2 bytes per sample)
    if (arrayBuffer.byteLength % 2 !== 0) {
        debugLog('[PCM] Odd byte length - trimming last byte');
        arrayBuffer = arrayBuffer.slice(0, arrayBuffer.byteLength - 1);
    }
    
    const dataView = new DataView(arrayBuffer);
    const numSamples = arrayBuffer.byteLength / 2;
    
    debugLog('[PCM] Decoding ' + numSamples + ' samples at ' + sampleRate + 'Hz');
    
    // Create buffer at SOURCE sample rate - browser will auto-resample during playback
    const audioBuffer = ttsAudioContext.createBuffer(1, numSamples, sampleRate);
    const channelData = audioBuffer.getChannelData(0);
    
    // Decode PCM16 to Float32 [-1.0, 1.0]
    for (let i = 0; i < numSamples; i++) {
        channelData[i] = dataView.getInt16(i * 2, true) / 32768.0;
    }
    
    debugLog('[PCM] Decode complete - ' + audioBuffer.duration.toFixed(2) + 's');
    return audioBuffer;
}

function resetSpeakingState() {
    isSpeaking = false;
    isProcessing = false;
    micButton.classList.remove('speaking');
    audioWaves.classList.remove('active');
    micStatus.textContent = 'Click to speak';
    ttsAudioChunks = [];
    updateMicState();
}

// ═══════════════════════════════════════════════
//  Utilities
// ═══════════════════════════════════════════════
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatPriceLkr(price) {
    const raw = String(price ?? '').trim();
    if (!raw) return '';
    if (/(lkr|rs\.?|රු)/i.test(raw)) return raw;
    const numeric = Number(raw.replace(/,/g, ''));
    if (!Number.isNaN(numeric)) return `LKR ${numeric.toLocaleString('en-US')}`;
    return `LKR ${raw}`;
}

function getOrCreateSessionId() {
    const existing = localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const generated = (window.crypto && typeof window.crypto.randomUUID === 'function')
        ? window.crypto.randomUUID()
        : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(SESSION_STORAGE_KEY, generated);
    return generated;
}

// ═══════════════════════════════════════════════
//  Cleanup
// ═══════════════════════════════════════════════
window.addEventListener('beforeunload', () => {
    stopPing();
    if (websocket) websocket.close();
    if (scriptProcessor) scriptProcessor.disconnect();
    if (mediaStream) mediaStream.getTracks().forEach(t => t.stop());
    if (audioContext && audioContext.state !== 'closed') audioContext.close();
    if (ttsAudioContext && ttsAudioContext.state !== 'closed') ttsAudioContext.close();
});
