import sys
import os

# Adjust path to import db
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection

def run_migration():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        print("Running Bulk Import module tables migration...")

        # 1. Create SemesterLocks
        cur.execute("""
        CREATE TABLE IF NOT EXISTS SemesterLocks (
            id SERIAL PRIMARY KEY,
            semester_id INTEGER REFERENCES Semesters(id) ON DELETE CASCADE UNIQUE,
            is_locked BOOLEAN DEFAULT FALSE,
            locked_by INTEGER REFERENCES Users(id) ON DELETE SET NULL,
            locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            unlocked_at TIMESTAMP
        );
        """)
        print("  [OK] SemesterLocks table ensured.")
        # 2. Create ImportJobs
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ImportJobs (
            id SERIAL PRIMARY KEY,
            faculty_id INTEGER REFERENCES Users(id) ON DELETE CASCADE,
            institution_id INTEGER REFERENCES Institutions(id) ON DELETE SET NULL,
            department_id INTEGER REFERENCES Departments(id) ON DELETE SET NULL,
            semester_id INTEGER REFERENCES Semesters(id) ON DELETE SET NULL,
            class_id INTEGER REFERENCES Classes(id) ON DELETE SET NULL,
            subject_id INTEGER REFERENCES Subjects(id) ON DELETE SET NULL,
            academic_year VARCHAR(50),
            exam_type VARCHAR(50), 
            hour INTEGER,          
            date DATE,             
            file_name VARCHAR(255) NOT NULL,
            import_type VARCHAR(50) NOT NULL, 
            status VARCHAR(50) NOT NULL,      
            progress_percent INTEGER DEFAULT 0,
            total_rows INTEGER DEFAULT 0,
            valid_rows INTEGER DEFAULT 0,
            warning_rows INTEGER DEFAULT 0,
            error_rows INTEGER DEFAULT 0,
            duration_ms INTEGER DEFAULT 0,
            rollback_token VARCHAR(100) UNIQUE,
            column_mapping JSONB,
            imported_data JSONB,       
            previous_records JSONB,    
            is_approved BOOLEAN DEFAULT FALSE,  
            approved_by INTEGER REFERENCES Users(id) ON DELETE SET NULL,
            approved_at TIMESTAMP,
            metadata JSONB,            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print("  [OK] ImportJobs table ensured.")

        # 3. Create ImportRows
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ImportRows (
            id SERIAL PRIMARY KEY,
            job_id INTEGER REFERENCES ImportJobs(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            raw_data JSONB NOT NULL,
            student_id INTEGER REFERENCES Students(user_id) ON DELETE SET NULL,
            validation_status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'valid', 'warning', 'error'
            execution_status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'imported', 'skipped', 'failed'
            error_message TEXT,
            processing_time_ms INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print("  [OK] ImportRows table ensured.")

        # 4. Create ImportErrors
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ImportErrors (
            id SERIAL PRIMARY KEY,
            job_id INTEGER REFERENCES ImportJobs(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            student_identifier VARCHAR(100),
            error_message TEXT NOT NULL,
            suggestion TEXT,
            error_type VARCHAR(50) NOT NULL, -- 'VALIDATION', 'CONFLICT', 'MATCHING'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print("  [OK] ImportErrors table ensured.")

        # 5. Create ImportLogs
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ImportLogs (
            id SERIAL PRIMARY KEY,
            job_id INTEGER REFERENCES ImportJobs(id) ON DELETE CASCADE,
            log_level VARCHAR(20) NOT NULL, 
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print("  [OK] ImportLogs table ensured.")

        # 6. Create ImportTemplates
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ImportTemplates (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            template_type VARCHAR(50) NOT NULL, 
            column_mapping JSONB,
            instructions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print("  [OK] ImportTemplates table ensured.")

        # 6.5. Create ImportHistory
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ImportHistory (
            id SERIAL PRIMARY KEY,
            job_id INTEGER REFERENCES ImportJobs(id) ON DELETE CASCADE,
            faculty_id INTEGER REFERENCES Users(id) ON DELETE SET NULL,
            action VARCHAR(50) NOT NULL,
            details JSONB,
            ip_address VARCHAR(45),
            user_agent TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print("  [OK] ImportHistory table ensured.")

        # 7. Create ImportVersions
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ImportVersions (
            id SERIAL PRIMARY KEY,
            class_id INTEGER REFERENCES Classes(id) ON DELETE CASCADE,
            subject_id INTEGER REFERENCES Subjects(id) ON DELETE CASCADE,
            import_type VARCHAR(50) NOT NULL,
            exam_type VARCHAR(50),
            date DATE,
            hour INTEGER,
            version_number INTEGER NOT NULL,
            job_id INTEGER REFERENCES ImportJobs(id) ON DELETE CASCADE,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print("  [OK] ImportVersions table ensured.")

        # 8. Create ImportConflicts
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ImportConflicts (
            id SERIAL PRIMARY KEY,
            job_id INTEGER REFERENCES ImportJobs(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            student_id INTEGER REFERENCES Students(user_id) ON DELETE CASCADE,
            field_name VARCHAR(100) NOT NULL,
            db_value VARCHAR(255),
            incoming_value VARCHAR(255),
            db_record_id INTEGER, -- references individual marks or attendance id
            modified_by VARCHAR(120),
            modified_date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print("  [OK] ImportConflicts table ensured.")

        # 9. Create ImportAnalytics
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ImportAnalytics (
            id SERIAL PRIMARY KEY,
            job_id INTEGER REFERENCES ImportJobs(id) ON DELETE CASCADE,
            summary_stats JSONB NOT NULL, -- e.g. average, standard deviation, grade distribution, pass rate
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print("  [OK] ImportAnalytics table ensured.")

        # 10. Create ImportNotifications
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ImportNotifications (
            id SERIAL PRIMARY KEY,
            job_id INTEGER REFERENCES ImportJobs(id) ON DELETE CASCADE,
            notification_id INTEGER REFERENCES Notifications(id) ON DELETE CASCADE
        );
        """)
        print("  [OK] ImportNotifications table ensured.")

        # 11. Create HeaderAliases
        cur.execute("""
        CREATE TABLE IF NOT EXISTS HeaderAliases (
            id SERIAL PRIMARY KEY,
            db_field VARCHAR(100) NOT NULL, 
            alias VARCHAR(100) UNIQUE NOT NULL, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print("  [OK] HeaderAliases table ensured.")

        # 12. Create ApprovalQueue
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ApprovalQueue (
            id SERIAL PRIMARY KEY,
            job_id INTEGER REFERENCES ImportJobs(id) ON DELETE CASCADE UNIQUE,
            status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
            reviewed_by INTEGER REFERENCES Users(id) ON DELETE SET NULL,
            comments TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP
        );
        """)
        print("  [OK] ApprovalQueue table ensured.")

        # Seed Default Header Aliases
        aliases = [
            # Register Number
            ('register_number', 'register number'),
            ('register_number', 'reg no'),
            ('register_number', 'reg number'),
            ('register_number', 'register_no'),
            ('register_number', 'roll no'),
            ('register_number', 'roll number'),
            ('register_number', 'roll_no'),
            ('register_number', 'admission no'),
            ('register_number', 'admission number'),
            ('register_number', 'student id'),
            ('register_number', 'student_id'),
            ('register_number', 'id'),
            ('register_number', 'university number'),
            ('register_number', 'university reg no'),
            ('register_number', 'enrollment number'),
            
            # Student Name
            ('student_name', 'student name'),
            ('student_name', 'name'),
            ('student_name', 'student_name'),
            ('student_name', 'full name'),
            ('student_name', 'fullname'),
            
            # Attendance
            ('attendance_status', 'attendance'),
            ('attendance_status', 'status'),
            ('attendance_status', 'attendance status'),
            ('attendance_status', 'attendance_status'),
            ('attendance_status', 'present'),
            ('attendance_status', 'p/a'),
            
            # Marks Types
            ('cia1', 'cia1'),
            ('cia1', 'cia 1'),
            ('cia1', 'cia_1'),
            ('cia1', 'internal1'),
            ('cia1', 'internal 1'),
            ('cia1', 'internal_1'),
            ('cia1', 'cia-i'),
            ('cia1', 'cia i'),
            ('cia1', 'series 1'),
            ('cia1', 'cat1'),
            
            ('cia2', 'cia2'),
            ('cia2', 'cia 2'),
            ('cia2', 'cia_2'),
            ('cia2', 'internal2'),
            ('cia2', 'internal 2'),
            ('cia2', 'internal_2'),
            ('cia2', 'cia-ii'),
            ('cia2', 'cia ii'),
            ('cia2', 'series 2'),
            ('cia2', 'cat2'),

            ('cia3', 'cia3'),
            ('cia3', 'cia 3'),
            ('cia3', 'cia_3'),
            ('cia3', 'internal3'),
            ('cia3', 'internal 3'),
            ('cia3', 'internal_3'),
            ('cia3', 'cia-iii'),
            ('cia3', 'cia iii'),
            ('cia3', 'series 3'),
            ('cia3', 'cat3'),
            
            ('assignment', 'assignment'),
            ('assignment', 'assignments'),
            ('assignment', 'assign'),
            
            ('lab', 'lab'),
            ('lab', 'labs'),
            ('lab', 'practical'),
            ('lab', 'practicals'),
            ('lab', 'viva'),
            
            ('project', 'project'),
            ('project', 'projects'),
            
            ('quiz', 'quiz'),
            ('quiz', 'quizzes'),
            
            ('seminar', 'seminar'),
            ('seminar', 'seminars'),

            ('total', 'total'),
            ('total', 'aggregate'),
            ('total', 'sum'),
            ('grade', 'grade'),
            ('grade', 'grades'),
            ('percentage', 'percentage'),
            ('percentage', 'percent'),
            ('percentage', '%')
        ]
        
        for db_field, alias in aliases:
            cur.execute("""
                INSERT INTO HeaderAliases (db_field, alias)
                VALUES (%s, %s)
                ON CONFLICT (alias) DO NOTHING
            """, (db_field, alias))
        print("  [OK] Seeded default header aliases.")

        # Create Indexes for fast querying
        cur.execute("CREATE INDEX IF NOT EXISTS idx_import_jobs_faculty ON ImportJobs(faculty_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_import_jobs_token ON ImportJobs(rollback_token);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_import_rows_job ON ImportRows(job_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_import_errors_job ON ImportErrors(job_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_import_history_job ON ImportHistory(job_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_import_conflicts_job ON ImportConflicts(job_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_import_versions_target ON ImportVersions(class_id, subject_id, import_type);")
        print("  [OK] Performance indexes created.")

        conn.commit()
        print("Migration completed successfully.")
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Migration failed: {e}")
        raise e
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
