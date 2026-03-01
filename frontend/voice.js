// Configuration
const WS_URL = 'ws://localhost:8000/voice/stream';
const SESSION_STORAGE_KEY = 'scenery_session_id';

let websocket = null;
let mediaStream = null;
let scriptProcessor = null;
let audioContext = null;
let isRecording = false;
let reconnectTimer = null;
let isProcessing = false;

// TTS Audio handling
let ttsAudioChunks = [];
let isSpeaking = false;

// DOM Elements
const micButton = document.getElementById('micButton');
const micStatus = document.getElementById('micStatus');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const transcript = document.getElementById('transcript');
const audioWaves = document.getElementById('audioWaves');

// Initialize WebSocket connection
function connectWebSocket() {
    try {
        const sessionId = getOrCreateSessionId();
        const wsUrl = `${WS_URL}?session_id=${encodeURIComponent(sessionId)}`;
        websocket = new WebSocket(wsUrl);
        
        websocket.onopen = () => {
            console.log('WebSocket connected');
            updateStatus('connected', 'Connected');
            micButton.disabled = false;
            micStatus.textContent = 'Click to speak';
        };
        
        websocket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            updateStatus('error', 'Error');
            addTranscript('system', '❌ Connection error. Please check if backend is running.');
        };
        
        websocket.onclose = () => {
            console.log('WebSocket closed');
            updateStatus('disconnected', 'Disconnected');
            micButton.disabled = true;
            micStatus.textContent = 'Reconnecting...';
            
            // Clear any existing reconnect timer to prevent stacking
            if (reconnectTimer) {
                clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
            
            // Reconnect faster if we were waiting for a response
            const delay = isProcessing ? 500 : 3000;
            reconnectTimer = setTimeout(() => {
                reconnectTimer = null;
                connectWebSocket();
            }, delay);
        };
    } catch (error) {
        console.error('Error connecting to WebSocket:', error);
        updateStatus('error', 'Error');
        addTranscript('system', '❌ Failed to connect. Make sure backend is running on port 8000.');
    }
}

// Handle WebSocket messages
function handleWebSocketMessage(data) {
    console.log('Received:', data);

    const extractAssistantPayload = (result) => {
        const ranking = result?.data?.ranking || {};
        const text = result?.response || ranking.llm_response || result?.message || '';
        const hotels = result?.hotels || ranking.ranked_hotels || result?.data?.results || [];
        return {
            text,
            hotels: Array.isArray(hotels) ? hotels : []
        };
    };
    
    switch (data.type) {
        case 'transcript':
        case 'final_text':
            if (data.text) {
                addTranscript('user', data.text);
            }
            break;
            
        case 'response':
            if (data.text) {
                addTranscript('assistant', data.text);
            }
            if (data.hotels && data.hotels.length > 0) {
                addHotelsToTranscript(data.hotels);
            }
            break;

        case 'assistant_response': {
            isProcessing = false;
            const payload = extractAssistantPayload(data.result || {});
            if (payload.text) {
                addTranscript('assistant', payload.text);
            }
            if (payload.hotels.length > 0) {
                addHotelsToTranscript(payload.hotels);
            }
            if (data.meta) {
                console.log('voice_timing', data.meta);
            }
            break;
        }
            
        case 'tts_start':
            console.log('TTS: Starting audio synthesis');
            ttsAudioChunks = [];
            isSpeaking = true;
            micButton.classList.add('speaking');
            micStatus.textContent = '🔊 Assistant speaking...';
            audioWaves.classList.add('active');
            break;

        case 'tts_audio':
            if (data.audio) {
                ttsAudioChunks.push(data.audio);
            }
            break;

        case 'tts_end':
            console.log('TTS: Audio synthesis complete, playing...');
            playTTSAudio();
            break;

        case 'tts_error':
            console.error('TTS Error:', data.error);
            addTranscript('system', `🔇 Audio playback error: ${data.error}`);
            resetSpeakingState();
            break;
            
        case 'audio':
            // Handle audio playback if implemented (legacy)
            break;
            
        case 'error':
            isProcessing = false;
            addTranscript('system', `❌ Error: ${data.message}`);
            break;
            
        case 'server_debug':
            console.log('Server debug:', data.message);
            break;
            
        default:
            console.log('Unknown message type:', data);
    }
}

// Update status indicator
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

// Mic button click handler
micButton.addEventListener('click', async () => {
    // Prevent interaction while assistant is speaking
    if (isSpeaking) {
        console.log('Cannot record while assistant is speaking');
        return;
    }
    
    if (isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
});

// Start recording – capture raw PCM 16-bit 16 kHz audio for ElevenLabs STT
async function startRecording() {
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: true,
                noiseSuppression: true,
            }
        });

        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        console.log('AudioContext actual sampleRate:', audioContext.sampleRate);

        const source = audioContext.createMediaStreamSource(mediaStream);

        // ScriptProcessorNode captures raw PCM frames we can send directly
        scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
        source.connect(scriptProcessor);
        scriptProcessor.connect(audioContext.destination); // required for processing to run

        scriptProcessor.onaudioprocess = (e) => {
            if (!isRecording) return;
            const float32 = e.inputBuffer.getChannelData(0);

            // Convert float32 (-1..1) → signed 16-bit PCM
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

        console.log('Recording started (raw PCM 16 kHz)');

    } catch (error) {
        console.error('Error starting recording:', error);
        addTranscript('system', '❌ Microphone access denied. Please allow microphone permissions.');
        micStatus.textContent = 'Microphone access denied';
    }
}

// Stop recording
function stopRecording() {
    isRecording = false;
    isProcessing = true;

    if (scriptProcessor) {
        scriptProcessor.disconnect();
        scriptProcessor = null;
    }

    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }

    if (audioContext && audioContext.state !== 'closed') {
        audioContext.close();
        audioContext = null;
    }

    // Tell the backend there is no more audio
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({ type: 'audio_end' }));
    }

    micButton.classList.remove('recording');
    micStatus.textContent = 'Processing...';
    audioWaves.classList.remove('active');

    console.log('Recording stopped');

    setTimeout(() => {
        if (!isRecording && !isSpeaking) {
            micStatus.textContent = 'Click to speak';
        }
    }, 2000);
}

// Add message to transcript
function addTranscript(role, text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `transcript-message ${role}`;
    
    let label = role;
    if (role === 'user') label = 'You';
    else if (role === 'assistant') label = 'Assistant';
    else if (role === 'system') label = 'System';
    
    messageDiv.innerHTML = `<strong>${label}:</strong> ${escapeHtml(text)}`;
    transcript.appendChild(messageDiv);
    transcript.scrollTop = transcript.scrollHeight;
}

// Add hotels to transcript
function addHotelsToTranscript(hotels) {
    const hotelsDiv = document.createElement('div');
    hotelsDiv.className = 'transcript-hotels';
    
    let hotelsHTML = '<div class="hotels-grid">';
    hotels.slice(0, 6).forEach(hotel => {
        hotelsHTML += `
            <div class="hotel-card glass-morphism">
                <div class="hotel-header">
                    <h4 class="hotel-name">${escapeHtml(hotel.name || 'Unnamed Hotel')}</h4>
                    ${hotel.rating ? `<span class="hotel-rating">⭐ ${hotel.rating}</span>` : ''}
                </div>
                ${hotel.location ? `<p class="hotel-location">📍 ${escapeHtml(hotel.location)}</p>` : ''}
                ${hotel.price ? `<p class="hotel-price">💰 ${escapeHtml(formatPriceLkr(hotel.price))}</p>` : ''}
            </div>
        `;
    });
    hotelsHTML += '</div>';
    
    hotelsDiv.innerHTML = hotelsHTML;
    transcript.appendChild(hotelsDiv);
    transcript.scrollTop = transcript.scrollHeight;
}

// Clear transcript
function clearTranscript() {
    transcript.innerHTML = `
        <div class="transcript-message assistant">
            <strong>Assistant:</strong> Hi! Click the microphone and speak to start searching for hotels.
        </div>
    `;
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatPriceLkr(price) {
    const raw = String(price ?? '').trim();
    if (!raw) return '';

    if (/(lkr|rs\.?|රු)/i.test(raw)) {
        return raw;
    }

    const numeric = Number(raw.replace(/,/g, ''));
    if (!Number.isNaN(numeric)) {
        return `LKR ${numeric.toLocaleString('en-US')}`;
    }

    return `LKR ${raw}`;
}

function getOrCreateSessionId() {
    const existing = localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) {
        return existing;
    }

    const generated = (window.crypto && typeof window.crypto.randomUUID === 'function')
        ? window.crypto.randomUUID()
        : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;

    localStorage.setItem(SESSION_STORAGE_KEY, generated);
    return generated;
}

// TTS Audio Playback Functions
async function playTTSAudio() {
    if (ttsAudioChunks.length === 0) {
        console.warn('No TTS audio chunks to play');
        resetSpeakingState();
        return;
    }

    try {
        // Combine all base64 chunks into one string
        const combinedBase64 = ttsAudioChunks.join('');
        
        // Decode base64 to binary
        const binaryString = atob(combinedBase64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        // Create audio context if not exists or closed
        if (!audioContext || audioContext.state === 'closed') {
            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        }

        // Decode PCM audio (16kHz, 16-bit)
        const audioBuffer = await decodePCMAudio(bytes.buffer, 16000);
        
        // Create buffer source and play
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        
        source.onended = () => {
            console.log('TTS playback finished');
            resetSpeakingState();
        };
        
        source.start(0);
        console.log(`Playing TTS audio: ${bytes.length} bytes, duration: ${audioBuffer.duration.toFixed(2)}s`);
        
    } catch (error) {
        console.error('Error playing TTS audio:', error);
        addTranscript('system', '🔇 Failed to play audio response');
        resetSpeakingState();
    }
}

async function decodePCMAudio(arrayBuffer, sampleRate) {
    // PCM is 16-bit little-endian
    const dataView = new DataView(arrayBuffer);
    const numSamples = arrayBuffer.byteLength / 2; // 16-bit = 2 bytes per sample
    
    // Create AudioBuffer
    const audioBuffer = audioContext.createBuffer(1, numSamples, sampleRate);
    const channelData = audioBuffer.getChannelData(0);
    
    // Convert 16-bit PCM to float32 (-1.0 to 1.0)
    for (let i = 0; i < numSamples; i++) {
        const int16 = dataView.getInt16(i * 2, true); // true = little-endian
        channelData[i] = int16 / 32768.0; // Normalize to -1.0 to 1.0
    }
    
    return audioBuffer;
}

function resetSpeakingState() {
    isSpeaking = false;
    isProcessing = false;
    micButton.classList.remove('speaking');
    audioWaves.classList.remove('active');
    micStatus.textContent = 'Click to speak';
    ttsAudioChunks = [];
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (websocket) {
        websocket.close();
    }
    if (scriptProcessor) {
        scriptProcessor.disconnect();
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
    }
    if (audioContext && audioContext.state !== 'closed') {
        audioContext.close();
    }
});
