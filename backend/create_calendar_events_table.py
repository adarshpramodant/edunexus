import sys
import os

# Adjust path to import db
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection

def run_migration():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Create AcademicEvents Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS AcademicEvents (
            id SERIAL PRIMARY KEY,
            institution_id INTEGER REFERENCES Institutions(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            event_type VARCHAR(30) NOT NULL CHECK (event_type IN ('holiday', 'internal_exam', 'university_exam', 'lab_exam', 'assignment_deadline', 'survey_deadline', 'project_review', 'seminar', 'workshop', 'event', 'other')),
            start_date TIMESTAMP NOT NULL,
            end_date TIMESTAMP NOT NULL,
            target_role VARCHAR(20) NULL CHECK (target_role IN ('student', 'faculty', 'admin', 'all')),
            target_class_id INTEGER REFERENCES Classes(id) ON DELETE CASCADE NULL,
            created_by INTEGER REFERENCES Users(id) ON DELETE CASCADE,
            status VARCHAR(20) DEFAULT 'published' CHECK (status IN ('draft', 'published', 'cancelled', 'completed')),
            document_id INTEGER REFERENCES Documents(id) ON DELETE SET NULL NULL,
            event_color VARCHAR(30) DEFAULT 'indigo',
            recurrence_pattern VARCHAR(30) DEFAULT 'none' CHECK (recurrence_pattern IN ('none', 'daily', 'weekly', 'monthly', 'yearly')),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Create Indexes for performance
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_institution ON AcademicEvents(institution_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_class ON AcademicEvents(target_class_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON AcademicEvents(event_type);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_start ON AcademicEvents(start_date DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_is_active ON AcademicEvents(is_active);")

        conn.commit()
        print("AcademicEvents table and indexes created successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
