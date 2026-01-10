from main import SessionLocal, User, recalculate_xp
import logging

# Setup basic logging to stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def migrate():
    print("🚀 Starting XP/Level Migration...")
    db = SessionLocal()
    
    try:
        users = db.query(User).all()
        print(f"found {len(users)} users.")
        
        for user in users:
            print(f"Processing User: {user.name} (ID: {user.id})...")
            original_xp = user.xp
            original_level = user.level
            
            recalculate_xp(user, db)
            
            print(f"  -> XP: {original_xp} -> {user.xp}")
            print(f"  -> Level: {original_level} -> {user.level}")
            
        print("✅ Migration Complete!")
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
