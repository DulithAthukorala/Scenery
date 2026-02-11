# backend/scripts/init_db.py
from backend.services.database import init_db, DB_PATH

if __name__ == "__main__":
    init_db()
    print(f"DB ready at: {DB_PATH}")
