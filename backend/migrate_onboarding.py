import sqlite3

try:
    conn = sqlite3.connect('watched_history.db')
    c = conn.cursor()
    c.execute("ALTER TABLE users ADD COLUMN has_completed_onboarding BOOLEAN DEFAULT 0")
    conn.commit()
    print("Migration successful: added has_completed_onboarding to users table")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("Column already exists")
    else:
        print(f"Error: {e}")
finally:
    conn.close()
