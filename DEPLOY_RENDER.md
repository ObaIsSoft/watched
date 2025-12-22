# 🚀 Deploying to Render

This guide will get your **Watched** dashboard live on the internet using Render.com.

## 1. Prepare your Repo
Ensure your code is pushed to GitHub.
```bash
git add .
git commit -m "Prepare for deployment"
git push origin main
```

## 2. Create the Database (Postgres)
**Crucial Step**: You cannot use SQLite on Render (your data will disappear every restart). You must use Postgres.

1.  Log in to [dashboard.render.com](https://dashboard.render.com).
2.  Click **New +** -> **PostgreSQL**.
3.  Name it `watched-db`.
4.  Select the **Free** tier (sandbox).
5.  Click **Create Database**.
6.  Wait for it to be created. Copy the **Internal Database URL**.

## 3. Create the Web Service
Now, deploy the Python app.

1.  Click **New +** -> **Web Service**.
2.  Connect your GitHub repo.
3.  **Settings**:
    *   **Name**: `watched-app`
    *   **Region**: Same as your DB (e.g., Oregon).
    *   **Root Directory**: `backend` (Important!)
    *   **Environment**: `Python 3`
    *   **Build Command**: `pip install -r requirements.txt`
    *   **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4.  **Environment Variables** (Scroll down to "Environment"):
    Add these keys:
    *   `DATABASE_URL`: Paste the **Internal Database URL** from Step 2.
    *   `TMDB_API_KEY`: Your TMDB API Key.
    *   `GOOGLE_CLIENT_ID`: Your Google Client ID.
    *   `SECRET_KEY`: Generate a random long string (e.g. `openssl rand -hex 32`).
5.  Click **Create Web Service**.

## 4. Finalize & Fix Google Login
Render will now build your app. Once it is live, you will get a URL like `https://watched-app.onrender.com`.

**⚠️ Important: Fix "Access Blocked" Error**
Google doesn't know about your new website yet.

1.  Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2.  Find your **OAuth 2.0 Client ID** (the one you made for this project).
3.  Look for **Authorized JavaScript origins**.
4.  Click **Add URI**.
5.  Paste your **new Render URL** (e.g., `https://watched-app.onrender.com`).
    *   *Do NOT put a trailing slash `/` at the end.*
6.  Click **Save**.

*Note: It may take 5 minutes for Google to update.*

**Done!** visit your `onrender.com` URL.
