import sys
import os

# Adjust path to import db
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection

def run_migration():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Create AnalyticsThresholds persistent table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS AnalyticsThresholds (
            institution_id INTEGER PRIMARY KEY REFERENCES Institutions(id) ON DELETE CASCADE,
            attendance_threshold DECIMAL(5,2) DEFAULT 75.00 CHECK (attendance_threshold BETWEEN 0 AND 100),
            assignment_threshold DECIMAL(5,2) DEFAULT 60.00 CHECK (assignment_threshold BETWEEN 0 AND 100),
            marks_threshold DECIMAL(5,2) DEFAULT 50.00 CHECK (marks_threshold BETWEEN 0 AND 100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2. Create Core Attendance Summary View
        cur.execute("""
        CREATE OR REPLACE VIEW vw_StudentOverallAttendance AS
        SELECT 
            s.user_id AS student_id,
            s.class_id,
            COUNT(att.id) AS total_hours,
            SUM(CASE WHEN att.status IN ('P', 'DL') THEN 1 ELSE 0 END) AS present_hours,
            COALESCE(
                ROUND((SUM(CASE WHEN att.status IN ('P', 'DL') THEN 1 ELSE 0 END)::decimal / NULLIF(COUNT(att.id), 0)) * 100, 2),
                100.00
            ) AS attendance_percentage
        FROM Students s
        LEFT JOIN Attendance att ON s.user_id = att.student_id AND s.class_id = att.class_id
        GROUP BY s.user_id, s.class_id;
        """)

        # 3. Create Core Assignment Summary View (Cross Joins for active assignments)
        cur.execute("""
        CREATE OR REPLACE VIEW vw_StudentAssignmentSummary AS
        SELECT 
            s.user_id AS student_id,
            s.class_id,
            COUNT(a.id) AS total_assignments,
            COUNT(sub.id) AS total_submissions,
            SUM(CASE WHEN sub.is_late = TRUE THEN 1 ELSE 0 END) AS late_submissions,
            SUM(CASE WHEN sub.id IS NULL AND a.deadline < CURRENT_TIMESTAMP THEN 1 ELSE 0 END) AS missing_assignments,
            COALESCE(
                ROUND((COUNT(sub.id)::decimal / NULLIF(COUNT(a.id), 0)) * 100, 2),
                100.00
            ) AS completion_percentage
        FROM Students s
        CROSS JOIN Assignments a
        LEFT JOIN AssignmentSubmissions sub ON a.id = sub.assignment_id AND s.user_id = sub.student_id
        WHERE s.class_id = a.class_id AND a.is_active = TRUE AND a.status = 'published'
        GROUP BY s.user_id, s.class_id;
        """)

        # 4. Create Core Marks Summary View
        cur.execute("""
        CREATE OR REPLACE VIEW vw_StudentMarksSummary AS
        SELECT 
            s.user_id AS student_id,
            s.class_id,
            COUNT(m.id) AS total_marks_records,
            COALESCE(ROUND(AVG(m.marks), 2), 0.00) AS average_marks
        FROM Students s
        LEFT JOIN Marks m ON s.user_id = m.student_id
        GROUP BY s.user_id, s.class_id;
        """)

        # 5. Create Scoped Performance Analytics Master View
        cur.execute("""
        CREATE OR REPLACE VIEW vw_StudentPerformanceAnalytics AS
        SELECT 
            s.user_id AS student_id,
            u.name AS student_name,
            s.register_number,
            s.class_id,
            c.section AS class_section,
            dept.name AS department_name,
            sem.number AS semester_number,
            u.institution_id,
            COALESCE(att.attendance_percentage, 100.00) AS attendance_percentage,
            COALESCE(att.total_hours, 0) AS attendance_total_hours,
            COALESCE(att.present_hours, 0) AS attendance_present_hours,
            COALESCE(assign.completion_percentage, 100.00) AS assignment_completion_percentage,
            COALESCE(assign.total_assignments, 0) AS assignment_total_count,
            COALESCE(assign.total_submissions, 0) AS assignment_submitted_count,
            COALESCE(assign.missing_assignments, 0) AS assignment_missing_count,
            COALESCE(assign.late_submissions, 0) AS assignment_late_count,
            COALESCE(marks.average_marks, 0.00) AS average_marks,
            COALESCE(marks.total_marks_records, 0) AS marks_records_count
        FROM Students s
        JOIN Users u ON s.user_id = u.id
        LEFT JOIN Classes c ON s.class_id = c.id
        LEFT JOIN Departments dept ON c.department_id = dept.id
        LEFT JOIN Semesters sem ON c.semester_id = sem.id
        LEFT JOIN vw_StudentOverallAttendance att ON s.user_id = att.student_id
        LEFT JOIN vw_StudentAssignmentSummary assign ON s.user_id = assign.student_id
        LEFT JOIN vw_StudentMarksSummary marks ON s.user_id = marks.student_id;
        """)

        # 6. Create Subject-Specific Risk Analysis View
        cur.execute("""
        CREATE OR REPLACE VIEW vw_SubjectRiskAnalysis AS
        SELECT 
            sub.id AS subject_id,
            sub.name AS subject_name,
            sub.code AS subject_code,
            sub.class_id,
            c.section AS class_section,
            dept.name AS department_name,
            sem.number AS semester_number,
            COALESCE(ROUND(AVG(m.marks), 2), 0.00) AS average_marks,
            COALESCE(ROUND(MAX(m.marks), 2), 0.00) AS highest_marks,
            COALESCE(ROUND(MIN(m.marks), 2), 0.00) AS lowest_marks,
            COUNT(DISTINCT m.student_id) AS graded_students_count,
            COALESCE(
                ROUND((SUM(CASE WHEN att.status IN ('P', 'DL') THEN 1 ELSE 0 END)::decimal / NULLIF(COUNT(att.id), 0)) * 100, 2),
                100.00
            ) AS subject_attendance_percentage,
            COUNT(att.id) AS total_hours,
            SUM(CASE WHEN att.status = 'AB' THEN 1 ELSE 0 END) AS total_absences
        FROM Subjects sub
        LEFT JOIN Classes c ON sub.class_id = c.id
        LEFT JOIN Departments dept ON c.department_id = dept.id
        LEFT JOIN Semesters sem ON c.semester_id = sem.id
        LEFT JOIN Marks m ON sub.id = m.subject_id
        LEFT JOIN Attendance att ON sub.id = att.subject_id AND sub.class_id = att.class_id
        GROUP BY sub.id, sub.name, sub.code, sub.class_id, c.section, dept.name, sem.number;
        """)

        conn.commit()
        print("Analytics Thresholds table and core real-time SQL Views created successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
