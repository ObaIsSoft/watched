import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import WatchHistory, User

engine = create_engine('sqlite:///./watchlist.db')
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

history = db.query(WatchHistory).filter(WatchHistory.crew.isnot(None), WatchHistory.crew != '').limit(5).all()
for item in history:
    print(f"Movie: {item.title}")
    # print(f"Crew string: {item.crew[:200]}...")
    if item.crew.strip().startswith('['):
        try:
            crew_list = json.loads(item.crew)
            directors = [c.get('name') for c in crew_list if c.get('job') == 'Director']
            print("Directors identified:", directors)
        except Exception as e:
            print("JSON error:", e)
    else:
        print("Comma string.")
