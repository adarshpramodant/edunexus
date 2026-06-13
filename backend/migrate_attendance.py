"""
Migration: Upgrade Attendance System
Run once to add AttendanceLogs table and any missing columns.
"""
from db import get_db_connection

def migrate():
    conn = get_db_connection()
    cur = conn.cursor()

    print("Running attendance system migration...")

    # 1. Create AttendanceLogs table (edit history)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS AttendanceLogs (
            id SERIAL PRIMARY KEY,
            attendance_id INTEGER REFERENCES Attendance(id) ON DELETE CASCADE NOT NULL,
            previous_status VARCHAR(2),
            new_status VARCHAR(2) NOT NULL,
            changed_by INTEGER REFERENCES Users(id) NOT NULL,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    print("  [OK] AttendanceLogs table ensured.")

    # 2. Ensure updated_at column exists on Attendance (it's in schema, but just in case)
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='attendance' AND column_name='updated_at'
            ) THEN
                ALTER TABLE Attendance ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            END IF;
        END$$;
    """)
    print("  [OK] Attendance.updated_at column ensured.")

    # 3. Add unique constraint on Attendance to prevent duplicate rows
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_attendance_slot_student'
            ) THEN
                ALTER TABLE Attendance
                ADD CONSTRAINT uq_attendance_slot_student
                UNIQUE (student_id, class_id, date, hour, subject_id);
            END IF;
        END$$;
    """)
    print("  [OK] Attendance unique constraint ensured.")

    conn.commit()
    conn.close()
    print("Migration completed successfully.")

if __name__ == '__main__':
    migrate()
