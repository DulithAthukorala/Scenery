# 🚀 Scenery Frontend - Plain HTML/CSS/JS

**No Node.js, No npm, No build tools required!**

Just open the HTML files in your browser and start using the app.

## 📁 What's Inside

```
frontend/
├── index.html       # Home page (landing)
├── chat.html        # AI Chat interface
├── search.html      # Hotel search
├── styles.css       # All the beautiful styles
├── chat.js          # Chat functionality
└── search.js        # Search functionality
```

## 🏃 How to Run

### Step 1: Start the Backend

The frontend needs your FastAPI backend running. Open Terminal and run:

```bash
cd /Users/dulith/Scenery
python -m uvicorn backend.main:app --reload --port 8000
```

Keep this terminal window open! You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 2: Open the Frontend

**Option A: Double-click the files**
- Navigate to `/Users/dulith/Scenery/frontend/`
- Double-click `index.html` to open in your browser

**Option B: Use the command line**
```bash
open /Users/dulith/Scenery/frontend/index.html
```

**Option C: Start a simple Python server (recommended for avoiding CORS issues)**
```bash
cd /Users/dulith/Scenery/frontend
python3 -m http.server 3000
```
Then open: http://localhost:3000

### Step 3: Explore!

- **Home Page** (`index.html`) - Beautiful landing page
- **Chat** (`chat.html`) - Talk to the AI assistant
- **Search** (`search.html`) - Advanced hotel search with filters

## 🎨 Features

- ✨ **Same Beautiful Design** - Dark theme with gradients
- 💬 **AI Chat** - Real-time conversations with hotel recommendations
- 🔍 **Hotel Search** - Filter by location, price, rating
- 📱 **Fully Responsive** - Works on desktop, tablet, mobile
- ⚡ **No Dependencies** - Pure vanilla JavaScript

## 🔧 How It Works

### Architecture

```
Browser (Frontend) ←→ FastAPI (Backend)
   Port 3000              Port 8000
```

The JavaScript files (`chat.js` and `search.js`) make HTTP requests to your backend API:
- Chat: `POST http://localhost:8000/chat`
- Search: `GET http://localhost:8000/localdb/hotels/insights`

### Configuration

Both JS files have this at the top:
```javascript
const API_BASE_URL = 'http://localhost:8000';
```

If your backend is on a different port, change this URL in:
- `chat.js`
- `search.js`

## 🐛 Troubleshooting

### "Failed to fetch" or "CORS error"

**Solution 1**: Use Python's HTTP server (recommended)
```bash
cd /Users/dulith/Scenery/frontend
python3 -m http.server 3000
```
Then open http://localhost:3000

**Solution 2**: Enable CORS in your backend
Add to `backend/main.py`:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Backend not responding

Make sure it's running on port 8000:
```bash
curl http://localhost:8000/health
```
Should return: `{"status":"ok"}`

### Chat/Search not working

1. Open browser DevTools (Right-click → Inspect → Console)
2. Look for error messages
3. Check that backend is running
4. Verify the API_BASE_URL in the JS files

## 📝 Making Changes

### Change Colors
Edit `styles.css` and modify the CSS variables at the top:
```css
:root {
  --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  /* etc */
}
```

### Add New Features
- HTML structure goes in `.html` files
- Styles go in `styles.css`
- JavaScript logic goes in `.js` files

### Hot Reload
Just refresh your browser (Cmd+R) after making changes!

## 🌟 What Makes This Special

- **Zero Dependencies**: No package.json, no node_modules
- **Simple Deployment**: Just upload HTML/CSS/JS files to any web server
- **Easy to Understand**: Plain vanilla JavaScript, no frameworks
- **Production Ready**: Minify the files and deploy anywhere
- **Beautiful UI**: Same aesthetic as the React version

## 🚀 Next Steps

1. Customize colors in `styles.css`
2. Add your own branding
3. Deploy to GitHub Pages, Netlify, or any static host
4. Add more features (save favorites, booking, etc.)

---

**Enjoy your Node.js-free, React-free, beautiful frontend!** 🎉
