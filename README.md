# Watched

A personal dashboard to track movies and TV shows, focused on your data habits rather than just lists.

I built this because I wanted to see my "Wrapped" stats year-round, not just in December. It serves as a self-hosted alternative to Letterboxd or IMDb, designed to give you better insight into *how* you watch.

## Features

*   **Real-time Wrapped**: Generates an Instagram-Story style report of your year at any moment.
*   **The Sprint**: A bi-weekly tracker to see your recent watching velocity.
*   **Recommendation Engine**: Filters out what you've likely seen and finds hidden gems based on your history.
*   **Private Leaderboards**: See how you stack up against friends in your city (e.g., "Most Watched in Lagos").
*   **Chrome Extension**: Adds a "Mark Watched" button directly to Google Search results.

## Tech Stack

*   **Backend**: Python (FastAPI), SQLite (Local) / PostgreSQL (Prod), SQLAlchemy
*   **Frontend**: HTML5, Vanilla JS, Tailwind CSS
*   **Auth**: Google OAuth + JWT
*   **Data**: TMDB API

## Setup

### Prerequisites
*   Python 3.8+
*   TMDB API Key
*   Google Client ID

### Local Development

1.  **Clone the repo**
    ```bash
    git clone https://github.com/ObaIsSoft/watched.git
    cd watched
    ```

2.  **Start Backend**
    ```bash
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    uvicorn main:app --reload
    ```
    App runs at `http://localhost:8000`.

3.  **Environment**
    Export your keys in the terminal or use a `.env` file:
    ```bash
    export TMDB_API_KEY="..."
    export GOOGLE_CLIENT_ID="..."
    export SECRET_KEY="..."
    ```

## Deployment
See [DEPLOY_RENDER.md](DEPLOY_RENDER.md) for a guide on deploying to Render.

## License
MIT.

---
*Built with ❤️ by Obafemi*
