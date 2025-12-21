import httpx
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, case, func, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime, timedelta
from collections import Counter
import os
import logging
from jose import jwt, JWTError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# --- LOGGING SETUP ---
logging.basicConfig(
    filename='server.log', 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- CONFIGURATION ---
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "331904c8f8fb8f3fbe3e59cf24566a89")
SECRET_KEY = os.environ.get("SECRET_KEY", "my_super_secret_key_change_me_in_prod")
ALGORITHM = "HS256"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "725965614246-s6r1sh4m1i9mocm8pa5ag1e67asd2ev3.apps.googleusercontent.com")
 

# --- DATABASE SETUP (SQLite) ---
DATABASE_URL = "sqlite:///./watched_history.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    picture = Column(String)
    is_public = Column(Boolean, default=True)
    
    history = relationship("WatchHistory", back_populates="user")
    
    # Relationships for Social
    followers = relationship("Follower", foreign_keys="Follower.followed_id", back_populates="followed")
    following = relationship("Follower", foreign_keys="Follower.follower_id", back_populates="follower")
    
    # New Social Fields
    bio = Column(String, default="")
    notifications = relationship("Notification", back_populates="user")

class Follower(Base):
    __tablename__ = "followers"
    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey("users.id"))
    followed_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    follower = relationship("User", foreign_keys=[follower_id], back_populates="following")
    followed = relationship("User", foreign_keys=[followed_id], back_populates="followers")

class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    history_id = Column(Integer, ForeignKey("history.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    history_id = Column(Integer, ForeignKey("history.id"))
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    history = relationship("WatchHistory", back_populates="comments") # Backref needed

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String) # 'like', 'comment', 'follow'
    message = Column(String)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="notifications")

class WatchHistory(Base):
    __tablename__ = "history"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    tmdb_id = Column(Integer)
    media_type = Column(String) # 'movie' or 'tv'
    poster_path = Column(String)
    
    # New Fields for Analytics
    status = Column(String, default="watchlist") # 'watchlist' or 'watched'
    added_at = Column(DateTime, default=datetime.utcnow)
    watched_at = Column(DateTime, nullable=True) # Set when moved to watched
    
    # Rich Metadata
    genres = Column(String) # Comma-separated string: "Action, Sci-Fi"
    runtime = Column(Integer) # In minutes
    year = Column(Integer)
    total_episodes = Column(Integer, default=1)
    
    # Enhanced Metadata (Analytics v2)
    production_companies = Column(String) # JSON or comma-separated
    cast = Column(String) # Top 5 actors
    crew = Column(String) # Director/Creator
    keywords = Column(String) # Sub-genres (e.g. "dystopian")
    production_countries = Column(String) # Country codes "US, NG, IN"
    
    # Ownership
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="history")
    
    comments = relationship("Comment", back_populates="history")
    likes = relationship("Like", backref="history")

# --- MIGRATION UTILS ---
def run_migrations():
    # Simple migration to add columns if they don't exist
    conn = engine.connect()
    try:
        # --- History Table ---
        result = conn.execute(text("PRAGMA table_info(history)"))
        columns = [row[1] for row in result.fetchall()]
        
        # Base cols
        if 'total_episodes' not in columns:
            logging.info("Migrating DB: Adding total_episodes column")
            conn.execute(text("ALTER TABLE history ADD COLUMN total_episodes INTEGER DEFAULT 1"))
        
        if 'user_id' not in columns:
            logging.info("Migrating DB: Adding user_id column")
            conn.execute(text("ALTER TABLE history ADD COLUMN user_id INTEGER references users(id)"))

        # Metadata Migrations
        new_cols = ['production_companies', 'cast', 'crew', 'keywords', 'production_countries']
        for col in new_cols:
            if col not in columns:
                logging.info(f"Migrating DB: Adding {col} column")
                conn.execute(text(f"ALTER TABLE history ADD COLUMN {col} STRING"))
                
        # --- Users Table ---
        result_u = conn.execute(text("PRAGMA table_info(users)"))
        u_cols = [row[1] for row in result_u.fetchall()]
        
        if 'bio' not in u_cols:
            logging.info("Migrating DB: Adding bio column to users")
            conn.execute(text("ALTER TABLE users ADD COLUMN bio STRING DEFAULT ''"))

        # --- User Notifications Relationship ---
        # No DB column needed for relationship, but ensuring logic is sound is good.
        
    except Exception as e:
        logging.error(f"Migration failed: {e}")
    finally:
        conn.close()



from sqlalchemy import text
Base.metadata.create_all(bind=engine) # This creates new tables like 'followers' automatically
run_migrations()

# --- REPAIR UTILS ---
def get_series_runtime_sync(tmdb_id, seasons):
    """Sync helper to calculate total minutes for a series."""
    total_minutes = 0
    total_episodes = 0
    
    for season in seasons:
        if season['season_number'] == 0: continue # Skip specials usually? Or include? User said "each episode in each season". Standard is usually regular seasons. Let's include all.
        
        try:
            url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season['season_number']}"
            res = httpx.get(url, params={"api_key": TMDB_API_KEY})
            if res.status_code == 200:
                data = res.json()
                episodes = data.get('episodes', [])
                for ep in episodes:
                    if ep.get('runtime'):
                        total_minutes += ep['runtime']
                        total_episodes += 1
        except Exception as e:
            logging.error(f"Failed to fetch S{season['season_number']} for {tmdb_id}: {e}")
            
    return total_minutes, total_episodes

def repair_data():
    """
    Scans for all entries and ensures:
    1. TV shows have TOTAL cumulative runtime.
    2. All entries have Enhanced Metadata (studios, cast, keywords).
    """
    db = SessionLocal()
    try:
        entries = db.query(WatchHistory).all()
        if not entries:
            return

        logging.info(f"Scanning {len(entries)} entries for maintenance (Runtime & Metadata)...")
        
        for entry in entries:
            # Check if metadata is missing (including countries)
            needs_metadata = not (entry.production_companies and entry.cast and entry.keywords and entry.production_countries)
            
            # Check if TV needs runtime fix (simplified check)
            needs_runtime = (entry.media_type == 'tv' and entry.runtime == 0)

            if not (needs_metadata or needs_runtime):
                continue

            logging.info(f"Backfilling data for: {entry.title}")
            
            try:
                # Fetch Details
                url = f"https://api.themoviedb.org/3/{entry.media_type}/{entry.tmdb_id}"
                params = {"api_key": TMDB_API_KEY, "append_to_response": "credits,keywords"}
                
                # Sync fetch
                res = httpx.get(url, params=params)
                if res.status_code == 200:
                    details = res.json()
                    
                    # 1. Update Metadata
                    studios = [c['name'] for c in details.get('production_companies', [])]
                    entry.production_companies = ", ".join(studios[:3])
                    
                    credits = details.get('credits', {})
                    entry.cast = ", ".join([c['name'] for c in credits.get('cast', [])[:5]])
                    
                    crew_list = [c['name'] for c in credits.get('crew', []) if c.get('job') in ['Director', 'Creator', 'Executive Producer']]
                    entry.crew = ", ".join(crew_list[:3])
                    
                    k_key = 'results' if 'results' in details.get('keywords', {}) else 'keywords'
                    entry.keywords = ", ".join([k['name'] for k in details.get('keywords', {}).get(k_key, [])][:10])

                    # Countries
                    c_list = [c['iso_3166_1'] for c in details.get('production_countries', [])]
                    entry.production_countries = ", ".join(c_list)

                    # 2. Update TV Runtime (if needed/applicable)
                    if entry.media_type == 'tv':
                        seasons = details.get('seasons', [])
                        total_min, total_eps = get_series_runtime_sync(entry.tmdb_id, seasons)
                        if total_min > 0:
                            entry.runtime = total_min
                            entry.total_episodes = total_eps
                    
                    db.commit()
                    
            except Exception as e:
                logging.error(f"Failed to backfill {entry.title}: {e}")
                
    except Exception as e:
        logging.error(f"Maintenance failed: {e}")
    finally:
        db.close()




# --- FASTAPI APP ---
app = FastAPI()

# Allow Chrome Extension to hit localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")

class LogRequest(BaseModel):
    title: str
    year: str | None = None
    status: str = "watchlist"
    media_type: str | None = None
    watched_at: datetime | None = None

class UpdateRequest(BaseModel):
    status: str # 'watched'
    watched_at: datetime | None = None

class CommentRequest(BaseModel):
    content: str
    
class ProfileUpdate(BaseModel):
    bio: str
    picture: Optional[str] = None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("templates/dashboard.html", "r") as f:
        return f.read()

@app.get("/login", response_class=HTMLResponse)
def read_login():
    with open("templates/login.html", "r") as f:
        return f.read()

@app.get("/history", response_class=HTMLResponse)
def read_history():
    with open("templates/dashboard.html", "r") as f:
        return f.read()

# --- AUTH UTILS ---
from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class GoogleAuthRequest(BaseModel):
    credential: str # Google ID Token

def create_access_token(data: dict):
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        # logging.info(f"Auth Check: Token={token[:10]}...") 
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            logging.error("Auth Fail: No sub in payload")
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logging.error(f"Auth Fail: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# --- AUTH ROUTES ---
@app.post("/api/auth/google")
def google_login(request: GoogleAuthRequest, db: Session = Depends(get_db)):
    try:
        # Verify Google Token
        id_info = id_token.verify_oauth2_token(request.credential, google_requests.Request(), GOOGLE_CLIENT_ID)
        
        email = id_info['email']
        name = id_info.get('name', 'Unknown')
        picture = id_info.get('picture', '')
        
        # Find or Create User
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, name=name, picture=picture)
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Update info
            user.name = name
            user.picture = picture
            db.commit()
            
        # Issue JWT
        access_token = create_access_token(data={"sub": str(user.id)})
        return {"access_token": access_token, "user": {"name": user.name, "picture": user.picture}}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Google Token")

@app.get("/api/users/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return {"name": current_user.name, "picture": current_user.picture}

# --- LEADERBOARD ---
@app.get("/api/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    # Aggregation: Get total runtime per user
    users = db.query(User).filter(User.is_public == True).all()
    leaderboard = []
    
    for user in users:
        # Calculate total watched hours
        watched = db.query(WatchHistory).filter(
            WatchHistory.user_id == user.id, 
            WatchHistory.status == 'watched'
        ).all()
        
        total_minutes = sum([(item.runtime or 0) * (item.total_episodes or 1) for item in watched])
        # Note: Above logic is simplified; exact logic (used in stats) already puts total in runtime.
        # Wait, my "Exact Series Runtime" change put the TOTAL in `.runtime`. 
        # So for Series, runtime IS the total. For Movies, it's also total.
        # So I assume `item.runtime` IS the total duration for that entry.
        # BUT, `get_stats` logic was: `duration = item.runtime`. 
        # But wait, `get_stats` logic had: `episodes = item.total_episodes if item.total_episodes else 1` -> `duration = runtime * episodes`.
        # I changed `repair_tv_data` to set `runtime = total_series_minutes`. 
        # So `total_episodes` is just metadata now? 
        # Let's check `get_stats` logic in previous turn again.
        # Ah, in Step 532 I updated `get_stats` to have `duration = item.runtime`. Oh wait, I see `duration = (item.runtime if item.runtime else 0) * episodes` in the replace block I sent?
        # Let me re-read Step 532.
        # Step 532 replace block for get_stats:
        # `duration = item.runtime if item.runtime else 0`
        # `total_runtime_minutes += duration`
        # Wait, I might have messed up `get_stats` in Step 532 logic vs Plan logic?
        # Step 532 code content for get_stats: "duration = item.runtime if item.runtime else 0". Correct, removed multiplication.
        # Okay, so here just use `item.runtime`.
        
        total_minutes = sum([item.runtime or 0 for item in watched])
        hours = int(total_minutes / 60)
        
        # Determine Vibe (Top Genre)
        genres = []
        for item in watched:
            if item.genres:
                genres.extend([g.strip() for g in item.genres.split(',')])
        top_genre = Counter(genres).most_common(1)[0][0] if genres else "Newbie"
        
        leaderboard.append({
            "name": user.name,
            "picture": user.picture,
            "hours": hours,
            "vibe": top_genre
        })
    
    # Sort desc
    return sorted(leaderboard, key=lambda x: x['hours'], reverse=True)


# --- AUTH UTILS ---
from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class GoogleAuthRequest(BaseModel):
    credential: str # Google ID Token

def create_access_token(data: dict):
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# --- AUTH ROUTES ---
@app.post("/api/auth/google")
def google_login(request: GoogleAuthRequest, db: Session = Depends(get_db)):
    try:
        # Verify Google Token
        id_info = id_token.verify_oauth2_token(request.credential, google_requests.Request(), GOOGLE_CLIENT_ID)
        
        email = id_info['email']
        name = id_info.get('name', 'Unknown')
        picture = id_info.get('picture', '')
        
        # Find or Create User
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, name=name, picture=picture)
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Update info
            user.name = name
            user.picture = picture
            db.commit()
            
        # Issue JWT
        access_token = create_access_token(data={"sub": str(user.id)})
        return {"access_token": access_token, "user": {"name": user.name, "picture": user.picture}}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Google Token")

@app.put("/api/users/me")
def update_profile(request: ProfileUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.bio = request.bio
    if request.picture:
        current_user.picture = request.picture
    db.commit()
    return {"status": "updated", "bio": current_user.bio, "picture": current_user.picture}

@app.post("/api/users/upload-avatar")
async def upload_avatar(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    try:
        if not os.path.exists("static/uploads"):
            os.makedirs("static/uploads")
        
        # Safe filename
        filename = f"user_{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename}"
        filepath = os.path.join("static/uploads", filename)
        
        with open(filepath, "wb") as buffer:
            import shutil
            shutil.copyfileobj(file.file, buffer)
            
        # Return URL (Assuming server runs on root or proxied correctly. For local: /static/uploads/...)
        return {"url": f"/static/uploads/{filename}"}
    except Exception as e:
        logging.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")

@app.get("/api/users/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return {"name": current_user.name, "picture": current_user.picture, "bio": current_user.bio, "id": current_user.id}

# --- LEADERBOARD ---
@app.get("/api/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    # Aggregation: Get total runtime per user
    users = db.query(User).filter(User.is_public == True).all()
    leaderboard = []
    
    for user in users:
        # Calculate total watched hours
        watched = db.query(WatchHistory).filter(
            WatchHistory.user_id == user.id, 
            WatchHistory.status == 'watched'
        ).all()
        
        # Calculate total minutes (sum of item.runtime)
        total_minutes = sum([item.runtime or 0 for item in watched])
        hours = int(total_minutes / 60)
        
        # Determine Vibe (Top Genre)
        genres = []
        for item in watched:
            if item.genres:
                genres.extend([g.strip() for g in item.genres.split(',')])
        top_genre = Counter(genres).most_common(1)[0][0] if genres else "Newbie"
        
        leaderboard.append({
            "name": user.name,
            "picture": user.picture,
            "hours": hours,
            "vibe": top_genre
        })
    
    # Sort desc
    return sorted(leaderboard, key=lambda x: x['hours'], reverse=True)

# --- LOGIC: THE INTELLIGENCE LAYER ---
async def search_tmdb(title: str, year: str = None, media_type_hint: str = None):
    async with httpx.AsyncClient() as client:
        params = {"api_key": TMDB_API_KEY, "query": title}
        if year:
            params["year"] = year
            
        # Helper for requests
        async def check_endpoint(endpoint, type_label):
            response = await client.get(f"https://api.themoviedb.org/3/search/{endpoint}", params=params)
            data = response.json()
            if data.get('results'):
                return data['results'][0], type_label
            return None, None

        # Prioritize based on hint
        first_choice = ('tv', 'tv') if media_type_hint == 'tv' else ('movie', 'movie')
        second_choice = ('movie', 'movie') if media_type_hint == 'tv' else ('tv', 'tv')

        # Try First Choice
        res, m_type = await check_endpoint(first_choice[0], first_choice[1])
        if res: return res, m_type
        
        # Try Second Choice
        res, m_type = await check_endpoint(second_choice[0], second_choice[1])
        return res, m_type

async def get_tmdb_details(tmdb_id: int, media_type: str):
    async with httpx.AsyncClient() as client:
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}"
        # Fetch credits and keywords in one go
        params = {"api_key": TMDB_API_KEY, "append_to_response": "credits,keywords"}
        response = await client.get(url, params=params)
        return response.json()

@app.post("/api/log")
async def log_content(request: LogRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 0. Sanitize and Log
    clean_title = request.title.strip()
    logging.info(f"User {current_user.name} logging: '{clean_title}'")

    # 1. Enrich Data
    tmdb_result, media_type = await search_tmdb(clean_title, request.year, request.media_type)
    
    if not tmdb_result:
        raise HTTPException(status_code=404, detail="Content not found")

    # 1.5. Check for Duplicates (User Scoped)
    existing_entry = db.query(WatchHistory).filter(
        WatchHistory.tmdb_id == tmdb_result['id'],
        WatchHistory.user_id == current_user.id
    ).first()
    
    if existing_entry:
        return {"status": "success", "saved": existing_entry.title, "note": "Already in watchlist"}

    # 2. Get Details
    details = await get_tmdb_details(tmdb_result['id'], media_type)
    
    real_title = tmdb_result.get('title', tmdb_result.get('name'))
    release_date = tmdb_result.get('release_date', tmdb_result.get('first_air_date', ''))
    year = int(release_date[:4]) if release_date else None
    genres = ", ".join([g['name'] for g in details.get('genres', [])])
    
    # Extract Deep Metadata
    studios = [c['name'] for c in details.get('production_companies', [])]
    production_companies = ", ".join(studios[:3]) # Store top 3 studios
    
    credits = details.get('credits', {})
    cast_list = [c['name'] for c in credits.get('cast', [])[:5]] # Top 5 actors
    cast = ", ".join(cast_list)
    
    crew_list = [c['name'] for c in credits.get('crew', []) if c.get('job') in ['Director', 'Creator', 'Executive Producer']]
    crew = ", ".join(crew_list[:3]) # Top 3 key crew
    
    # TV vs Movie Keywords structure is slightly different
    k_key = 'results' if 'results' in details.get('keywords', {}) else 'keywords'
    keyword_list = [k['name'] for k in details.get('keywords', {}).get(k_key, [])]
    keywords = ", ".join(keyword_list[:10])

    # Countries
    c_list = [c['iso_3166_1'] for c in details.get('production_countries', [])]
    production_countries = ", ".join(c_list)

    # Logic for runtime
    runtime = 0
    total_episodes = 1
    
    if media_type == 'movie':
        runtime = details.get('runtime', 0)
    else:
        # TV Deep Scan logic (copied from previous, omitting full redundant block for brevity in tool call, but I must encompass it)
        # Actually I need to keep the full logic I just wrote previously.
        seasons = details.get('seasons', [])
        total_episodes = 0
        async with httpx.AsyncClient() as client:
            for season in seasons:
                if season['season_number'] == 0: continue
                try:
                    url_s = f"https://api.themoviedb.org/3/tv/{tmdb_result['id']}/season/{season['season_number']}"
                    res_s = await client.get(url_s, params={"api_key": TMDB_API_KEY})
                    if res_s.status_code == 200:
                        data_s = res_s.json()
                        eps = data_s.get('episodes', [])
                        for ep in eps:
                            if ep.get('runtime'):
                                runtime += ep['runtime']
                                total_episodes += 1
                except Exception:
                    pass

    # 3. Save to Watched (User Scoped)
    # Create Entry
    entry = WatchHistory(
        title=real_title,
        tmdb_id=tmdb_result['id'],
        media_type=media_type,
        poster_path=tmdb_result.get('poster_path'),
        status=request.status,
        user_id=current_user.id,
        # Use provided date if Watched, else None or Now
        watched_at=request.watched_at if request.status == 'watched' else None,
        # Metadata
        year=year,
        genres=genres,
        runtime=runtime,
        total_episodes=total_episodes,
        production_companies=production_companies,
        cast=cast,
        crew=crew,
        keywords=keywords,
        production_countries=production_countries,
        added_at=datetime.utcnow() # Keep added_at as creation time
    )
    
    db.add(entry)
    db.commit()
    return {"status": "success", "saved": real_title}

@app.put("/api/entry/{id}/status")
def update_status(id: int, request: UpdateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    entry = db.query(WatchHistory).filter(WatchHistory.tmdb_id == id, WatchHistory.user_id == current_user.id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    entry.status = request.status
    if request.status == 'watched':
        # Use provided date OR Now (if not already set)
        if request.watched_at:
             entry.watched_at = request.watched_at
        elif not entry.watched_at:
             entry.watched_at = datetime.utcnow()
    else:
        entry.watched_at = None
        
    db.commit()
    return {"status": "updated", "new_status": entry.status}

@app.delete("/api/entry/{id}")
def delete_entry(id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    entry = db.query(WatchHistory).filter(WatchHistory.tmdb_id == id, WatchHistory.user_id == current_user.id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    db.delete(entry)
    db.commit()
    return {"status": "deleted", "id": id}

@app.get("/api/history")
def get_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(WatchHistory).filter(WatchHistory.user_id == current_user.id).order_by(WatchHistory.added_at.desc()).all()

@app.get("/api/stats/sprint")
def get_biweekly_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Stats for last 14 days (The Sprint)"""
    cutoff = datetime.utcnow() - timedelta(days=14)
    # Get watched items in window
    recent = db.query(WatchHistory).filter(
        WatchHistory.user_id == current_user.id,
        WatchHistory.status == 'watched',
        WatchHistory.watched_at >= cutoff
    ).order_by(WatchHistory.watched_at.desc()).all()
    
    total_minutes = 0
    items = []
    
    for item in recent:
        total_minutes += (item.runtime or 0)
        items.append({
            "id": item.tmdb_id,
            "title": item.title,
            "type": item.media_type,
            "watched_at": item.watched_at,
            "poster_path": item.poster_path
        })
        
    return {
        "period": "Last 14 Days",
        "total_count": len(items),
        "total_minutes": total_minutes,
        "total_hours": round(total_minutes / 60, 1),
        "items": items
    }

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    history = db.query(WatchHistory).filter(WatchHistory.user_id == current_user.id).all()
    
    # 1. Counts & Basics
    watchlist_count = 0
    watched_count = 0
    movie_count = 0
    series_count = 0
    
    # 2. Aggregation
    total_runtime_minutes = 0
    movie_runtime_minutes = 0
    series_runtime_minutes = 0
    
    genre_counts = Counter()
    year_counts = Counter()
    
    year_counts = Counter()
    
    # Deep Analytics Counters
    studios_count = Counter()
    cast_count = Counter()
    crew_count = Counter()
    keywords_count = Counter()
    country_count = Counter()
    
    activity_log = {} # "YYYY-MM" -> count
    
    for item in history:
        # Status Counts
        if item.status == 'watched':
            watched_count += 1
        else:
            watchlist_count += 1
            
        if item.status != 'watched':
            continue

        if item.media_type == 'movie':
            movie_count += 1
        else:
            series_count += 1

        # Runtime
        r = item.runtime or 0
        total_runtime_minutes += r
        
        if item.media_type == 'movie':
            movie_runtime_minutes += r
        else:
            series_runtime_minutes += r
            
        # Genres
        if item.genres:
            for g in item.genres.split(','):
                genre_counts[g.strip()] += 1
                
        # Years
        if item.year:
            year_counts[item.year] += 1
            
        # Studios
        if item.production_companies:
            for s in item.production_companies.split(','):
                s = s.strip()
                if s: studios_count[s] += 1

        # Cast
        if item.cast:
            for c in item.cast.split(','):
                c = c.strip()
                if c: cast_count[c] += 1

        # Crew (Directors)
        if item.crew:
            for c in item.crew.split(','):
                c = c.strip()
                if c: crew_count[c] += 1

        # Keywords
        if item.keywords:
            for k in item.keywords.split(','):
                k = k.strip()
                if k: keywords_count[k] += 1

        # Countries
        if item.production_countries:
            for c in item.production_countries.split(','):
                c = c.strip()
                if c: country_count[c] += 1
            
        # Activity
        if item.watched_at:
            month_key = item.watched_at.strftime("%Y-%m")
            month_name = item.watched_at.strftime("%B")
            day_name = item.watched_at.strftime("%A")
            activity_log[month_key] = activity_log.get(month_key, 0) + 1
            
            # Temporal Stats
            # We need persistent trackers for these, defined outside loop
            # Check below loop
            
    # Computations for Temporal (moving out of loop for cleaner logic, but need accumulation)
    # Refactoring slightly to use Counters for Day/Month
    month_counts = Counter()
    day_counts = Counter()
    
    for item in history:
        if item.status == 'watched' and item.watched_at:
            month_counts[item.watched_at.strftime("%B")] += 1
            day_counts[item.watched_at.strftime("%A")] += 1

    # Computations
    avg_runtime = total_runtime_minutes / watched_count if watched_count > 0 else 0
    avg_time_to_watch_hours = (avg_runtime / 60)
    
    # Top Lists
    top_genres = genre_counts.most_common(5)
    top_years = year_counts.most_common(5)
    top_years = year_counts.most_common(5)
    top_studios = studios_count.most_common(5)
    top_cast = cast_count.most_common(5)
    top_crew = crew_count.most_common(5)
    top_keywords = keywords_count.most_common(10) # Increased to 10 for cloud
    
    top_month = month_counts.most_common(1)
    top_day = day_counts.most_common(1)
    
    # Sort Activity
    sorted_activity = sorted(activity_log.items())
    
    # Eras (Decades)
    decades = Counter()
    for y, count in year_counts.items():
        decade = (y // 10) * 10
        decades[f"{decade}s"] += count
    sorted_decades = sorted(decades.items())

    # --- TRIVIA ENGINE V2 ---
    trivia = []
    
    try:
        # 1. Temporal Tease
        if top_day:
             trivia.append(f"You love a good {top_day[0][0]} movie night.")
        
        # 2. Travel Tease
        top_country = country_count.most_common(1)
        if top_country:
            code = top_country[0][0]
            count = top_country[0][1]
            country_map = {"NG": "Lagos", "IN": "Mumbai", "US": "Hollywood", "KR": "Seoul", "JP": "Tokyo", "GB": "London", "FR": "Paris", "ES": "Madrid"}
            if code in country_map:
                 trivia.append(f"You watched {count} titles from {code}. Ready to move to {country_map[code]}?")
            else:
                 trivia.append(f"You're a fan of {code} cinema. Worldwide traveler!")

        # 3. Binge Tease
        if avg_time_to_watch_hours < 24:
            trivia.append("You devour content faster than a black hole.")
        elif avg_time_to_watch_hours > 720:
            trivia.append("You take your time. Like, a LOT of time.")
            
        # 4. Actor Tease
        top_actor = cast_count.most_common(1)
        if top_actor:
            actor = top_actor[0][0]
            a_count = top_actor[0][1]
            trivia.append(f"You've spent {a_count * 2} hours staring at {actor}. We won't judge.")

        # 5. Genre Roast
        if top_genres:
            top_g = top_genres[0][0]
            if top_g == "Horror": trivia.append("You like being scared? Who hurt you?")
            elif top_g == "Romance": trivia.append("Hopeless romantic detected.")
            elif top_g == "Science Fiction": trivia.append("Living in the future, are we?")
            elif top_g == "Documentary": trivia.append("You're here to learn, not to have fun.")
            
        # 6. Studio Stan
        if top_studios:
            top_s = top_studios[0][0]
            if "A24" in top_s: trivia.append("A24? You must be very distinctive.")
            elif "Marvel" in top_s: trivia.append("Marvel fan? Assemble.")

    except Exception:
        pass
        
    return {
        "counts": {
            "watchlist": watchlist_count,
            "watched": watched_count,
            "movies": movie_count,
            "series": series_count
        },
        "total_runtime_minutes": total_runtime_minutes,
        "avg_runtime": avg_runtime,
        "top_genres": top_genres,
        "top_years": top_years,
        "top_studios": top_studios,
        "top_cast": top_cast,
        "top_crew": top_crew,
        "top_countries": country_count.most_common(10),
        "top_keywords": top_keywords,
        "activity_log": sorted_activity,
        "decades": sorted_decades,
        "trivia": trivia,
        "top_month": top_month[0] if top_month else ("None", 0),
        "top_day": top_day[0] if top_day else ("None", 0)
    }

@app.get("/api/stats/details")
def get_stats_details(category: str, value: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Drill-down endpoint
    query = db.query(WatchHistory).filter(WatchHistory.user_id == current_user.id).filter(WatchHistory.status == 'watched')
    
    value = value.lower()
    
    # We must fetch all and filter in python because comma-separated strings are hard to exact-match in SQL LIKE efficiently for this simple DB structure
    # Actually LIKE %value% is fine for now
    
    if category == 'cast':
        query = query.filter(WatchHistory.cast.ilike(f"%{value}%"))
    elif category == 'studio':
        query = query.filter(WatchHistory.production_companies.ilike(f"%{value}%"))
    elif category == 'genre':
        query = query.filter(WatchHistory.genres.ilike(f"%{value}%"))
    elif category == 'country':
        query = query.filter(WatchHistory.production_countries.ilike(f"%{value}%"))
    elif category == 'crew':
        query = query.filter(WatchHistory.crew.ilike(f"%{value}%"))
        
    results = query.all()
    # Return limited fields to save bandwidth? No, renderCard needs full object usually.
    return results



    return {
        "counts": {
            "watchlist": watchlist_count,
            "watched": watched_count,
            "movies": movie_count,
            "series": series_count
        },
        "avg_hours_to_watch": round(avg_time_to_watch_hours, 2),
        "total_runtime_minutes": total_runtime_minutes,
        "split_runtime": {
            "movies": movie_runtime_minutes,
            "series": series_runtime_minutes
        },
        "top_genres": top_genres,
        "top_years": top_years,
        "top_studios": top_studios,
        "top_cast": top_cast,
        "top_keywords": top_keywords,
        "top_countries": country_count.most_common(5),
        "trivia": trivia,
        "monthly_activity": sorted_activity,
        "decade_distribution": sorted_decades
    }


@app.get("/api/recommendations")
async def get_recommendations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # --- STRATEGY: CONCEPT INTERSECTION ---
    # Goal: "Because you watched X and Y"
    
    # 1. Gather Seeds (Broaden the net)
    full_history = db.query(WatchHistory).filter(WatchHistory.user_id == current_user.id).all()
    if not full_history:
        return await fetch_trending_content()

    seen_ids = {h.tmdb_id for h in full_history}
    
    # Priority Seeds:
    # - 5 Most Recent
    # - 3 Highest Rated (Favorites)
    # - 2 Random Discovery
    
    sorted_by_date = sorted(full_history, key=lambda x: x.watched_at or x.added_at or datetime.min, reverse=True)
    favorites = sorted([h for h in full_history if h.rating and h.rating >= 4], key=lambda x: x.rating, reverse=True)
    
    seeds = []
    seeds.extend(sorted_by_date[:5])
    seeds.extend(favorites[:3])
    
    import random
    if len(full_history) > 10:
        remaining = [h for h in full_history if h not in seeds]
        if remaining:
            seeds.extend(random.sample(remaining, min(2, len(remaining))))
            
    # Remove duplicates from seeds list while preserving order
    unique_seeds = []
    seen_seed_ids = set()
    for s in seeds:
        if s.tmdb_id not in seen_seed_ids:
            unique_seeds.append(s)
            seen_seed_ids.add(s.tmdb_id)
    
    # 2. Fetch & Intersect
    candidates = {} # tmdb_id -> { count, data, sources: [] }

    async with httpx.AsyncClient() as client:
        # Fetch in parallel? For now sequential loop is safer for rate limits, or use limited concurrency.
        # TMDB doesn't like huge bursts. Sequential is fine for ~10 requests.
        for item in unique_seeds:
            try:
                url = f"https://api.themoviedb.org/3/{item.media_type}/{item.tmdb_id}/recommendations"
                res = await client.get(url, params={"api_key": TMDB_API_KEY})
                if res.status_code == 200:
                    results = res.json().get('results', [])
                    # Filter poor quality
                    results = [r for r in results if r.get('vote_average', 0) >= 6.0] 
                    
                    for rec in results[:10]: # Analyze top 10 from each seed
                        mid = rec['id']
                        if mid in seen_ids: continue
                        
                        if mid not in candidates:
                            candidates[mid] = {
                                'data': rec,
                                'count': 0,
                                'sources': [],
                                'score': rec.get('vote_average', 0)
                            }
                        
                        candidates[mid]['count'] += 1
                        candidates[mid]['sources'].append(item.title)
                        
            except Exception:
                pass
                
        # 3. Trending Fill (if low candidates)
        if len(candidates) < 10:
            try:
                url = "https://api.themoviedb.org/3/trending/all/week"
                res = await client.get(url, params={"api_key": TMDB_API_KEY})
                if res.status_code == 200:
                    trending = res.json().get('results', [])
                    for t in trending:
                        if t['id'] not in seen_ids and t['id'] not in candidates:
                             candidates[t['id']] = {
                                'data': t,
                                'count': 1,
                                'sources': ['Global Trends'], # Special source
                                'score': t.get('vote_average', 0) * 1.1 # Boost slightly
                            }
            except Exception:
                pass

    # 3. Scoring & Formatting
    final_list = []
    
    # Algorithm: Boost by Count
    # Score = VoteAvg * (1 + (Count - 1) * 0.5)
    # Count 1: 8.0 * 1 = 8.0
    # Count 2: 8.0 * 1.5 = 12.0
    # Count 3: 8.0 * 2.0 = 16.0
    
    for mid, info in candidates.items():
        count_boost = 1 + (info['count'] - 1) * 0.5
        final_score = info['score'] * count_boost
        
        # Format Reason
        sources = info['sources']
        if 'Global Trends' in sources:
            reason = "Trending Globally"
        else:
            # removing dupes from sources list
            sources = list(set(sources))
            if len(sources) == 1:
                reason = f"Because you watched {sources[0]}"
            elif len(sources) == 2:
                reason = f"Because you watched {sources[0]} and {sources[1]}"
            elif len(sources) > 2:
                reason = f"Because you watched {sources[0]}, {sources[1]} and others"
            else:
                reason = "Recommended for you"
                
        rec_item = info['data']
        rec_item['reason'] = reason
        rec_item['match_score'] = final_score # Internal debug
        
        # Ensure media_type is set (Trending results have it, specific endpoints might not?)
        # Recommendations endpoint usually does NOT include media_type field in results if fetched from /movie/{id}/recommendations (it's implicit).
        # We must infer or check.
        if 'media_type' not in rec_item:
             # Heuristic: if title exists, likely movie. name exists, likely tv.
             if 'title' in rec_item: rec_item['media_type'] = 'movie'
             elif 'name' in rec_item: rec_item['media_type'] = 'tv'
             
        final_list.append(rec_item)

    # Sort by Final Score Descending
    final_list.sort(key=lambda x: x['match_score'], reverse=True)
    
    return final_list[:18]

async def fetch_trending_content():
    async with httpx.AsyncClient() as client:
        url = "https://api.themoviedb.org/3/trending/all/week"
        res = await client.get(url, params={"api_key": TMDB_API_KEY})
        return res.json().get('results', [])[:12] if res.status_code == 200 else []

# --- SOCIAL API ---
@app.post("/api/social/follow/{user_id}")
def follow_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
        
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
        
    existing = db.query(Follower).filter(Follower.follower_id == current_user.id, Follower.followed_id == user_id).first()
    if existing:
        return {"status": "already_following"}
        
    new_follow = Follower(follower_id=current_user.id, followed_id=user_id)
    db.add(new_follow)
    db.commit()
    return {"status": "followed", "user": target.name}

@app.post("/api/social/unfollow/{user_id}")
def unfollow_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing = db.query(Follower).filter(Follower.follower_id == current_user.id, Follower.followed_id == user_id).first()
    if existing:
        db.delete(existing)
        db.commit()
    return {"status": "unfollowed"}

@app.get("/api/social/search")
def search_users(q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not q: return []
    # Simple logic: users matching name/email who are public
    users = db.query(User).filter(
        (User.name.ilike(f"%{q}%")) | (User.email.ilike(f"%{q}%")),
        User.id != current_user.id,
        User.is_public == True
    ).limit(10).all()
    
    # Check following status
    following_ids = {f.followed_id for f in current_user.following}
    
    results = []
    for u in users:
        results.append({
            "id": u.id,
            "name": u.name,
            "picture": u.picture,
            "is_following": u.id in following_ids
        })
    return results

@app.get("/api/social/following")
def get_following(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get list of users I follow"""
    results = []
    for f in current_user.following:
        u = f.followed
        if u:
             results.append({
                "id": u.id,
                "name": u.name,
                "picture": u.picture
            })
    return results



# --- INTERACTION API ---
def create_notification(db, user_id, type, message, ref_id=None):
    if not user_id: return
    n = Notification(user_id=user_id, type=type, message=message, ref_id=ref_id)
    db.add(n)
    db.commit()

@app.post("/api/social/like/{history_id}")
def toggle_like(history_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(WatchHistory).filter(WatchHistory.id == history_id).first()
    if not item: raise HTTPException(404, "Item not found")
    
    existing = db.query(Like).filter(Like.user_id == current_user.id, Like.history_id == history_id).first()
    
    if existing:
        db.delete(existing)
        status = "unliked"
    else:
        new_like = Like(user_id=current_user.id, history_id=history_id)
        db.add(new_like)
        status = "liked"
        # Notify owner if not self
        if item.user_id != current_user.id:
            create_notification(db, item.user_id, 'like', f"{current_user.name} liked your watch of {item.title}", history_id)
            
    db.commit()
    return {"status": status}

@app.post("/api/social/comment/{history_id}")
def add_comment(history_id: int, request: CommentRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(WatchHistory).filter(WatchHistory.id == history_id).first()
    if not item: raise HTTPException(404, "Item not found")
    
    comment = Comment(user_id=current_user.id, history_id=history_id, content=request.content)
    db.add(comment)
    db.commit()
    
    # Notify
    if item.user_id != current_user.id:
        create_notification(db, item.user_id, 'comment', f"{current_user.name} roasted: {request.content}", history_id)
        
    return {"status": "commented"}

@app.get("/api/notifications")
def get_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    notifs = db.query(Notification).filter(Notification.user_id == current_user.id, Notification.read == False).order_by(Notification.created_at.desc()).all()
    return [{"message": n.message, "type": n.type, "created_at": n.created_at} for n in notifs]

@app.post("/api/notifications/clear")
def clear_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.query(Notification).filter(Notification.user_id == current_user.id, Notification.read == False).update({"read": True})
    db.commit()
    return {"status": "cleared"}

@app.get("/api/social/feed")
def get_friend_feed(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 1. Get IDs of people I follow
    following_ids = [f.followed_id for f in current_user.following]
    if not following_ids:
        return []
        
    # 2. Get their recent watch history
    feed = db.query(WatchHistory).filter(
        WatchHistory.user_id.in_(following_ids),
        WatchHistory.status == 'watched'
    ).order_by(WatchHistory.watched_at.desc()).limit(20).all()
    
    # 3. Format with interaction data
    result = []
    for item in feed:
        # Check if I liked it
        # This is N+1 query, but fine for MVP (limit 20)
        is_liked = db.query(Like).filter(Like.user_id == current_user.id, Like.history_id == item.id).first() is not None
        like_count = db.query(Like).filter(Like.history_id == item.id).count()
        comments = db.query(Comment).filter(Comment.history_id == item.id).order_by(Comment.created_at.asc()).all()
        
        c_list = [{"user": c.user.name, "content": c.content} for c in comments]
        
        result.append({
            "id": item.id, 
            "user_name": item.user.name,
            "user_picture": item.user.picture,
            "title": item.title,
            "poster_path": item.poster_path,
            "rating": 5, 
            "date": item.watched_at.isoformat() if item.watched_at else None,
            "is_liked": is_liked,
            "like_count": like_count,
            "comments": c_list
        })
    return result

    return result

# --- INTERACTION API ---
def create_notification(db, user_id, type, message, ref_id=None):
    if not user_id: return
    n = Notification(user_id=user_id, type=type, message=message, ref_id=ref_id)
    db.add(n)
    db.commit()

@app.post("/api/social/like/{history_id}")
def toggle_like(history_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(WatchHistory).filter(WatchHistory.id == history_id).first()
    if not item: raise HTTPException(404, "Item not found")
    
    existing = db.query(Like).filter(Like.user_id == current_user.id, Like.history_id == history_id).first()
    
    if existing:
        db.delete(existing)
        status = "unliked"
    else:
        new_like = Like(user_id=current_user.id, history_id=history_id)
        db.add(new_like)
        status = "liked"
        # Notify owner if not self
        if item.user_id != current_user.id:
            create_notification(db, item.user_id, 'like', f"{current_user.name} liked your watch of {item.title}", history_id)
            
    db.commit()
    return {"status": status}

@app.post("/api/social/comment/{history_id}")
def add_comment(history_id: int, request: CommentRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(WatchHistory).filter(WatchHistory.id == history_id).first()
    if not item: raise HTTPException(404, "Item not found")
    
    comment = Comment(user_id=current_user.id, history_id=history_id, content=request.content)
    db.add(comment)
    db.commit()
    
    # Notify
    if item.user_id != current_user.id:
        create_notification(db, item.user_id, 'comment', f"{current_user.name} roasted: {request.content}", history_id)
        
    return {"status": "commented"}

@app.get("/api/notifications")
def get_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    notifs = db.query(Notification).filter(Notification.user_id == current_user.id, Notification.read == False).order_by(Notification.created_at.desc()).all()
    return [{"message": n.message, "type": n.type, "created_at": n.created_at} for n in notifs]

@app.post("/api/notifications/clear")
def clear_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.query(Notification).filter(Notification.user_id == current_user.id, Notification.read == False).update({"read": True})
    db.commit()
    return {"status": "cleared"}

@app.get("/api/social/feed")
def get_friend_feed(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 1. Get IDs of people I follow
    following_ids = [f.followed_id for f in current_user.following]
    # Include self for testing if list is empty? No, strict following.
    if not following_ids:
        return []
        
    # 2. Get their recent watch history
    feed = db.query(WatchHistory).filter(
        WatchHistory.user_id.in_(following_ids),
        WatchHistory.status == 'watched'
    ).order_by(WatchHistory.watched_at.desc()).limit(20).all()
    
    # 3. Format with interaction data
    result = []
    for item in feed:
        # Check if I liked it
        # This is N+1 query, but fine for MVP (limit 20)
        is_liked = db.query(Like).filter(Like.user_id == current_user.id, Like.history_id == item.id).first() is not None
        like_count = db.query(Like).filter(Like.history_id == item.id).count()
        comments = db.query(Comment).filter(Comment.history_id == item.id).order_by(Comment.created_at.asc()).all()
        
        c_list = [{"user": c.user.name, "content": c.content} for c in comments]
        
        result.append({
            "id": item.id, # Internal DB ID needed for interactions
            "user_name": item.user.name,
            "user_picture": item.user.picture,
            "title": item.title,
            "poster_path": item.poster_path,
            "rating": 5, 
            "date": item.watched_at.isoformat() if item.watched_at else None,
            "is_liked": is_liked,
            "like_count": like_count,
            "comments": c_list
        })
    return result
    
if __name__ == "__main__":
    import uvicorn
    import threading
    import sys
    
    try:
        # Run maintenance on startup
        run_migrations()
        threading.Thread(target=repair_data).start()
        
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except Exception as e:
        print(f"Server Startup Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()