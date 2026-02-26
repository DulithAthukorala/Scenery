// Configuration
const WS_URL = 'ws://localhost:8000/voice/stream';

let websocket = null;
let mediaRecorder = null;
let audioContext = null;
let isRecording = false;
let audioChunks = [];

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
        websocket = new WebSocket(WS_URL);
        
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
            micStatus.textContent = 'Disconnected';
            
            // Try to reconnect after 3 seconds
            setTimeout(() => {
                if (websocket.readyState === WebSocket.CLOSED) {
                    addTranscript('system', 'Attempting to reconnect...');
                    connectWebSocket();
                }
            }, 3000);
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
    
    switch (data.type) {
        case 'transcript':
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
            
        case 'audio':
            // Handle audio playback if implemented
            break;
            
        case 'error':
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
    if (isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
});

// Start recording
async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: true,
                noiseSuppression: true,
            } 
        });
        
        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        const source = audioContext.createMediaStreamSource(stream);
        
        // Simple recording using MediaRecorder
        const options = { mimeType: 'audio/webm' };
        mediaRecorder = new MediaRecorder(stream, options);
        
        audioChunks = [];
        
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
                
                // Send audio chunk to WebSocket
                if (websocket && websocket.readyState === WebSocket.OPEN) {
                    event.data.arrayBuffer().then(buffer => {
                        websocket.send(buffer);
                    });
                }
            }
        };
        
        mediaRecorder.onstop = () => {
            // Send end signal
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({ type: 'audio_end' }));
            }
        };
        
        mediaRecorder.start(100); // Collect data every 100ms
        isRecording = true;
        
        micButton.classList.add('recording');
        micStatus.textContent = '🔴 Recording... Click to stop';
        audioWaves.classList.add('active');
        
        console.log('Recording started');
        
    } catch (error) {
        console.error('Error starting recording:', error);
        addTranscript('system', '❌ Microphone access denied. Please allow microphone permissions.');
        micStatus.textContent = 'Microphone access denied';
    }
}

// Stop recording
function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }
    
    if (audioContext) {
        audioContext.close();
    }
    
    isRecording = false;
    micButton.classList.remove('recording');
    micStatus.textContent = 'Processing...';
    audioWaves.classList.remove('active');
    
    console.log('Recording stopped');
    
    setTimeout(() => {
        if (!isRecording) {
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
                ${hotel.price ? `<p class="hotel-price">💰 $${hotel.price}</p>` : ''}
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

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (websocket) {
        websocket.close();
    }
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
});
