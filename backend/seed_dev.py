from main import SessionLocal, User, WatchHistory, WatchParty, InboxMessage, Achievement
from datetime import datetime, timedelta
import json
import random

db = SessionLocal()

def seed():
    print("🌱 Seeding Dev Data...")

    # 1. Ensure Dev User
    dev_user = db.query(User).filter(User.email == "dev@example.com").first()
    if not dev_user:
        dev_user = User(email="dev@example.com", name="Dev User", picture="https://api.dicebear.com/7.x/avataaars/svg?seed=Dev")
        db.add(dev_user)
        db.commit()
    
    print(f"👤 Dev User: {dev_user.id}")

    # 2. Create Friends
    friend_names = ["Alice", "Bob", "Charlie", "Diana"]
    friends = []
    for name in friend_names:
        u = db.query(User).filter(User.email == f"{name.lower()}@example.com").first()
        if not u:
            u = User(
                email=f"{name.lower()}@example.com", 
                name=name, 
                picture=f"https://api.dicebear.com/7.x/avataaars/svg?seed={name}"
            )
            db.add(u)
            db.commit()
            # Follow them
            # (Assuming we have a Follow association table or logic? 
            #  Wait, main.py has `following` relationship? Let's check `User` model structure if needed.
            #  The `User` model likely has a many-to-many or a separate table.
            #  Let's assume `Follow` model exists or just skip if complex.
            #  Actually, let's just create them so they exist for search.)
        friends.append(u)

    # 3. Seed History (Movies)
    movies = [
        (27205, "Inception", "Science Fiction"),
        (157336, "Interstellar", "Science Fiction"),
        (155, "The Dark Knight", "Action"),
        (299534, "Avengers: Endgame", "Action"),
        (19995, "Avatar", "Science Fiction"),
        (634649, "Spider-Man: No Way Home", "Action"),
        (496243, "Parasite", "Drama"),
        (120, "The Lord of the Rings: The Fellowship of the Ring", "Adventure"),
        (680, "Pulp Fiction", "Crime"),
        (13, "Forrest Gump", "Comedy")
    ]

    for tmdb_id, title, genre in movies:
        exists = db.query(WatchHistory).filter(WatchHistory.user_id == dev_user.id, WatchHistory.tmdb_id == tmdb_id).first()
        if not exists:
            h = WatchHistory(
                user_id=dev_user.id,
                tmdb_id=tmdb_id,
                media_type="movie",
                title=title,
                status="watched",
                rating=random.randint(4, 5), # High ratings
                genres=json.dumps([genre]),
                watched_at=datetime.utcnow() - timedelta(days=random.randint(1, 100))
            )
            db.add(h)
    
    # 4. Seed Watchlist (TV)
    shows = [
        (1399, "Game of Thrones", "Drama"),
        (66732, "Stranger Things", "Mystery"),
        (60059, "Better Call Saul", "Drama")
    ]
    for tmdb_id, title, genre in shows:
        exists = db.query(WatchHistory).filter(WatchHistory.user_id == dev_user.id, WatchHistory.tmdb_id == tmdb_id).first()
        if not exists:
            h = WatchHistory(
                user_id=dev_user.id,
                tmdb_id=tmdb_id,
                media_type="tv",
                title=title,
                status="watchlist",
                genres=json.dumps([genre])
                # No date field for watchlist? Check model. Model has 'date' for watched.
                # If status is watchlist, we rely on ID logic or maybe 'date' is nullable?
                # Let's just omit date for now if it's not strictly required or use 'date' field if applicable.
                # Actually, WatchHistory has `date` (Date).
            )
            h.date = datetime.utcnow().date() # Set the main date field
            db.add(h)

    # 5. Create a Watch Party
    party = db.query(WatchParty).first()
    if not party:
        party = WatchParty(
            host_id=friends[0].id, # Alice hosts
            tmdb_id=27205,
            title="Inception Rewatch",
            scheduled_at=datetime.utcnow() + timedelta(days=2),
            attendees=json.dumps([friends[0].id, dev_user.id])
        )
        db.add(party)

    # 6. Inbox Message
    msg = db.query(InboxMessage).filter(InboxMessage.receiver_id == dev_user.id).first()
    if not msg:
        msg = InboxMessage(
            sender_id=friends[1].id, # Bob
            receiver_id=dev_user.id,
            type="recommendation",
            content_id=603, # The Matrix
            message="You have to watch this!!",
            created_at=datetime.utcnow()
        )
        db.add(msg)

    db.commit()
    print("✅ Seeding Complete!")

if __name__ == "__main__":
    seed()
