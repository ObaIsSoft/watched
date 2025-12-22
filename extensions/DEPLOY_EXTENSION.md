# 🔌 Connecting the Extension to Live

The Chrome Extension currently points to your **Local** server (`localhost:8000`).
To make it talk to your **Live** Render server, you need to change 3 lines of code.

## 1. Edit `manifest.json`
Change the `host_permissions` to your Render URL.
```json
// Old
"host_permissions": ["http://localhost:8000/*"],

// New
"host_permissions": ["https://your-app-name.onrender.com/*"],
```

## 2. Edit `background.js`
Update the API URL and Cookie URL in `background.js`.

**Line 5:**
```javascript
// Old
chrome.cookies.get({ url: "http://localhost:8000", name: "access_token" }, ...

// New
chrome.cookies.get({ url: "https://your-app-name.onrender.com", name: "access_token" }, ...
```

**Line 14:**
```javascript
// Old
fetch("http://localhost:8000/api/log", ...

// New
fetch("https://your-app-name.onrender.com/api/log", ...
```

## 3. Reload Extension
1. Go to `chrome://extensions`.
2. Find **Watched: Overlay**.
3. Click the **Refresh** icon (circular arrow).

## 4. Log In
1. Go to your new `https://your-app-name.onrender.com` in Chrome.
2. Log in with Google.
3. The extension will now automatically grab your token and start working!
