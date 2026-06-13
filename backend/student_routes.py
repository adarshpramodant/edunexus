from flask import Blueprint, request, jsonify
from db import get_db_connection
from auth_middleware import token_required

student_bp = Blueprint('student', __name__, url_prefix='/api/student')

# Get My Profile and Class details
@student_bp.route('/profile', methods=['GET'])
@token_required(allowed_roles=['student'])
def get_profile(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    query = """
        SELECT s.register_number, u.name, u.email, c.id as class_id, c.section, d.name as department, sem.number as semester
        FROM Students s
        JOIN Users u ON s.user_id = u.id
        LEFT JOIN Classes c ON s.class_id = c.id
        LEFT JOIN Departments d ON c.department_id = d.id
        LEFT JOIN Semesters sem ON c.semester_id = sem.id
        WHERE s.user_id = %s
    """
    cur.execute(query, (current_user['user_id'],))
    profile = cur.fetchone()
    conn.close()
    return jsonify(profile), 200

# Get Subjects and Overall Attendance Percentage
@student_bp.route('/courses', methods=['GET'])
@token_required(allowed_roles=['student'])
def get_courses_and_attendance_summary(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # First get student's class_id
    cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
    res = cur.fetchone()
    class_id = res['class_id'] if res else None
    
    if not class_id:
        return jsonify([]), 200
        
    # Get subjects for the class
    query = """
        SELECT sub.id, sub.name, sub.code, u.name as teacher_name
        FROM Subjects sub
        LEFT JOIN SubjectAssignments sa ON sub.id = sa.subject_id AND sa.class_id = %s
        LEFT JOIN Users u ON sa.teacher_id = u.id
        WHERE sub.class_id = %s
    """
    cur.execute(query, (class_id, class_id))
    subjects = cur.fetchall()
    
    results = []
    # Calculate attendance & fetch marks for each subject
    for sub in subjects:
        # Total recorded hours for this subject in this class
        cur.execute("SELECT COUNT(*) FROM Attendance WHERE class_id = %s AND subject_id = %s AND student_id = %s", 
                    (class_id, sub['id'], current_user['user_id']))
        total = cur.fetchone()['count']
        
        # Total present/duty leave
        cur.execute("SELECT COUNT(*) FROM Attendance WHERE class_id = %s AND subject_id = %s AND student_id = %s AND status IN ('P', 'DL')", 
                    (class_id, sub['id'], current_user['user_id']))
        present = cur.fetchone()['count']
        
        # Get Marks
        cur.execute("SELECT mark_type, mark_name, marks FROM Marks WHERE subject_id = %s AND student_id = %s", 
                    (sub['id'], current_user['user_id']))
        subject_marks = cur.fetchall()
        
        percentage = (present / total * 100) if total > 0 else 0
        
        results.append({
            'subject_id': sub['id'],
            'subject_name': sub['name'],
            'subject_code': sub['code'],
            'teacher_name': sub['teacher_name'],
            'present_hours': present,
            'total_hours': total,
            'percentage': round(percentage, 2),
            'marks': subject_marks
        })
        
    conn.close()
    return jsonify(results), 200

# Day-by-day attendance tracking
@student_bp.route('/attendance/history', methods=['GET'])
@token_required(allowed_roles=['student'])
def get_attendance_history(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
        SELECT a.date, a.hour, sub.name as subject_name, a.status
        FROM Attendance a
        JOIN Subjects sub ON a.subject_id = sub.id
        WHERE a.student_id = %s
        ORDER BY a.date DESC, a.hour ASC
    """
    cur.execute(query, (current_user['user_id'],))
    history = cur.fetchall()
    conn.close()
    
    # Format dates
    for row in history:
        row['date'] = row['date'].strftime('%Y-%m-%d') if row['date'] else ''
        
    return jsonify(history), 200

# Get Marks — structured by subject, grouped by mark_type
@student_bp.route('/marks', methods=['GET'])
@token_required(allowed_roles=['student'])
def get_student_marks(current_user):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        query = """
            SELECT sub.id AS subject_id, sub.name AS subject_name, sub.code AS subject_code,
                   m.mark_type, m.mark_name, m.marks, m.updated_at
            FROM Marks m
            JOIN Subjects sub ON m.subject_id = sub.id
            WHERE m.student_id = %s
            ORDER BY sub.name ASC, m.mark_type ASC, m.mark_name ASC
        """
        cur.execute(query, (current_user['user_id'],))
        rows = cur.fetchall()

        # Group: subject → types → entries
        subjects = {}
        for r in rows:
            sid = r['subject_id']
            if sid not in subjects:
                subjects[sid] = {
                    'subject_id':   sid,
                    'subject_name': r['subject_name'],
                    'subject_code': r['subject_code'],
                    'types':        {},
                    'total':        0.0,
                    'count':        0
                }
            mt = r['mark_type']
            if mt not in subjects[sid]['types']:
                subjects[sid]['types'][mt] = []
            subjects[sid]['types'][mt].append({
                'mark_name': r['mark_name'],
                'marks':     float(r['marks']) if r['marks'] is not None else None,
                'updated_at': r['updated_at'].isoformat() if r['updated_at'] else None
            })
            if r['marks'] is not None:
                subjects[sid]['total'] += float(r['marks'])
                subjects[sid]['count'] += 1

        def grade(score):
            for threshold, g in [(90,'A+'),(80,'A'),(70,'B+'),(60,'B'),(50,'C'),(0,'D')]:
                if score >= threshold: return g
            return 'D'

        result = []
        for s in subjects.values():
            avg = s['total'] / s['count'] if s['count'] > 0 else 0
            s['average'] = round(avg, 2)
            s['grade']   = grade(avg)
            # Convert types dict to list for JSON
            s['groups']  = [{'mark_type': t, 'entries': e} for t, e in s['types'].items()]
            del s['types']
            result.append(s)

        return jsonify(result), 200
    finally:
        conn.close()

# GET /api/student/performance — overall academic performance across all subjects
@student_bp.route('/performance', methods=['GET'])
@token_required(allowed_roles=['student'])
def get_performance(current_user):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
        res = cur.fetchone()
        if not res or not res['class_id']:
            return jsonify({'subjects': [], 'overall_average': 0, 'overall_grade': 'N/A'}), 200
        class_id = res['class_id']

        # All subjects + marks for this student
        cur.execute("""
            SELECT sub.id AS subject_id, sub.name AS subject_name, sub.code AS subject_code,
                   m.mark_type, m.mark_name, m.marks
            FROM Subjects sub
            LEFT JOIN Marks m ON m.subject_id = sub.id AND m.student_id = %s
            WHERE sub.class_id = %s
            ORDER BY sub.name ASC, m.mark_type ASC
        """, (current_user['user_id'], class_id))
        rows = cur.fetchall()

        def grade(score):
            for threshold, g in [(90,'A+'),(80,'A'),(70,'B+'),(60,'B'),(50,'C'),(0,'D')]:
                if score >= threshold: return g
            return 'D'

        subjects = {}
        for r in rows:
            sid = r['subject_id']
            if sid not in subjects:
                subjects[sid] = {
                    'subject_id':   sid,
                    'subject_name': r['subject_name'],
                    'subject_code': r['subject_code'],
                    'total': 0.0, 'count': 0, 'entries': []
                }
            if r['marks'] is not None:
                subjects[sid]['total'] += float(r['marks'])
                subjects[sid]['count'] += 1
                subjects[sid]['entries'].append({
                    'mark_type': r['mark_type'],
                    'mark_name': r['mark_name'],
                    'marks': float(r['marks'])
                })

        subject_list = []
        all_avgs = []
        for s in subjects.values():
            avg = s['total'] / s['count'] if s['count'] > 0 else None
            s['average'] = round(avg, 2) if avg is not None else None
            s['grade']   = grade(avg) if avg is not None else '—'
            subject_list.append(s)
            if avg is not None:
                all_avgs.append(avg)

        overall_avg   = round(sum(all_avgs) / len(all_avgs), 2) if all_avgs else 0
        overall_grade = grade(overall_avg) if all_avgs else 'N/A'

        return jsonify({
            'subjects':       subject_list,
            'overall_average': overall_avg,
            'overall_grade':   overall_grade
        }), 200
    finally:
        conn.close()

# Get Archived Academic History
@student_bp.route('/academic-history', methods=['GET'])
@token_required(allowed_roles=['student'])
def get_academic_history(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Needs to see if the table exists or if there's any data
    try:
        cur.execute("""
            SELECT ah.date, ah.hour, ah.status, sub.name as subject_name, sem.number as semester_number
            FROM AttendanceHistory ah
            JOIN Subjects sub ON ah.subject_id = sub.id
            JOIN Semesters sem ON ah.semester_id = sem.id
            WHERE ah.student_id = %s
            ORDER BY sem.number DESC, ah.date DESC
        """, (current_user['user_id'],))
        attendance_hist = cur.fetchall()
        
        cur.execute("""
            SELECT mh.mark_type, mh.mark_name, mh.marks, sub.name as subject_name, sem.number as semester_number
            FROM MarksHistory mh
            JOIN Subjects sub ON mh.subject_id = sub.id
            JOIN Semesters sem ON mh.semester_id = sem.id
            WHERE mh.student_id = %s
            ORDER BY sem.number DESC, mh.mark_type ASC
        """, (current_user['user_id'],))
        marks_hist = cur.fetchall()
        
        for row in attendance_hist:
            row['date'] = row['date'].strftime('%Y-%m-%d') if row['date'] else ''
            
        return jsonify({'attendance': attendance_hist, 'marks': marks_hist}), 200
        
    except Exception as e:
        # Table might not reflect yet if nothing was preserved in PostgreSQL or error
        return jsonify({'attendance': [], 'marks': [], 'error': str(e)}), 200
    finally:
        conn.close()

# Get Class Timetable for Student
@student_bp.route('/timetable', methods=['GET'])
@token_required(allowed_roles=['student'])
def get_student_timetable(current_user):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
        res = cur.fetchone()
        if not res or not res['class_id']:
            return jsonify({}), 200

        class_id = res['class_id']
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

        cur.execute("""
            SELECT t.day, t.hour, sub.name as subject_name, sub.code as subject_code,
                   u.name as teacher_name
            FROM Timetable t
            LEFT JOIN Subjects sub ON t.subject_id = sub.id
            LEFT JOIN SubjectAssignments sa ON sub.id = sa.subject_id AND sa.class_id = t.class_id
            LEFT JOIN Users u ON sa.teacher_id = u.id
            WHERE t.class_id = %s
            ORDER BY t.day, t.hour
        """, (class_id,))
        rows = cur.fetchall()

        timetable = {d: {} for d in days_order}
        for row in rows:
            timetable[row['day']][row['hour']] = {
                'subject_name': row['subject_name'],
                'subject_code': row['subject_code'],
                'teacher_name': row['teacher_name']
            }

        return jsonify(timetable), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
