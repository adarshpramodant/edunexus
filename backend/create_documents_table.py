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
        CREATE TABLE IF NOT EXISTS Documents (
            id SERIAL PRIMARY KEY,
            institution_id INTEGER REFERENCES Institutions(id) ON DELETE CASCADE,
            uploaded_by INTEGER REFERENCES Users(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            original_filename VARCHAR(255) NOT NULL,
            storage_path VARCHAR(500) NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            file_size BIGINT NOT NULL,
            category VARCHAR(50) NOT NULL,
            visibility VARCHAR(20) NOT NULL CHECK (visibility IN ('public', 'role', 'class')),
            target_role VARCHAR(20) NULL CHECK (target_role IN ('student', 'faculty', 'admin')),
            target_class_id INTEGER REFERENCES Classes(id) ON DELETE SET NULL,
            version INTEGER DEFAULT 1,
            is_archived BOOLEAN DEFAULT FALSE,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_institution ON Documents(institution_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_class ON Documents(target_class_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by ON Documents(uploaded_by);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_visibility ON Documents(visibility);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_category ON Documents(category);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_is_deleted ON Documents(is_deleted);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_is_archived ON Documents(is_archived);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_created_at ON Documents(created_at DESC);")
        
        conn.commit()
        print("Documents table and indexes created successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
