from db import get_db_connection

conn = get_db_connection()
cur = conn.cursor()
try:
    cur.execute("""
    CREATE TABLE IF NOT EXISTS AttendanceHistory (
        id SERIAL PRIMARY KEY,
        student_id INTEGER NOT NULL,
        class_id INTEGER NOT NULL,
        date DATE NOT NULL,
        hour INTEGER NOT NULL,
        subject_id INTEGER NOT NULL, 
        semester_id INTEGER REFERENCES Semesters(id),
        status VARCHAR(2) NOT NULL,
        updated_by INTEGER,
        archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS MarksHistory (
        id SERIAL PRIMARY KEY,
        student_id INTEGER NOT NULL,
        subject_id INTEGER NOT NULL,
        semester_id INTEGER REFERENCES Semesters(id),
        mark_type VARCHAR(50) NOT NULL,
        mark_name VARCHAR(100) NOT NULL,
        marks DECIMAL(5,2) NOT NULL,
        updated_by INTEGER,
        archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    print("Tables created")
except Exception as e:
    print(e)
finally:
    conn.close()
