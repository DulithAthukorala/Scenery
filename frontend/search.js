// Configuration
const API_BASE_URL = 'http://localhost:8000';
const SESSION_STORAGE_KEY = 'scenery_session_id';

// Clear filters
function clearFilters() {
    document.getElementById('location').value = '';
    document.getElementById('rating').value = '';
    document.getElementById('priceMin').value = '';
    document.getElementById('priceMax').value = '';
    document.getElementById('userRequest').value = 'Find the best value hotel for me.';
    
    document.getElementById('emptyState').style.display = 'flex';
    document.getElementById('resultsContainer').style.display = 'none';
    document.getElementById('errorMessage').style.display = 'none';
}

// Handle form submission
document.getElementById('searchForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const location = document.getElementById('location').value;
    const rating = document.getElementById('rating').value;
    const priceMin = document.getElementById('priceMin').value;
    const priceMax = document.getElementById('priceMax').value;
    const userRequest = document.getElementById('userRequest').value.trim();
    
    if (!location) {
        showError('Please select a location');
        return;
    }
    
    // Hide empty state and previous results
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('resultsContainer').style.display = 'none';
    document.getElementById('errorMessage').style.display = 'none';
    
    // Show loading state
    const searchButton = document.getElementById('searchButton');
    const originalButtonHTML = searchButton.innerHTML;
    searchButton.disabled = true;
    searchButton.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinner">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
        Searching...
    `;
    
    try {
        const sessionId = getOrCreateSessionId();
        const queryParts = [userRequest || 'Find hotels'];
        queryParts.push(`in ${location}`);
        if (rating) queryParts.push(`rating ${rating}+`);
        if (priceMin) queryParts.push(`minimum price ${priceMin}`);
        if (priceMax) queryParts.push(`maximum price ${priceMax}`);
        const query = queryParts.join(', ');

        // Use the chat endpoint which intelligently routes to local DB or RapidAPI
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query,
                mode: 'text',
                session_id: sessionId
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        displayResults(data);
        
    } catch (error) {
        showError(error.message || 'Failed to fetch hotels. Please make sure the backend is running on port 8000!');
    } finally {
        searchButton.disabled = false;
        searchButton.innerHTML = originalButtonHTML;
    }
});

// Display results
function displayResults(data) {
    const resultsContainer = document.getElementById('resultsContainer');

    // Handle different response structures from chat endpoint
    const responseData = data.data || {};

    // Check if this is an error or ask response
    if (data.action === 'ASK_LOCATION' || data.action === 'ASK_DATES') {
        showError(data.message || 'Please provide more information');
        return;
    }

    if (data.action === 'RAPIDAPI_ERROR') {
        showError(data.message || 'Could not fetch live prices right now.');
        return;
    }

    const ranking = responseData.ranking || {};
    const hotels = ranking.ranked_hotels || responseData.results || [];
    const insights = ranking.llm_response || 'Here are your best matching hotels.';

    let html = `
        <div class="results-header">
            <h2>Found ${hotels.length} hotels</h2>
            ${insights ? `<p class="ai-insights">${escapeHtml(insights)}</p>` : ''}
            ${data.action === 'RAPIDAPI' ? '<p class="live-prices-badge">🔴 Live Prices</p>' : ''}
        </div>
    `;
    
    if (hotels.length > 0) {
        html += '<div class="hotels-results-grid">';
        hotels.forEach(hotel => {
            html += `
                <div class="hotel-result-card glass-morphism hover-lift">
                    <div class="hotel-card-header">
                        <h3 class="hotel-card-name">${escapeHtml(hotel.name || 'Unnamed Hotel')}</h3>
                        ${hotel.rating ? `
                            <div class="hotel-card-rating">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2">
                                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                                </svg>
                                ${hotel.rating}
                            </div>
                        ` : ''}
                    </div>
                    
                    ${hotel.location ? `
                        <div class="hotel-card-info">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                                <circle cx="12" cy="10" r="3"/>
                            </svg>
                            ${escapeHtml(hotel.location)}
                        </div>
                    ` : ''}
                    
                    ${hotel.price ? `
                        <div class="hotel-card-info">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="12" y1="1" x2="12" y2="23"/>
                                <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
                            </svg>
                            ${escapeHtml(formatPriceLkr(hotel.price))} per night
                        </div>
                    ` : ''}
                    
                    ${hotel.description ? `
                        <p class="hotel-card-description">${escapeHtml(hotel.description)}</p>
                    ` : ''}
                    
                    ${hotel.amenities && hotel.amenities.length > 0 ? `
                        <div class="hotel-amenities">
                            ${hotel.amenities.slice(0, 3).map(amenity => 
                                `<span class="amenity-tag">${escapeHtml(amenity)}</span>`
                            ).join('')}
                        </div>
                    ` : ''}
                    
                    <button class="hotel-view-button">View Details</button>
                </div>
            `;
        });
        html += '</div>';
    } else {
        html += `
            <div class="no-results glass-morphism">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"/>
                    <path d="m21 21-4.35-4.35"/>
                </svg>
                <h3>No hotels found</h3>
                <p>Try adjusting your filters or search criteria</p>
            </div>
        `;
    }
    
    resultsContainer.innerHTML = html;
    resultsContainer.style.display = 'flex';
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

// Show error
function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.className = 'error-message glass-morphism';
    errorDiv.innerHTML = `<p>❌ ${escapeHtml(message)}</p>`;
    errorDiv.style.display = 'block';
    
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('resultsContainer').style.display = 'none';
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
