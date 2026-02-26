# 🚀 How to Run the Scenery Frontend

This is a complete guide for someone who has never built a React frontend before!

## Prerequisites

You need to have **Node.js** installed on your Mac. Node.js comes with npm (Node Package Manager) which we'll use to install dependencies.

### Step 1: Install Node.js

1. Open Terminal (you can find it using Spotlight Search: Cmd + Space, then type "Terminal")
2. Check if you have Node.js installed:
   ```bash
   node --version
   ```
   
   If you see a version number (like v18.0.0 or higher), you're good to go! Skip to Step 2.
   
3. If not installed, install Node.js using Homebrew:
   ```bash
   # Install Homebrew if you don't have it
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   
   # Install Node.js
   brew install node
   ```
   
4. Verify installation:
   ```bash
   node --version
   npm --version
   ```

## Step 2: Navigate to the Frontend Directory

```bash
cd /Users/dulith/Scenery/frontend
```

## Step 3: Install Dependencies

This will download and install all the required packages (React, Vite, etc.):

```bash
npm install
```

This might take a few minutes. You'll see a progress bar as npm downloads packages.

## Step 4: Start the Backend Server

The frontend needs the backend API to be running. Open a **NEW terminal window** (Cmd + T) and:

```bash
cd /Users/dulith/Scenery

# Activate your Python environment if you have one
# For example: source venv/bin/activate

# Start the backend server
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Keep this terminal window open!** The backend needs to keep running.

## Step 5: Start the Frontend Development Server

Go back to your first terminal window (the one in the frontend directory) and run:

```bash
npm run dev
```

You should see output like:
```
  VITE v5.0.8  ready in XXX ms

  ➜  Local:   http://localhost:3000/
  ➜  Network: use --host to expose
  ➜  press h to show help
```

## Step 6: Open the Application

1. Open your web browser (Chrome, Safari, Firefox, etc.)
2. Go to: **http://localhost:3000**

🎉 **You should now see the Scenery frontend!**

## Understanding What You're Seeing

- **Home Page**: Beautiful landing page with features and call-to-action
- **Chat Page**: Interactive AI chat interface - click "Start Chatting" or "Chat" in the nav
- **Search Page**: Advanced hotel search with filters

## How It Works

1. **Frontend (Port 3000)**: The React app running in your browser
2. **Backend (Port 8000)**: The Python FastAPI server handling requests
3. **Communication**: When you chat or search, the frontend sends requests to the backend at `http://localhost:8000`

## Common Issues & Solutions

### Issue: "npm: command not found"
**Solution**: Node.js isn't installed. Go back to Step 1.

### Issue: Port 3000 is already in use
**Solution**: Stop any other application using port 3000, or change the port in `vite.config.js`:
```javascript
server: {
  port: 3001, // Change to any available port
  // ... rest of config
}
```

### Issue: Backend connection failed
**Solution**: Make sure the backend is running on port 8000. Check the terminal running the backend for errors.

### Issue: "Cannot GET /chat" or API errors
**Solution**: The Vite proxy might need a restart. Stop the frontend (Ctrl + C) and run `npm run dev` again.

## Making Changes

The beauty of React development is **hot reloading**! Any changes you make to files in the `src/` directory will automatically update in your browser - no need to restart!

Try it:
1. Open `src/pages/Home.jsx`
2. Change some text (like the hero title)
3. Save the file
4. Watch your browser automatically update!

## Building for Production

When you're ready to deploy your app:

```bash
npm run build
```

This creates an optimized production build in the `dist/` folder.

## Project Structure

```
frontend/
├── src/
│   ├── pages/           # Main page components
│   │   ├── Home.jsx     # Landing page
│   │   ├── Chat.jsx     # Chat interface
│   │   └── SearchPage.jsx  # Hotel search
│   ├── components/      # Reusable components (empty for now)
│   ├── App.jsx          # Main app component with routing
│   ├── main.jsx         # Entry point
│   └── index.css        # Global styles
├── public/              # Static assets
├── index.html           # HTML template
├── package.json         # Dependencies and scripts
└── vite.config.js       # Vite configuration
```

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build locally

## Next Steps

1. **Customize the Design**: Edit CSS files to change colors, fonts, etc.
2. **Add Features**: Create new components in the `src/components/` directory
3. **Explore React**: Learn about React hooks, state management, and more!

## Learning Resources

- [React Documentation](https://react.dev/) - Official React docs
- [Vite Documentation](https://vitejs.dev/) - Vite build tool
- [React Router](https://reactrouter.com/) - Navigation in React

## Need Help?

- Check the browser console (Right-click → Inspect → Console) for errors
- Check the terminal running the frontend for build errors
- Check the terminal running the backend for API errors

---

Enjoy building with Scenery! 🌄
