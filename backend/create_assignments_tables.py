import sys
import os

# Adjust path to import db
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection

def run_migration():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Create Assignments Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS Assignments (
            id SERIAL PRIMARY KEY,
            class_id INTEGER REFERENCES Classes(id) ON DELETE CASCADE,
            subject_id INTEGER REFERENCES Subjects(id) ON DELETE CASCADE,
            created_by INTEGER REFERENCES Users(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            max_marks DECIMAL(5,2) NOT NULL,
            deadline TIMESTAMP NOT NULL,
            allow_resubmission BOOLEAN DEFAULT TRUE,
            status VARCHAR(20) DEFAULT 'published' CHECK (status IN ('draft', 'published', 'closed', 'archived')),
            is_active BOOLEAN DEFAULT TRUE,
            closed_at TIMESTAMP NULL,
            marks_published BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Create AssignmentSubmissions Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS AssignmentSubmissions (
            id SERIAL PRIMARY KEY,
            assignment_id INTEGER REFERENCES Assignments(id) ON DELETE CASCADE,
            student_id INTEGER REFERENCES Users(id) ON DELETE CASCADE,
            document_id INTEGER REFERENCES Documents(id) ON DELETE SET NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'submitted' CHECK (status IN ('submitted', 'evaluated')),
            marks DECIMAL(5,2) NULL,
            feedback TEXT,
            evaluated_by INTEGER REFERENCES Users(id) ON DELETE SET NULL,
            evaluated_at TIMESTAMP NULL,
            submission_count INTEGER DEFAULT 1,
            last_resubmitted_at TIMESTAMP NULL,
            is_late BOOLEAN DEFAULT FALSE,
            CONSTRAINT uq_assignment_student UNIQUE (assignment_id, student_id)
        );
        """)

        # Create Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assignments_class ON Assignments(class_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assignments_subject ON Assignments(subject_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assignments_status ON Assignments(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_submissions_assignment ON AssignmentSubmissions(assignment_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_submissions_student ON AssignmentSubmissions(student_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_submissions_status ON AssignmentSubmissions(status);")

        conn.commit()
        print("Assignments and Submissions tables and indexes created successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
