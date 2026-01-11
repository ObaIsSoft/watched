"""
Migration script to set is_public=True for all existing users
Run this once to ensure all users appear in leaderboards by default
"""
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Get DATABASE_URL from environment
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./watched.db")

# Create engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def migrate_is_public():
    """Set is_public=True for all users who don't have it set"""
    db = SessionLocal()
    try:
        # Update all users to have is_public=True if it's NULL or False
        result = db.execute(
            text("UPDATE users SET is_public = 1 WHERE is_public IS NULL OR is_public = 0")
        )
        db.commit()
        print(f"✅ Updated {result.rowcount} users to have is_public=True")
        
        # Show current status
        count_result = db.execute(text("SELECT COUNT(*) FROM users WHERE is_public = 1"))
        public_count = count_result.scalar()
        total_result = db.execute(text("SELECT COUNT(*) FROM users"))
        total_count = total_result.scalar()
        
        print(f"📊 {public_count}/{total_count} users now have public profiles")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🔄 Migrating user privacy settings...")
    migrate_is_public()
    print("✨ Migration complete!")
