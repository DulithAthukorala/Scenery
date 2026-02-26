// Configuration
const API_BASE_URL = 'http://localhost:8000';

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const initialTime = document.getElementById('initialTime');
    if (initialTime) {
        initialTime.textContent = getCurrentTime();
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
    input.value = button.textContent;
    input.focus();
}

// Handle form submission
document.getElementById('chatForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Hide suggested queries after first message
    const suggestedQueries = document.getElementById('suggestedQueries');
    if (suggestedQueries) {
        suggestedQueries.style.display = 'none';
    }
    
    // Add user message
    addMessage('user', message);
    
    // Clear input
    input.value = '';
    
    // Disable input and button
    const sendButton = document.getElementById('sendButton');
    input.disabled = true;
    sendButton.disabled = true;
    
    // Show typing indicator
    showTypingIndicator();
    
    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: message,
                mode: 'text'
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Remove typing indicator
        removeTypingIndicator();
        
        // Add assistant message
        const content = data.response || JSON.stringify(data, null, 2);
        addMessage('assistant', content, data);
        
    } catch (error) {
        removeTypingIndicator();
        addMessage('assistant', `❌ Sorry, I encountered an error: ${error.message}. Please make sure the backend is running on port 8000!`, null, true);
    } finally {
        // Re-enable input and button
        input.disabled = false;
        sendButton.disabled = false;
        input.focus();
    }
});

// Add message to chat
function addMessage(role, content, data = null, isError = false) {
    const messagesContainer = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role} ${isError ? 'error' : ''} slide-in`;
    
    const avatarSVG = role === 'user' 
        ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
        : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';
    
    const roleText = role === 'user' ? 'You' : 'AI Assistant';
    
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
}

// Format hotels response
function formatHotelsResponse(text, hotels) {
    const hotelsToShow = hotels.slice(0, 6);
    
    let hotelsHTML = hotelsToShow.map(hotel => `
        <div class="hotel-card glass-morphism">
            <div class="hotel-header">
                <h4 class="hotel-name">${escapeHtml(hotel.name || 'Unnamed Hotel')}</h4>
                ${hotel.rating ? `<span class="hotel-rating">⭐ ${hotel.rating}</span>` : ''}
            </div>
            ${hotel.location ? `<p class="hotel-location">📍 ${escapeHtml(hotel.location)}</p>` : ''}
            ${hotel.price ? `<p class="hotel-price">💰 $${hotel.price}</p>` : ''}
            ${hotel.description ? `<p class="hotel-description">${escapeHtml(hotel.description)}</p>` : ''}
        </div>
    `).join('');
    
    return `
        <div class="hotels-response">
            <p class="response-text">${escapeHtml(text)}</p>
            <div class="hotels-grid">
                ${hotelsHTML}
            </div>
        </div>
    `;
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
