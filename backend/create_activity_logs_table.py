import sys
import os

# Adjust path to import db
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection

def run_migration():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ActivityLogs (
            id SERIAL PRIMARY KEY,
            institution_id INTEGER REFERENCES Institutions(id) ON DELETE SET NULL,
            user_id INTEGER REFERENCES Users(id) ON DELETE SET NULL,
            action VARCHAR(100) NOT NULL,
            entity_type VARCHAR(100),
            entity_id VARCHAR(100),
            old_data JSONB,
            new_data JSONB,
            ip_address VARCHAR(45),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_institution ON ActivityLogs(institution_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON ActivityLogs(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_action ON ActivityLogs(action);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON ActivityLogs(created_at DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_entity ON ActivityLogs(entity_type, entity_id);")
        
        conn.commit()
        print("ActivityLogs table and indexes created successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
