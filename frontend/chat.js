// Configuration
const API_BASE_URL = 'http://localhost:8000';
const SESSION_STORAGE_KEY = 'scenery_session_id';
const MESSAGES_STORAGE_KEY = 'scenery_chat_messages';

// Mode state
let currentMode = 'standard';
let livePricesPresets = null;
let livePricesResults = null; // Store initial RapidAPI results for re-ranking

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const initialTime = document.getElementById('initialTime');
    if (initialTime) {
        initialTime.textContent = getCurrentTime();
    }
    
    // Restore messages from sessionStorage
    restoreMessages();
    
    // Mode toggle handlers
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => handleModeToggle(btn));
    });
    
    // Start search button
    const startSearchBtn = document.getElementById('startSearchBtn');
    if (startSearchBtn) {
        startSearchBtn.addEventListener('click', handleStartSearch);
    }
    
    // Handle form submission
    const chatForm = document.getElementById('chatForm');
    if (chatForm) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const input = document.getElementById('chatInput');
            const sendButton = document.getElementById('sendButton');
            const message = input.value.trim();
            
            // Prevent double submission and validate message
            if (!message || input.disabled || sendButton.disabled) return;
            
            // Hide suggested queries after first message
            const suggestedQueries = document.getElementById('suggestedQueries');
            if (suggestedQueries) {
                suggestedQueries.style.display = 'none';
            }
            
            // Disable input immediately to prevent race condition
            input.disabled = true;
            sendButton.disabled = true;
            
            // Add user message and clear input
            addMessage('user', message);
            input.value = '';
            showTypingIndicator();

            // Validate/create session ID
            let sessionId = getOrCreateSessionId();
            if (!sessionId) {
                console.warn('Session ID invalid, regenerating...');
                localStorage.removeItem(SESSION_STORAGE_KEY);
                sessionId = getOrCreateSessionId();
            }
            
            try {
                const requestBody = { 
                    query: message, 
                    mode: 'text', 
                    session_id: sessionId,
                    force_mode: currentMode
                };
                
                // If in live prices mode with existing results, send for re-ranking only (no new RapidAPI call)
                if (currentMode === 'live_prices' && livePricesResults && livePricesResults.length > 0) {
                    requestBody.rerank_hotels = livePricesResults;
                    requestBody.preset_location = livePricesPresets.location;
                    requestBody.preset_dates = livePricesPresets.dates;
                }
                // If in live prices mode but no results yet (shouldn't happen), include presets
                else if (currentMode === 'live_prices' && livePricesPresets) {
                    requestBody.preset_location = livePricesPresets.location;
                    requestBody.preset_dates = livePricesPresets.dates;
                }
                
                const response = await fetch(`${API_BASE_URL}/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();

                // Save session ID from response
                if (data.session_id) {
                    localStorage.setItem(SESSION_STORAGE_KEY, data.session_id);
                }
                
                removeTypingIndicator();
                
                const content = (data.response || '').trim() || 'I could not generate a response right now. Please try again.';
                const assistantData = Array.isArray(data.hotels) ? { hotels: data.hotels } : null;
                addMessage('assistant', content, assistantData);
                
            } catch (error) {
                removeTypingIndicator();
                addMessage('assistant', `Sorry, I encountered an error: ${error.message}. Please make sure the backend is running on port 8000!`, null, true);
            } finally {
                input.disabled = false;
                sendButton.disabled = false;
                input.focus();
            }
        });
    }
});

// Get current time
function getCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Set suggestion
function setSuggestion(button) {
    const input = document.getElementById('chatInput');
    input.value = button.textContent.trim();
    input.focus();
}

// Handle mode toggle
function handleModeToggle(button) {
    const mode = button.dataset.mode;
    currentMode = mode;
    
    // Update button states
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    button.classList.add('active');
    
    // Show/hide live prices form
    const livePricesForm = document.getElementById('livePricesForm');
    const chatMessages = document.getElementById('chatMessages');
    const chatInput = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    
    if (mode === 'live_prices') {
        livePricesForm.style.display = 'block';
        chatInput.disabled = true;
        sendButton.disabled = true;
        chatMessages.style.opacity = '0.5';
    } else {
        livePricesForm.style.display = 'none';
        livePricesPresets = null;
        livePricesResults = null; // Clear stored results when switching modes
        chatInput.disabled = false;
        sendButton.disabled = false;
        chatMessages.style.opacity = '1';
        document.getElementById('searchInfo').style.display = 'none';
    }
}

// Handle start search
async function handleStartSearch() {
    const city = document.getElementById('citySelect').value;
    const checkIn = document.getElementById('checkInDate').value;
    const checkOut = document.getElementById('checkOutDate').value;
    const preferences = document.getElementById('preferencesInput').value.trim();
    
    if (!city || !checkIn || !checkOut) {
        alert('Please select a city, check-in date, and check-out date.');
        return;
    }
    
    // Store presets
    livePricesPresets = {
        location: city,
        dates: { check_in: checkIn, check_out: checkOut }
    };
    
    // Disable start button during search
    const startSearchBtn = document.getElementById('startSearchBtn');
    startSearchBtn.disabled = true;
    startSearchBtn.textContent = 'Searching...';
    
    // Show typing indicator
    showTypingIndicator();
    
    const sessionId = getOrCreateSessionId();
    const query = preferences || `Show me hotels in ${city}`;
    
    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                mode: 'text',
                session_id: sessionId,
                force_mode: 'live_prices',
                preset_location: city,
                preset_dates: { check_in: checkIn, check_out: checkOut }
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        removeTypingIndicator();
        
        // Store results for re-ranking
        if (Array.isArray(data.hotels)) {
            livePricesResults = data.hotels;
        }
        
        // Display results
        const content = (data.response || '').trim() || 'Here are the available hotels.';
        const assistantData = Array.isArray(data.hotels) ? { hotels: data.hotels } : null;
        addMessage('assistant', content, assistantData);
        
        // Hide live prices form and show chat interface
        const livePricesForm = document.getElementById('livePricesForm');
        const chatMessages = document.getElementById('chatMessages');
        livePricesForm.style.display = 'none';
        chatMessages.style.opacity = '1'; // Restore full opacity to show results clearly
        
        // Enable chat input
        const chatInput = document.getElementById('chatInput');
        const sendButton = document.getElementById('sendButton');
        chatInput.disabled = false;
        sendButton.disabled = false;
        chatInput.placeholder = 'Ask to re-sort hotels (e.g., "show most romantic", "cheapest first")...';
        chatInput.focus();
        
        // Show search info
        const searchInfo = document.getElementById('searchInfo');
        searchInfo.innerHTML = `<strong>Active Search:</strong> ${city} | ${checkIn} to ${checkOut} <button onclick="resetLivePricesSearch()" style="margin-left: 1rem; padding: 0.3rem 0.8rem; background: rgba(139, 115, 85, 0.2); border: none; border-radius: 15px; cursor: pointer;">New Search</button>`;
        searchInfo.style.display = 'block';
        
    } catch (error) {
        removeTypingIndicator();
        addMessage('assistant', `Sorry, I encountered an error: ${error.message}. Please make sure the backend is running on port 8000!`, null, true);
    } finally {
        startSearchBtn.disabled = false;
        startSearchBtn.textContent = 'Start Search';
    }
}

// Reset live prices search (allow new search)
function resetLivePricesSearch() {
    livePricesResults = null;
    livePricesPresets = null;
    
    // Show live prices form
    const livePricesForm = document.getElementById('livePricesForm');
    const chatMessages = document.getElementById('chatMessages');
    livePricesForm.style.display = 'block';
    chatMessages.style.opacity = '0.5'; // Dim messages while form is active
    
    // Disable chat input
    const chatInput = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    chatInput.disabled = true;
    sendButton.disabled = true;
    chatInput.placeholder = 'Ask about hotels in Sri Lanka...';
    
    // Hide search info
    const searchInfo = document.getElementById('searchInfo');
    searchInfo.style.display = 'none';
    
    // Clear form
    document.getElementById('citySelect').value = '';
    document.getElementById('checkInDate').value = '';
    document.getElementById('checkOutDate').value = '';
    document.getElementById('preferencesInput').value = '';
}

// Add message to chat
function addMessage(role, content, data = null, isError = false) {
    const messagesContainer = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role} ${isError ? 'error' : ''} slide-in`;
    
    const avatarSVG = role === 'user' 
        ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
        : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';
    
    const roleText = role === 'user' ? 'You' : 'Scenery';
    
    let bodyContent = '';
    if (data && data.hotels && Array.isArray(data.hotels)) {
        bodyContent = formatHotelsResponse(content, data.hotels);
    } else {
        bodyContent = `<p class="response-text">${escapeHtml(content)}</p>`;
    }
    
    messageDiv.innerHTML = `
        <div class="message-avatar">${avatarSVG}</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-role">${roleText}</span>
                <span class="message-time">${getCurrentTime()}</span>
            </div>
            <div class="message-body">
                ${bodyContent}
            </div>
        </div>
    `;
    
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    // Save message to sessionStorage
    saveMessageToStorage(role, content, data, isError);
}

// Save message to sessionStorage
function saveMessageToStorage(role, content, data = null, isError = false) {
    try {
        let messages = JSON.parse(sessionStorage.getItem(MESSAGES_STORAGE_KEY) || '[]');
        messages.push({
            role,
            content,
            data,
            isError,
            timestamp: new Date().toISOString()
        });
        sessionStorage.setItem(MESSAGES_STORAGE_KEY, JSON.stringify(messages));
    } catch (error) {
        console.error('Failed to save message to sessionStorage:', error);
    }
}

// Restore messages from sessionStorage
function restoreMessages() {
    try {
        const messages = JSON.parse(sessionStorage.getItem(MESSAGES_STORAGE_KEY) || '[]');
        
        if (messages.length > 0) {
            // Hide suggested queries if there are messages
            const suggestedQueries = document.getElementById('suggestedQueries');
            if (suggestedQueries) {
                suggestedQueries.style.display = 'none';
            }
            
            const messagesContainer = document.getElementById('chatMessages');
            messages.forEach(msg => {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${msg.role} ${msg.isError ? 'error' : ''}`;
                
                const avatarSVG = msg.role === 'user' 
                    ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
                    : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';
                
                const roleText = msg.role === 'user' ? 'You' : 'Scenery';
                
                let bodyContent = '';
                if (msg.data && msg.data.hotels && Array.isArray(msg.data.hotels)) {
                    bodyContent = formatHotelsResponse(msg.content, msg.data.hotels);
                } else {
                    bodyContent = `<p class="response-text">${escapeHtml(msg.content)}</p>`;
                }
                
                // Format timestamp
                const timestamp = new Date(msg.timestamp);
                const timeString = timestamp.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit'
                });
                
                messageDiv.innerHTML = `
                    <div class="message-avatar">${avatarSVG}</div>
                    <div class="message-content">
                        <div class="message-header">
                            <span class="message-role">${roleText}</span>
                            <span class="message-time">${timeString}</span>
                        </div>
                        <div class="message-body">
                            ${bodyContent}
                        </div>
                    </div>
                `;
                
                messagesContainer.appendChild(messageDiv);
            });
            
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    } catch (error) {
        console.error('Failed to restore messages from sessionStorage:', error);
    }
}

// Format hotels response
function formatHotelsResponse(text, hotels) {
    // Display all LLM-ranked hotels (backend sends top 5 based on user preferences)
    const hotelsToShow = hotels;
    
    let hotelsHTML = hotelsToShow.map((hotel, index) => `
        <div class="hotel-card glass-morphism">
            <div class="hotel-header">
                <h4 class="hotel-name">${escapeHtml(hotel.name || 'Unnamed Hotel')}</h4>
                ${hotel.rating ? `<span class="hotel-rating">⭐ ${hotel.rating}</span>` : ''}
            </div>
            ${hotel.location ? `<p class="hotel-location">📍 ${escapeHtml(hotel.location)}</p>` : ''}
            ${hotel.price ? `<p class="hotel-price">💰 ${escapeHtml(formatPriceLkr(hotel.price))}</p>` : ''}
            ${hotel.description ? `<p class="hotel-description">${escapeHtml(hotel.description)}</p>` : ''}
        </div>
    `).join('');
    
    // Only show summary box if there are hotels
    const summaryBox = hotelsToShow.length > 0 ? `
        <div class="llm-summary-box glass-morphism">
            <svg class="summary-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 11l3 3L22 4"></path>
                <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"></path>
            </svg>
            <div class="summary-content">
                <h4 class="summary-title">Scenery's Choice</h4>
                <p class="summary-text">${escapeHtml(text)}</p>
            </div>
        </div>
    ` : `<p class="response-text">${escapeHtml(text)}</p>`;
    
    // Only render hotels-grid when there are hotels to prevent empty div creating gap
    const hotelsGridHTML = hotelsToShow.length > 0 ? `
        <div class="hotels-grid">
            ${hotelsHTML}
        </div>
    ` : '';
    
    return `
        <div class="hotels-response">
            ${hotelsGridHTML}
            ${summaryBox}
        </div>
    `;
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
    let existing = localStorage.getItem(SESSION_STORAGE_KEY);
    
    // Validate existing session ID
    if (existing && existing.length > 10) {
        return existing;
    }

    // Generate new session ID
    const generated = (window.crypto && typeof window.crypto.randomUUID === 'function')
        ? window.crypto.randomUUID()
        : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;

    localStorage.setItem(SESSION_STORAGE_KEY, generated);
    return generated;
}

// Show typing indicator
function showTypingIndicator() {
    const messagesContainer = document.getElementById('chatMessages');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message assistant slide-in';
    typingDiv.id = 'typingIndicator';
    
    typingDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    
    messagesContainer.appendChild(typingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Remove typing indicator
function removeTypingIndicator() {
    const typingIndicator = document.getElementById('typingIndicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
