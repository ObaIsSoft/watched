# Watched

> **Your Media. Your Data. Your Vibe.**
> A next-generation personal media tracker that replaces spreadsheets and basic apps with a premium, data-driven dashboard.

![Watched Dashboard](https://via.placeholder.com/1200x600?text=Watched+Dashboard+Preview)

## What makes this different?
Unlike standard trackers (IMDb, Letterboxd), **Watched** is built for **self-discovery**. It doesn't just list what you watched; it tells you *who you are*.

*   **2025 Wrapped... Every Day**: Generate an interactive, Instagram-Story style "Wrapped" report any time you want. See your year in review, instantly.
*   **The Sprint**: Tracks your watching habits over the last 14 days. Are you slacking? Binging? The dashboard knows.
*   **Smart Recommendations**: A recommendation engine that actually respects your history. No more suggesting movies you've already seen.
*   **Social Leaderboards**: Compare "Hours Watched" and "Vibe" with friends in your city or country.
*   **Premium UI**: Dark mode, glassmorphism, and fluid animations powered by Tailwind CSS.

## Tech Stack
*   **Backend**: Python, FastAPI, SQLite, SQLAlchemy.
*   **Frontend**: HTML5, Vanilla JavaScript, Tailwind CSS (CDN).
*   **Data Source**: TMDB (The Movie Database) API.
*   **Authentication**: Google OAuth + JWT.

## Getting Started

### Prerequisites
*   Python 3.8+
*   A TMDB API Key (Get one at [themoviedb.org](https://www.themoviedb.org/documentation/api))
*   Google OAuth Client ID (for login)

### Installation

1.  **Clone the repo**
    ```bash
    git clone https://github.com/ObaIsSoft/watched.git
    cd watched
    ```

2.  **Setup the Backend**
    ```bash
    cd backend
    python3 -m venv venv
    source venv/bin/activate  # or venv\Scripts\activate on Windows
    pip install -r requirements.txt
    ```

3.  **Environment Variables**
    Create a `.env` file in `backend/` or export them:
    ```bash
    export TMDB_API_KEY="your_tmdb_key_here"
    export GOOGLE_CLIENT_ID="your_google_client_id"
    export SECRET_KEY="super_secret_key"
    ```
    *(Note: The `main.py` has defaults for dev, but use env vars for security!)*

4.  **Run the Server**
    ```bash
    uvicorn main:app --reload
    ```
    The app will be live at `http://localhost:8000`.

## Chrome Extension (Optional)
This project includes a Chrome Extension to overlay "Mark Watched" buttons directly on Google Search results.

1.  Go to `chrome://extensions/` in Chrome.
2.  Enable "Developer mode" (top right).
3.  Click "Load unpacked".
4.  Select the `extensions/` folder from this project.

## Features in Depth

### The Dashboard
Your command center. View your Watchlist, History, and Up Next recommendations. Filter by genre, rating, or year.

### Story Mode
Click "2025 Wrapped" to enter an immersive story experience.
*   **Intro**: Your year at a glance.
*   **The Vibe**: Your top genre and personality roast.
*   **Stats**: Total hours, movies vs TV split.
*   **Top Cast**: Who did you watch the most?

### Private Social
Add friends to see a private leaderboard.
*   **City/Country Rank**: Who is the #1 watcher in Lagos?
*   **Vibe Check**: See what your friends are into (e.g., "Sci-Fi", "Horror").

## License
MIT License. It's your code.

---
*Built with ❤️ by Obafemi*
