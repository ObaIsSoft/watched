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
# Force print for debugging
print("Logger initialized")
from jose import jwt, JWTError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# --- LOGGING SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(
    filename=os.path.join(BASE_DIR, 'server.log'), 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- CONFIGURATION ---
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "331904c8f8fb8f3fbe3e59cf24566a89")
SECRET_KEY = os.environ.get("SECRET_KEY", "my_super_secret_key_change_me_in_prod")
ALGORITHM = "HS256"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "725965614246-s6r1sh4m1i9mocm8pa5ag1e67asd2ev3.apps.googleusercontent.com")
 

# --- DATABASE SETUP (SQLite) ---
# --- DATABASE SETUP ---
# Render/Production provides DATABASE_URL. Local uses SQLite.
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'watched_history.db')}")

# Fix for Render: Postgres URLs must start with postgresql:// not postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    picture = Column(String)
    bio = Column(String, default="")
    is_public = Column(Boolean, default=True)
    
    history = relationship("WatchHistory", back_populates="user")
    
    # Relationships for Social
    followers = relationship("Follower", foreign_keys="Follower.followed_id", back_populates="followed")
    following = relationship("Follower", foreign_keys="Follower.follower_id", back_populates="follower")
    
    notifications = relationship("Notification", back_populates="user")
    
    # Location
    city = Column(String, nullable=True)
    country = Column(String, nullable=True)

# --- Database Setup & Migration ---

app = FastAPI()

# Allow CORS for Extension and Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for now to debug extension issues
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


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
    ref_id = Column(Integer, nullable=True)
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
    rating = Column(Integer, default=0) # 0=Unrated, 1-5 Stars
    
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
# --- MIGRATION UTILS ---
from sqlalchemy import text, inspect

def run_migrations():
    # Robust migration that works on both SQLite and Postgres
    inspector = inspect(engine)
    conn = engine.connect()
    try:
        # Check History Table
        if inspector.has_table("history"):
             columns = [c['name'] for c in inspector.get_columns("history")]
             
             # Base cols
             if 'total_episodes' not in columns:
                 logging.info("Migrating DB: Adding total_episodes column")
                 conn.execute(text("ALTER TABLE history ADD COLUMN total_episodes INTEGER DEFAULT 1"))
                 
             if 'rating' not in columns:
                 print("Migrating DB: Adding rating column")
                 conn.execute(text("ALTER TABLE history ADD COLUMN rating INTEGER DEFAULT 0"))
             
             if 'user_id' not in columns:
                 logging.info("Migrating DB: Adding user_id column")
                 conn.execute(text("ALTER TABLE history ADD COLUMN user_id INTEGER REFERENCES users(id)")) # Standard SQL

             # Metadata Migrations
             new_cols = ['production_companies', 'cast', 'crew', 'keywords', 'production_countries']
             for col in new_cols:
                 if col not in columns:
                     logging.info(f"Migrating DB: Adding {col} column")
                     # Postgres uses VARCHAR/TEXT, SQLite is loose. 'VARCHAR' is safe.
                     conn.execute(text(f"ALTER TABLE history ADD COLUMN {col} VARCHAR"))
                     
        # Check Users Table
        if inspector.has_table("users"):
             u_cols = [c['name'] for c in inspector.get_columns("users")]
             
             if 'bio' not in u_cols:
                 logging.info("Migrating DB: Adding bio column to users")
                 conn.execute(text("ALTER TABLE users ADD COLUMN bio VARCHAR DEFAULT ''"))
                 
             if 'city' not in u_cols:
                 logging.info("Migrating DB: Adding city column to users")
                 conn.execute(text("ALTER TABLE users ADD COLUMN city VARCHAR"))
 
             if 'country' not in u_cols:
                 logging.info("Migrating DB: Adding country column to users")
                 conn.execute(text("ALTER TABLE users ADD COLUMN country VARCHAR"))

        # Check Notifications Table
        if inspector.has_table("notifications"):
             n_cols = [c['name'] for c in inspector.get_columns("notifications")]
             if 'ref_id' not in n_cols:
                 logging.info("Migrating DB: Adding ref_id column to notifications")
                 conn.execute(text("ALTER TABLE notifications ADD COLUMN ref_id INTEGER"))

        conn.commit()
    except Exception as e:
        print(f"Migration Warning: {e}")
    finally:
        conn.close()

# Create Tables
Base.metadata.create_all(bind=engine)
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

        print(f"Scanning {len(entries)} entries for maintenance (Runtime & Metadata)...")
        
        for entry in entries:
            # Check if metadata is missing (including countries)
            needs_metadata = not (entry.production_companies and entry.cast and entry.keywords and entry.production_countries)
            
            # Check if runtime is missing (for ANY type)
            needs_runtime = (entry.runtime is None or entry.runtime == 0)

            if not (needs_metadata or needs_runtime):
                continue

            print(f"Backfilling data for: {entry.title}")
            
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

                    # 2. Update Runtime
                    if entry.media_type == 'tv':
                        seasons = details.get('seasons', [])
                        total_min, total_eps = get_series_runtime_sync(entry.tmdb_id, seasons)
                        if total_min > 0:
                            entry.runtime = total_min
                            entry.total_episodes = total_eps
                    else:
                        # Movie
                        entry.runtime = details.get('runtime', 0)
                    
                    db.commit()
                    
            except Exception as e:
                logging.error(f"Failed to backfill {entry.title}: {e}")
                
    except Exception as e:
        logging.error(f"Maintenance failed: {e}")
    finally:
        db.close()






class LogRequest(BaseModel):
    title: str
    media_type: Optional[str] = 'movie'
    status: str = 'watchlist'
    rating: int = 0
    year: Optional[str] = None
    watched_at: Optional[datetime] = None
    tmdb_id: Optional[int] = None

class UpdateRequest(BaseModel):
    status: str # 'watched'
    watched_at: datetime | None = None

class CommentRequest(BaseModel):
    content: str
    
class ProfileUpdate(BaseModel):
    bio: str
    picture: Optional[str] = None
    name: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open(os.path.join(BASE_DIR, "templates/dashboard.html"), "r") as f:
        return f.read()

@app.get("/privacy", response_class=HTMLResponse)
def read_privacy():
    with open(os.path.join(BASE_DIR, "templates/privacy.html"), "r") as f:
        return f.read()

@app.get("/login", response_class=HTMLResponse)
def read_login():
    with open(os.path.join(BASE_DIR, "templates/login.html"), "r") as f:
        return f.read()

@app.get("/history", response_class=HTMLResponse)
def read_history():
    with open(os.path.join(BASE_DIR, "templates/dashboard.html"), "r") as f:
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
    # Uniqueness Check
    if request.name and request.name != current_user.name:
        existing = db.query(User).filter(User.name == request.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        current_user.name = request.name
        
    current_user.bio = request.bio
    if request.picture:
        current_user.picture = request.picture
    
    # Update Location
    if request.city is not None:
        current_user.city = request.city
    if request.country is not None:
        current_user.country = request.country
        
    db.commit()
    return {
        "status": "updated", 
        "bio": current_user.bio, 
        "picture": current_user.picture, 
        "name": current_user.name,
        "city": current_user.city,
        "country": current_user.country
    }

# --- EXPORT ---
import csv
import io
from fastapi.responses import StreamingResponse

@app.get("/api/export")
def export_data(type: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # type: 'watchlist' or 'history'
    
    stream = io.StringIO()
    writer = csv.writer(stream)
    
    if type == 'watchlist':
        items = db.query(WatchHistory).filter(
            WatchHistory.user_id == current_user.id,
            WatchHistory.status == 'watchlist'
        ).all()
        writer.writerow(["Title", "Year", "Type", "Added At"])
        for item in items:
            writer.writerow([item.title, item.year, item.media_type, item.added_at])
            
        filename = "watchlist_export.csv"
        
    elif type == 'history':
        items = db.query(WatchHistory).filter(
            WatchHistory.user_id == current_user.id,
            WatchHistory.status == 'watched'
        ).all()
        writer.writerow(["Title", "Year", "Type", "Rating", "Watched At", "Runtime (m)", "Genres"])
        for item in items:
            writer.writerow([
                item.title, 
                item.year, 
                item.media_type, 
                item.rating, 
                item.watched_at, 
                item.runtime,
                item.genres
            ])
            
        filename = "watched_history_export.csv"
    
    else:
        raise HTTPException(status_code=400, detail="Invalid export type")
    
    stream.seek(0)
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

# --- Social Feed Logic for Single Item (Notifications) ---
@app.get("/api/social/feed/{history_id}")
def get_feed_item(history_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(WatchHistory).filter(WatchHistory.id == history_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    is_liked = db.query(Like).filter(Like.user_id == current_user.id, Like.history_id == item.id).first() is not None
    like_count = db.query(Like).filter(Like.history_id == item.id).count()
    comments = db.query(Comment).filter(Comment.history_id == item.id).order_by(Comment.created_at.asc()).all()
    
    c_list = [{"user": c.user.name, "content": c.content} for c in comments]
    
    return {
        "id": item.id, 
        "user_name": item.user.name,
        "user_picture": item.user.picture,
        "title": item.title,
        "poster_path": item.poster_path,
        "rating": item.rating,
        "date": item.watched_at.isoformat() if item.watched_at else None,
        "is_liked": is_liked,
        "like_count": like_count,
        "comments": c_list
    }

@app.post("/api/users/upload-avatar")
async def upload_avatar(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    try:
        upload_dir = os.path.join(BASE_DIR, "static/uploads")
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        
        # Safe filename
        filename = f"user_{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename}"
        filepath = os.path.join(upload_dir, filename)
        
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
def get_leaderboard(scope: str = "global", genre: str = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Scope check
    query = db.query(User).filter(User.is_public == True)
    
    if scope == 'friends':
        friend_ids = db.query(Follower.followed_id).filter(Follower.follower_id == current_user.id).subquery()
        query = query.filter(or_(User.id == current_user.id, User.id.in_(friend_ids)))
    elif scope == 'city':
        if not current_user.city: return [] 
        query = query.filter(User.city == current_user.city, User.city.isnot(None))
    elif scope == 'country':
        if not current_user.country: return []
        query = query.filter(User.country == current_user.country, User.country.isnot(None))
        
    users = query.all()
    leaderboard = []
    
    for user in users:
        # Filter WatchHistory by Genre if requested
        history_query = db.query(WatchHistory).filter(
            WatchHistory.user_id == user.id, 
            WatchHistory.status == 'watched'
        )
        
        if genre and genre != "All":
            # Loose string matching for genre
            history_query = history_query.filter(WatchHistory.genres.ilike(f"%{genre}%"))
            
        watched = history_query.all()
        
        if not watched and genre: continue # Skip user if no history for this genre
        
        total_minutes = sum([item.runtime or 0 for item in watched])
        hours = int(total_minutes / 60)
        
        # Determine Vibe (Top Genre) - Recalculate based on filtered view or global?
        # Let's show their Vibe for *this specific genre* (likely the genre itself) or global vibe?
        # User output expects "Vibe". If filtered by Sci-Fi, Vibe is likely Sci-Fi. 
        # But showing their overall persona is maybe more interesting? 
        # Let's keep global vibe calculation for context, or just empty if filtered.
        # Actually, let's just grab their top genre from the *filtered* list to see specifically what sub-genre they like?
        # No, let's keep it simple: Vibe = Top Genre of the filtered set.
        
        genres_list = []
        for item in watched:
            if item.genres:
                genres_list.extend([g.strip() for g in item.genres.split(',')])
        top_genre = Counter(genres_list).most_common(1)[0][0] if genres_list else "Newbie"
        
        leaderboard.append({
            "name": user.name,
            "picture": user.picture,
            "hours": hours,
            "vibe": top_genre,
            "city": user.city or "",
            "country": user.country or ""
        })
    
    # Sort desc
    return sorted(leaderboard, key=lambda x: x['hours'], reverse=True)[:100]

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

@app.get("/api/tmdb/search")
async def api_search_tmdb(q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not q: return []
    async with httpx.AsyncClient() as client:
        params = {"api_key": TMDB_API_KEY, "query": q}
        
        # Parallel fetch movie and tv? Or just multi-search? 
        # TMDB has multi.
        url = "https://api.themoviedb.org/3/search/multi"
        res = await client.get(url, params=params)
        if res.status_code == 200:
            data = res.json()
            return [
                x for x in data.get('results', []) 
                if x.get('media_type') in ['movie', 'tv']
            ]
        return []

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
    if request.tmdb_id:
        tmdb_result = {"id": request.tmdb_id, "title": request.title, "name": request.title} # Minimal mock, details will fetch rest
        media_type = request.media_type
    else:
        tmdb_result, media_type = await search_tmdb(clean_title, request.year, request.media_type)
    
    if not tmdb_result:
        raise HTTPException(status_code=404, detail="Content not found")

    # 1.5. Check for Duplicates (User Scoped)
    existing_entry = db.query(WatchHistory).filter(
        WatchHistory.tmdb_id == tmdb_result['id'],
        WatchHistory.user_id == current_user.id
    ).first()
    
    if existing_entry:
        if request.status == 'watched' and existing_entry.status == 'watchlist':
             # Allow upscaling from watchlist to watched
             pass 
        else:
             return {"status": "success", "saved": existing_entry.title, "note": "Already in library"}

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

@app.put("/api/log/{tmdb_id}/rating")
def update_rating(tmdb_id: int, rating: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(WatchHistory).filter(
        WatchHistory.tmdb_id == tmdb_id,
        WatchHistory.user_id == current_user.id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    if rating < 0 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 0-5")
        
    item.rating = rating
    db.commit()
    return {"status": "updated", "rating": rating}

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
            
            # Daily Map for Heatmap
            daily_key = item.watched_at.strftime("%Y-%m-%d")
            # We need a persistent counter for this, initializing outside loop
            
    # Computations for Temporal (moving out of loop for cleaner logic)
    month_counts = Counter()
    day_counts = Counter()
    daily_activity_map = {} # YYYY-MM-DD -> count
    
    for item in history:
        if item.status == 'watched' and item.watched_at:
            month_counts[item.watched_at.strftime("%B")] += 1
            day_counts[item.watched_at.strftime("%A")] += 1
            # Heatmap Data
            d_key = item.watched_at.strftime("%Y-%m-%d")
            daily_activity_map[d_key] = daily_activity_map.get(d_key, 0) + 1

    # Computations
    print(f"DEBUG: Total Runtime Minutes: {total_runtime_minutes} | Watched Count: {watched_count}")
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

        # 3. New Analytics
        # Completion Rate
        total_items = watched_count + watchlist_count
        completion_rate = round((watched_count / total_items * 100)) if total_items > 0 else 0
        
        # Rating Stats
        rated_items = [i.rating for i in history if i.status == 'watched' and i.rating > 0]
        avg_rating = round(sum(rated_items) / len(rated_items), 1) if rated_items else 0
        perfect_scores = len([r for r in rated_items if r == 5])
        
        # Runtime Distribution buckets
        runtime_dist = {"Short (<90m)": 0, "Medium (90-120m)": 0, "Long (>120m)": 0}
        for item in history:
            if item.status == 'watched' and item.media_type == 'movie' and item.runtime:
                if item.runtime < 90: runtime_dist["Short (<90m)"] += 1
                elif item.runtime <= 120: runtime_dist["Medium (90-120m)"] += 1
                else: runtime_dist["Long (>120m)"] += 1
                
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
            "series": series_count,
            "completion_rate": locals().get('completion_rate', 0),
            "avg_rating": locals().get('avg_rating', 0),
            "perfect_scores": locals().get('perfect_scores', 0)
        },
        "avg_hours_to_watch": round(avg_time_to_watch_hours, 2),
        "total_runtime_minutes": total_runtime_minutes,
        "split_runtime": {
            "movies": movie_runtime_minutes,
            "series": series_runtime_minutes
        },
        "runtime_distribution": locals().get('runtime_dist', {}),
        "daily_activity": daily_activity_map,
        "top_genres": top_genres,
        "top_years": top_years,
        "top_studios": top_studios,
        "top_cast": top_cast,
        "top_crew": top_crew,
        "top_countries": country_count.most_common(10),
        "top_keywords": top_keywords,
        "monthly_activity": sorted_activity,
        "decade_distribution": sorted_decades,
        "trivia": trivia,
        "top_month": top_month[0] if top_month else ("None", 0),
        "top_day": top_day[0] if top_day else ("None", 0)
    }

@app.get("/api/stats/details")
def get_stats_details(category: str, value: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Drill-down endpoint
    query = db.query(WatchHistory).filter(WatchHistory.user_id == current_user.id).filter(WatchHistory.status == 'watched')
    
    value = value.lower()
    
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
    return results


@app.get("/api/recommendations")
async def get_recommendations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # --- STRATEGY: CONCEPT INTERSECTION ---
    # Goal: "Because you watched X and Y"
    
    # 1. Gather Seeds (Broaden the net)
    full_history = db.query(WatchHistory).filter(WatchHistory.user_id == current_user.id).all()
    if not full_history:
        return await fetch_trending_content()

    seen_lookup = set()
    for h in full_history:
        # Robustly handle ID types and ensure media_type consistency
        try:
            tid = int(h.tmdb_id)
            mtype = (h.media_type or 'movie').lower()
            seen_lookup.add((tid, mtype))
        except:
            pass
    
    # Priority Seeds:
    sorted_by_date = sorted(full_history, key=lambda x: x.watched_at or x.added_at or datetime.min, reverse=True)
    favorites = sorted([h for h in full_history if h.status == 'watched'], key=lambda x: x.watched_at or datetime.min, reverse=True)
    
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
        for item in unique_seeds:
            try:
                # Infer type for endpoint
                seed_type = (item.media_type or 'movie').lower()
                url = f"https://api.themoviedb.org/3/{seed_type}/{item.tmdb_id}/recommendations"
                res = await client.get(url, params={"api_key": TMDB_API_KEY})
                if res.status_code == 200:
                    results = res.json().get('results', [])
                    # Filter poor quality
                    results = [r for r in results if r.get('vote_average', 0) >= 6.0] 
                    
                    for rec in results[:10]: # Analyze top 10 from each seed
                        mid = rec['id']
                        # Recs from a movie endpoint are movies, etc.
                        rec_type = seed_type 
                        
                        # Strict Filter
                        if (mid, rec_type) in seen_lookup: continue
                        
                        if mid not in candidates:
                            # Inject media_type if missing (TMDB specific endpoints don't always return it)
                            if 'media_type' not in rec: rec['media_type'] = rec_type
                            
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
                        mt = t.get('media_type', 'movie')
                        if (t['id'], mt) not in seen_lookup and t['id'] not in candidates:
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
        logging.info(f"Posting notification for user {item.user_id} from {current_user.name}")
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
    # 1. Get IDs of people I follow AND myself (so I can see replies to my own stuff)
    following_ids = [f.followed_id for f in current_user.following]
    following_ids.append(current_user.id)
    
    # 2. Get their recent watch history
    feed = db.query(WatchHistory).filter(
        WatchHistory.user_id.in_(following_ids),
        WatchHistory.status == 'watched'
    ).order_by(WatchHistory.watched_at.desc()).limit(30).all()
    
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
    
# Serve Templates (Last to avoid overriding API)
from fastapi.responses import FileResponse, RedirectResponse

# Explicit Routes for robustness
@app.get("/login")
@app.get("/login.html")
async def serve_login():
    return FileResponse(os.path.join(BASE_DIR, "templates/login.html"))

@app.get("/dashboard")
@app.get("/dashboard.html")
async def serve_dashboard():
    return FileResponse(os.path.join(BASE_DIR, "templates/dashboard.html"))

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard.html")

# Serve other static assets (if any) from template dir as fallback, or strict static


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