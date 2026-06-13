"""
EduNexus — Notifications Table Migration
Run once: python migrate_notifications.py
"""

from db import get_db_connection

def run():
    conn = get_db_connection()
    cur  = conn.cursor()
    print("Running notifications migration...")

    # 1. Create Notifications table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Notifications (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
            title      VARCHAR(120) NOT NULL,
            message    TEXT NOT NULL,
            type       VARCHAR(20) NOT NULL DEFAULT 'system'
                           CHECK (type IN ('marks','attendance','survey','system','promotion','assignment')),
            is_read    BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    print("  ✓ Notifications table ensured.")

    # 2. Index for fast per-user queries (sorted by newest)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_notif_user_created
        ON Notifications (user_id, created_at DESC);
    """)
    print("  ✓ Index on (user_id, created_at) ensured.")

    # 3. Index for unread count queries
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_notif_user_unread
        ON Notifications (user_id, is_read)
        WHERE is_read = FALSE;
    """)
    print("  ✓ Partial index on unread notifications ensured.")

    conn.commit()
    conn.close()
    print("Migration completed successfully.")

if __name__ == '__main__':
    run()
