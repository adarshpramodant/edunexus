from flask import Blueprint, request, jsonify
from db import get_db_connection
from auth_middleware import token_required
from notification_routes import create_notification, notify_class_students
from activity_logger import log_activity

faculty_bp = Blueprint('faculty', __name__, url_prefix='/api/faculty')

def get_user_institution(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT institution_id FROM Users WHERE id = %s", (user_id,))
    res = cur.fetchone()
    conn.close()
    return res['institution_id'] if res else None

# Fetch classes assigned to this faculty member, grouped by class
@faculty_bp.route('/my-classes', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_grouped_classes(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Needs to get all classes they either teach a subject in, or are class/vice teacher for
    query = """
        SELECT c.id as class_id, d.name as department, s.number as semester, c.section, 
               tca.role as assigned_role, sub.name as subject_name
        FROM Classes c
        JOIN Departments d ON c.department_id = d.id
        JOIN Semesters s ON c.semester_id = s.id
        LEFT JOIN ClassAssignments tca ON c.id = tca.class_id AND tca.teacher_id = %s
        LEFT JOIN SubjectAssignments sa ON c.id = sa.class_id AND sa.teacher_id = %s
        LEFT JOIN Subjects sub ON sa.subject_id = sub.id
        WHERE tca.teacher_id = %s OR sa.teacher_id = %s
    """
    
    cur.execute(query, (current_user['user_id'], current_user['user_id'], current_user['user_id'], current_user['user_id']))
    raw_data = cur.fetchall()
    conn.close()
    
    # Grouping logic
    classes_map = {}
    for row in raw_data:
        cid = row['class_id']
        if cid not in classes_map:
            classes_map[cid] = {
                'class_id': cid,
                'department': row['department'],
                'semester': row['semester'],
                'section': row['section'],
                'roles': set(),
                'subjects': set()
            }
        
        if row['assigned_role']:
            classes_map[cid]['roles'].add(row['assigned_role'])
            
        if row['subject_name']:
            classes_map[cid]['subjects'].add(row['subject_name'])
            
    # Serialize sets to lists
    result = []
    for cid, data in classes_map.items():
        data['roles'] = list(data['roles'])
        data['subjects'] = list(data['subjects'])
        result.append(data)
        
    return jsonify(result), 200

# Get Class Details for Workspace
@faculty_bp.route('/class/<int:class_id>', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_class_details(current_user, class_id):
    conn = get_db_connection()
    cur = conn.cursor()

    # Get base class info
    cur.execute("""
        SELECT c.id, d.name as department, s.number as semester, c.section
        FROM Classes c
        JOIN Departments d ON c.department_id = d.id
        JOIN Semesters s ON c.semester_id = s.id
        WHERE c.id = %s
    """, (class_id,))
    class_info = cur.fetchone()

    if not class_info:
        conn.close()
        return jsonify({'message': 'Class not found'}), 404

    # --- Multi-role resolution with priority ---
    ROLE_PRIORITY = {
        'class_teacher': 3,
        'vice_class_teacher': 2,
        'subject_teacher': 1
    }

    # Fetch ALL roles from ClassAssignments for this faculty + class
    cur.execute(
        "SELECT role FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s",
        (class_id, current_user['user_id'])
    )
    roles = list({row['role'] for row in cur.fetchall() if row['role']})

    # Check SubjectAssignments to detect subject_teacher role
    cur.execute(
        "SELECT id FROM SubjectAssignments WHERE class_id = %s AND teacher_id = %s LIMIT 1",
        (class_id, current_user['user_id'])
    )
    if cur.fetchone() and 'subject_teacher' not in roles:
        roles.append('subject_teacher')

    # Compute primary role by highest priority
    primary_role = max(roles, key=lambda r: ROLE_PRIORITY.get(r, 0)) if roles else None

    # Debug logging
    print(f"[Role Debug] class_id={class_id} user_id={current_user['user_id']}")
    print(f"[Role Debug] Roles: {roles}")
    print(f"[Role Debug] Primary Role: {primary_role}")

    conn.close()
    return jsonify({
        'id': class_info['id'],
        'department': class_info['department'],
        'semester': class_info['semester'],
        'section': class_info['section'],
        'roles': roles,
        'primary_role': primary_role,
        'class_role': primary_role  # backward-compat field
    }), 200

# Get all faculty for this institution (so class_teachers can assign subjects)
@faculty_bp.route('/all-faculty', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_all_faculty(current_user):
    inst_id = get_user_institution(current_user['user_id'])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM Users WHERE institution_id = %s AND role = 'faculty' ORDER BY name ASC", (inst_id,))
    faculty = cur.fetchall()
    conn.close()
    return jsonify(faculty), 200
# Create Subject for a specific class
@faculty_bp.route('/subjects', methods=['POST'])
@token_required(allowed_roles=['faculty'])
def add_subject(current_user):
    data = request.json
    class_id = data.get('class_id')
    subject_name = data.get('name')
    subject_code = data.get('code')
    
    if not all([class_id, subject_name, subject_code]):
        return jsonify({'message': 'Missing fields'}), 400
        
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check authorization
        cur.execute("SELECT role FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s AND role IN ('class_teacher', 'vice_class_teacher')",
                    (class_id, current_user['user_id']))
        if not cur.fetchone():
            return jsonify({'message': 'Unauthorized: Only Class/Vice Class Teacher can create subjects'}), 403
            
        cur.execute("INSERT INTO Subjects (name, code, class_id) VALUES (%s, %s, %s) RETURNING id", (subject_name, subject_code, class_id))
        new_sub = cur.fetchone()
        log_activity(current_user['user_id'], 'SUBJECT_CREATED', entity_type='subject', entity_id=new_sub['id'], new_data={'name': subject_name, 'code': subject_code, 'class_id': class_id}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Subject created successfully', 'subject_id': new_sub['id']}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# Get Subjects for a specific class (and their assignments)
@faculty_bp.route('/class/<int:class_id>/subjects', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_class_subjects(current_user, class_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if they are class/vice teacher
    cur.execute("SELECT role FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s AND role IN ('class_teacher', 'vice_class_teacher')",
                (class_id, current_user['user_id']))
    is_class_teacher = bool(cur.fetchone())
    
    if is_class_teacher:
        query = """
            SELECT sub.id as subject_id, sub.name, sub.code, sa.id as assignment_id, sa.teacher_id, u.name as teacher_name
            FROM Subjects sub
            LEFT JOIN SubjectAssignments sa ON sub.id = sa.subject_id
            LEFT JOIN Users u ON sa.teacher_id = u.id
            WHERE sub.class_id = %s
            ORDER BY sub.name
        """
        cur.execute(query, (class_id,))
    else:
        query = """
            SELECT sub.id as subject_id, sub.name, sub.code, sa.id as assignment_id, sa.teacher_id, u.name as teacher_name
            FROM Subjects sub
            JOIN SubjectAssignments sa ON sub.id = sa.subject_id
            JOIN Users u ON sa.teacher_id = u.id
            WHERE sa.teacher_id = %s AND sub.class_id = %s
        """
        cur.execute(query, (current_user['user_id'], class_id))
        
    subjects = cur.fetchall()
    
    # Optional logic to structure the response exactly mapping the ID properly to id so frontend doesn't break
    structured_subjects = []
    for s in subjects:
        structured_subjects.append({
            'id': s['subject_id'],
            'name': s['name'],
            'code': s['code'],
            'assignment_id': s['assignment_id'],
            'teacher_id': s['teacher_id'],
            'teacher_name': s['teacher_name']
        })
        
    conn.close()
    return jsonify(structured_subjects), 200

# Assign Teacher to Subject
@faculty_bp.route('/assign-subject', methods=['POST'])
@token_required(allowed_roles=['faculty'])
def assign_subject(current_user):
    data = request.json
    subject_id = data.get('subject_id')
    teacher_id = data.get('teacher_id')
    class_id = data.get('class_id')
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Validate auth
        cur.execute("SELECT role FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s AND role IN ('class_teacher', 'vice_class_teacher')",
                    (class_id, current_user['user_id']))
        if not cur.fetchone():
            return jsonify({'message': 'Unauthorized'}), 403
            
        # Update if exists, else insert
        cur.execute("SELECT teacher_id FROM SubjectAssignments WHERE subject_id = %s", (subject_id,))
        old_res = cur.fetchone()
        old_teacher_id = old_res['teacher_id'] if old_res else None

        cur.execute("SELECT id FROM SubjectAssignments WHERE subject_id = %s", (subject_id,))
        if cur.fetchone():
            cur.execute("UPDATE SubjectAssignments SET teacher_id = %s, class_id = %s WHERE subject_id = %s",
                        (teacher_id, class_id, subject_id))
        else:
            cur.execute("INSERT INTO SubjectAssignments (teacher_id, class_id, subject_id) VALUES (%s, %s, %s)",
                        (teacher_id, class_id, subject_id))
        
        log_activity(current_user['user_id'], 'SUBJECT_TEACHER_CHANGED', entity_type='subject', entity_id=subject_id, old_data={'teacher_id': old_teacher_id}, new_data={'teacher_id': teacher_id}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Subject assigned successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# Remove Assignment
@faculty_bp.route('/assign-subject/<int:assignment_id>', methods=['DELETE'])
@token_required(allowed_roles=['faculty'])
def remove_subject_assignment(current_user, assignment_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # We must verify the user mapping against the course to delete it
        # To find out the class_id of this assignment
        cur.execute("SELECT class_id FROM SubjectAssignments WHERE id = %s", (assignment_id,))
        res = cur.fetchone()
        if not res:
            return jsonify({'message': 'Assignment not found'}), 404
            
        class_id = res['class_id']
        cur.execute("SELECT role FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s AND role IN ('class_teacher', 'vice_class_teacher')",
                    (class_id, current_user['user_id']))
        if not cur.fetchone():
            return jsonify({'message': 'Unauthorized'}), 403
            
        cur.execute("DELETE FROM SubjectAssignments WHERE id = %s", (assignment_id,))
        return jsonify({'message': 'Assignment removed successfully'}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# Get My Subjects explicitly mapped to active teacher across all classes
@faculty_bp.route('/my-subjects', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_my_subjects(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
        SELECT sub.id as subject_id, sub.name, sub.code, c.id as class_id, c.section, d.name as department, s.number as semester
        FROM Subjects sub
        JOIN SubjectAssignments sa ON sub.id = sa.subject_id
        JOIN Classes c ON sa.class_id = c.id
        JOIN Departments d ON c.department_id = d.id
        JOIN Semesters s ON c.semester_id = s.id
        WHERE sa.teacher_id = %s
    """
    cur.execute(query, (current_user['user_id'],))
    subjects = cur.fetchall()
    conn.close()
    
    return jsonify(subjects), 200

# Get Students for a class
@faculty_bp.route('/class/<int:class_id>/students', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_class_students(current_user, class_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
        SELECT s.user_id as id, s.register_number, u.name, u.email
        FROM Students s
        JOIN Users u ON s.user_id = u.id
        WHERE s.class_id = %s
        ORDER BY s.register_number ASC
    """
    cur.execute(query, (class_id,))
    students = cur.fetchall()
    conn.close()
    
    return jsonify(students), 200

# ─────────────────────────────────────────────────────────────────────────────
# ATTENDANCE SYSTEM (v2 — Bulk, Conflict Detection, Audit Logs)
# ─────────────────────────────────────────────────────────────────────────────

def _check_att_authorization(cur, class_id, subject_id, user_id):
    """Check if user can manage attendance for this class/subject.
    Returns: ('full', None) | ('subject', None) | (None, 'error message')
    """
    cur.execute(
        "SELECT role FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s "
        "AND role IN ('class_teacher', 'vice_class_teacher')",
        (class_id, user_id)
    )
    if cur.fetchone():
        return 'full', None
    cur.execute(
        "SELECT id FROM SubjectAssignments WHERE subject_id = %s AND teacher_id = %s",
        (subject_id, user_id)
    )
    if cur.fetchone():
        return 'subject', None
    return None, 'Unauthorized: Not assigned to this subject or class'


# GET /api/faculty/attendance?class_id=&date=&hour=&subject_id=
@faculty_bp.route('/attendance', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_attendance(current_user):
    class_id   = request.args.get('class_id')
    date       = request.args.get('date')
    hour       = request.args.get('hour')
    subject_id = request.args.get('subject_id')

    if not all([class_id, date, hour, subject_id]):
        return jsonify({'message': 'Missing parameters'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        # Fetch attendance with last-updated metadata
        cur.execute("""
            SELECT a.student_id, a.status, a.updated_at,
                   u.name AS updated_by_name
            FROM Attendance a
            LEFT JOIN Users u ON a.updated_by = u.id
            WHERE a.class_id = %s AND a.date = %s
              AND a.hour = %s AND a.subject_id = %s
        """, (class_id, date, hour, subject_id))
        records = cur.fetchall()

        # Detect conflict: does another subject already have attendance in this slot?
        cur.execute("""
            SELECT DISTINCT s.name AS subject_name
            FROM Attendance a
            JOIN Subjects s ON a.subject_id = s.id
            WHERE a.class_id = %s AND a.date = %s AND a.hour = %s
              AND a.subject_id != %s
            LIMIT 1
        """, (class_id, date, hour, subject_id))
        conflict = cur.fetchone()

        attendance_map = {}
        session_meta = None
        for rec in records:
            attendance_map[rec['student_id']] = rec['status']
            if session_meta is None:
                session_meta = {
                    'updated_by': rec['updated_by_name'],
                    'updated_at': rec['updated_at'].isoformat() if rec['updated_at'] else None
                }

        return jsonify({
            'attendance': attendance_map,
            'session_meta': session_meta,
            'conflict': {'subject_name': conflict['subject_name']} if conflict else None
        }), 200
    finally:
        conn.close()


# POST /api/faculty/attendance
# Payload: { class_id, date, hour, subject_id, attendance: [{student_id, status}], force_overwrite }
@faculty_bp.route('/attendance', methods=['POST'])
@token_required(allowed_roles=['faculty'])
def save_attendance(current_user):
    data           = request.json
    class_id       = data.get('class_id')
    date           = data.get('date')
    hour           = data.get('hour')
    subject_id     = data.get('subject_id')
    attendance_arr = data.get('attendance')  # [{student_id, status}]
    force_overwrite = data.get('force_overwrite', False)

    if not all([class_id, date, hour, subject_id, attendance_arr]):
        return jsonify({'message': 'Missing data'}), 400

    if not isinstance(attendance_arr, list) or len(attendance_arr) == 0:
        return jsonify({'message': 'attendance must be a non-empty array'}), 400

    # Validate all students have a status
    missing = [item for item in attendance_arr if not item.get('status')]
    if missing:
        return jsonify({'message': f'{len(missing)} student(s) have no status set. All students must have a status.'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        # Authorization
        auth_level, err = _check_att_authorization(cur, class_id, subject_id, current_user['user_id'])
        if err:
            return jsonify({'message': err}), 403

        # Conflict detection — another subject in same slot
        cur.execute("""
            SELECT DISTINCT s.name AS subject_name
            FROM Attendance a
            JOIN Subjects s ON a.subject_id = s.id
            WHERE a.class_id = %s AND a.date = %s AND a.hour = %s
              AND a.subject_id != %s
            LIMIT 1
        """, (class_id, date, hour, subject_id))
        conflict = cur.fetchone()
        if conflict and not force_overwrite:
            return jsonify({
                'conflict': True,
                'message': f'Attendance already marked for "{conflict["subject_name"]}" in this slot. Set force_overwrite=true to proceed.'
            }), 409

        updated_count = 0
        inserted_count = 0

        for item in attendance_arr:
            stu_id = item['student_id']
            status = item['status']

            # Check existing record
            cur.execute("""
                SELECT id, status FROM Attendance
                WHERE class_id = %s AND date = %s AND hour = %s
                  AND subject_id = %s AND student_id = %s
            """, (class_id, date, hour, subject_id, stu_id))
            existing = cur.fetchone()

            if existing:
                prev_status = existing['status']
                cur.execute("""
                    UPDATE Attendance
                    SET status = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (status, current_user['user_id'], existing['id']))

                # Log the change (only if status actually changed)
                if prev_status != status:
                    cur.execute("""
                        INSERT INTO AttendanceLogs
                            (attendance_id, previous_status, new_status, changed_by)
                        VALUES (%s, %s, %s, %s)
                    """, (existing['id'], prev_status, status, current_user['user_id']))
                updated_count += 1
            else:
                cur.execute("""
                    INSERT INTO Attendance
                        (student_id, class_id, date, hour, subject_id, status, updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (stu_id, class_id, date, hour, subject_id, status, current_user['user_id']))
                new_id = cur.fetchone()['id']

                # Log the initial insert as a new entry
                cur.execute("""
                    INSERT INTO AttendanceLogs
                        (attendance_id, previous_status, new_status, changed_by)
                    VALUES (%s, NULL, %s, %s)
                """, (new_id, status, current_user['user_id']))
                inserted_count += 1

        # Log action at the session level
        action_type = 'ATTENDANCE_UPDATED' if updated_count > 0 else 'ATTENDANCE_CREATED'
        log_activity(
            current_user['user_id'],
            action_type,
            entity_type='class',
            entity_id=class_id,
            new_data={'subject_id': subject_id, 'date': date, 'hour': hour, 'students_count': len(attendance_arr)},
            cursor=cur
        )

        conn.commit()

        # ── Notification trigger: notify students that attendance was marked ──
        try:
            cur.execute("SELECT name FROM Subjects WHERE id = %s", (subject_id,))
            sub_rec = cur.fetchone()
            sub_name = sub_rec['name'] if sub_rec else 'your subject'

            notify_class_students(
                cur, class_id,
                'Attendance Marked',
                f'Attendance for {sub_name} on {date} (Hour {hour}) has been recorded.',
                'attendance'
            )
            conn.commit()
        except Exception:
            pass  # notifications are non-critical

        return jsonify({
            'message': f'Attendance saved. {inserted_count} new, {updated_count} updated.',
            'inserted': inserted_count,
            'updated': updated_count
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'message': 'Database error: ' + str(e)}), 500
    finally:
        conn.close()


# GET /api/faculty/attendance/history?class_id=&date=&hour=&subject_id=
@faculty_bp.route('/attendance/history', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_attendance_history(current_user):
    class_id   = request.args.get('class_id')
    date       = request.args.get('date')
    hour       = request.args.get('hour')
    subject_id = request.args.get('subject_id')

    if not all([class_id, date, hour, subject_id]):
        return jsonify({'message': 'Missing parameters'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            SELECT al.id, al.attendance_id, al.previous_status, al.new_status,
                   al.changed_at, u.name AS changed_by_name,
                   s.register_number, us.name AS student_name
            FROM AttendanceLogs al
            JOIN Attendance a ON al.attendance_id = a.id
            JOIN Users u ON al.changed_by = u.id
            JOIN Students s ON a.student_id = s.user_id
            JOIN Users us ON s.user_id = us.id
            WHERE a.class_id = %s AND a.date = %s
              AND a.hour = %s AND a.subject_id = %s
            ORDER BY al.changed_at DESC
            LIMIT 100
        """, (class_id, date, hour, subject_id))
        logs = cur.fetchall()
        result = []
        for log in logs:
            result.append({
                'id': log['id'],
                'student': log['student_name'],
                'register_number': log['register_number'],
                'previous_status': log['previous_status'],
                'new_status': log['new_status'],
                'changed_by': log['changed_by_name'],
                'changed_at': log['changed_at'].isoformat() if log['changed_at'] else None
            })
        return jsonify(result), 200
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# MARKS SYSTEM (v2 — Structured, Grouped, Editable, Validated)
# ─────────────────────────────────────────────────────────────────────────────

GRADE_SCALE = [
    (90, 'A+'), (80, 'A'), (70, 'B+'), (60, 'B'), (50, 'C'), (0, 'D')
]

def compute_grade(score):
    for threshold, grade in GRADE_SCALE:
        if score >= threshold:
            return grade
    return 'D'

def _check_marks_auth(cur, subject_id, user_id):
    """Returns (class_id, None) if authorized, else (None, error_msg)."""
    cur.execute("SELECT class_id FROM Subjects WHERE id = %s", (subject_id,))
    rec = cur.fetchone()
    if not rec:
        return None, 'Subject not found'
    class_id = rec['class_id']
    cur.execute(
        "SELECT role FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s "
        "AND role IN ('class_teacher', 'vice_class_teacher')",
        (class_id, user_id)
    )
    if cur.fetchone():
        return class_id, None
    cur.execute(
        "SELECT id FROM SubjectAssignments WHERE subject_id = %s AND teacher_id = %s",
        (subject_id, user_id)
    )
    if cur.fetchone():
        return class_id, None
    return None, 'Unauthorized: Not assigned to this subject'


# GET /api/faculty/marks?subject_id=&mark_type=&mark_name=&class_id=
@faculty_bp.route('/marks', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_marks(current_user):
    subject_id = request.args.get('subject_id')
    mark_type  = request.args.get('mark_type')
    mark_name  = request.args.get('mark_name')
    class_id   = request.args.get('class_id')

    if not all([subject_id, mark_type, mark_name]):
        return jsonify({'message': 'subject_id, mark_type, mark_name are required'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        _, err = _check_marks_auth(cur, subject_id, current_user['user_id'])
        if err and err != 'Subject not found':
            return jsonify({'message': err}), 403

        cur.execute("""
            SELECT m.student_id, m.marks, m.updated_at, u.name AS updated_by_name,
                   s.register_number, us.name AS student_name
            FROM Marks m
            JOIN Students s ON m.student_id = s.user_id
            JOIN Users us   ON s.user_id = us.id
            LEFT JOIN Users u ON m.updated_by = u.id
            WHERE m.subject_id = %s AND m.mark_type = %s AND m.mark_name = %s
            ORDER BY s.register_number ASC
        """, (subject_id, mark_type, mark_name))
        rows = cur.fetchall()

        result = {}
        for r in rows:
            result[r['student_id']] = {
                'marks': float(r['marks']) if r['marks'] is not None else None,
                'updated_by': r['updated_by_name'],
                'updated_at': r['updated_at'].isoformat() if r['updated_at'] else None
            }
        return jsonify(result), 200
    finally:
        conn.close()


# POST /api/faculty/marks
# Payload: { subject_id, mark_type, mark_name, max_marks, marks: [{student_id, marks}] }
@faculty_bp.route('/marks', methods=['POST'])
@token_required(allowed_roles=['faculty'])
def save_marks(current_user):
    data       = request.json
    subject_id = data.get('subject_id')
    mark_type  = data.get('mark_type')
    mark_name  = data.get('mark_name')
    max_marks  = data.get('max_marks', 100)
    marks_arr  = data.get('marks')  # [{student_id, marks}]

    if not all([subject_id, mark_type, mark_name, marks_arr]):
        return jsonify({'message': 'subject_id, mark_type, mark_name, marks are required'}), 400

    if not isinstance(marks_arr, list):
        return jsonify({'message': 'marks must be an array'}), 400

    # Validate all values
    for item in marks_arr:
        val = item.get('marks')
        if val is None or val == '':
            continue  # skip blanks (allowed — not everyone needs a mark)
        try:
            fval = float(val)
        except (ValueError, TypeError):
            return jsonify({'message': f'Invalid marks value "{val}" — must be numeric'}), 400
        if not (0 <= fval <= float(max_marks)):
            return jsonify({'message': f'Marks {fval} out of range (0–{max_marks})'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        class_id, err = _check_marks_auth(cur, subject_id, current_user['user_id'])
        if err:
            return jsonify({'message': err}), 403 if err != 'Subject not found' else 404

        inserted = 0
        updated  = 0

        for item in marks_arr:
            stu_id = item.get('student_id')
            val    = item.get('marks')
            if val is None or val == '':
                continue
            fval = float(val)

            cur.execute("""
                SELECT id FROM Marks
                WHERE subject_id = %s AND mark_type = %s AND mark_name = %s AND student_id = %s
            """, (subject_id, mark_type, mark_name, stu_id))
            existing = cur.fetchone()

            if existing:
                cur.execute("""
                    UPDATE Marks SET marks = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (fval, current_user['user_id'], existing['id']))
                updated += 1
            else:
                cur.execute("""
                    INSERT INTO Marks (student_id, subject_id, mark_type, mark_name, marks, updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (stu_id, subject_id, mark_type, mark_name, fval, current_user['user_id']))
                inserted += 1

        # Log action at the evaluation component level
        action_type = 'MARK_UPDATED' if updated > 0 else 'MARK_CREATED'
        log_activity(
            current_user['user_id'],
            action_type,
            entity_type='subject',
            entity_id=subject_id,
            new_data={'mark_type': mark_type, 'mark_name': mark_name, 'students_count': len(marks_arr)},
            cursor=cur
        )

        conn.commit()

        # ── Notification trigger: tell each affected student their marks were updated ──
        try:
            # Get subject name for the message
            cur.execute("SELECT name FROM Subjects WHERE id = %s", (subject_id,))
            sub_rec = cur.fetchone()
            sub_name = sub_rec['name'] if sub_rec else 'a subject'

            # Notify students who received marks in this batch
            notified_ids = [item['student_id'] for item in marks_arr if item.get('marks') not in (None, '')]
            for stu_id in notified_ids:
                create_notification(
                    cur, stu_id,
                    f'Marks Updated — {sub_name}',
                    f'Your {mark_type} marks for "{mark_name}" in {sub_name} have been recorded.',
                    'marks'
                )
            conn.commit()
        except Exception:
            pass  # notifications are non-critical

        return jsonify({
            'message': f'Marks saved. {inserted} new, {updated} updated.',
            'inserted': inserted,
            'updated': updated
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'message': 'Error: ' + str(e)}), 500
    finally:
        conn.close()


# DELETE /api/faculty/marks?subject_id=&mark_type=&mark_name=
# Clears an entire evaluation component for the class
@faculty_bp.route('/marks', methods=['DELETE'])
@token_required(allowed_roles=['faculty'])
def delete_marks_component(current_user):
    subject_id = request.args.get('subject_id')
    mark_type  = request.args.get('mark_type')
    mark_name  = request.args.get('mark_name')

    if not all([subject_id, mark_type, mark_name]):
        return jsonify({'message': 'subject_id, mark_type, mark_name required'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        class_id, err = _check_marks_auth(cur, subject_id, current_user['user_id'])
        if err:
            return jsonify({'message': err}), 403

        cur.execute("""
            DELETE FROM Marks
            WHERE subject_id = %s AND mark_type = %s AND mark_name = %s
        """, (subject_id, mark_type, mark_name))
        conn.commit()
        return jsonify({'message': 'Evaluation component deleted.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


# GET /api/faculty/marks/summary?subject_id=&class_id=
# Returns per-student aggregated performance across all mark components
@faculty_bp.route('/marks/summary', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_marks_summary(current_user):
    subject_id = request.args.get('subject_id')
    class_id   = request.args.get('class_id')

    if not all([subject_id, class_id]):
        return jsonify({'message': 'subject_id and class_id required'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        _, err = _check_marks_auth(cur, subject_id, current_user['user_id'])
        if err:
            return jsonify({'message': err}), 403

        # All mark components for this subject
        cur.execute("""
            SELECT DISTINCT mark_type, mark_name
            FROM Marks
            WHERE subject_id = %s
            ORDER BY mark_type, mark_name
        """, (subject_id,))
        components = cur.fetchall()

        # All students in class with their marks
        cur.execute("""
            SELECT s.user_id AS student_id, s.register_number,
                   us.name AS student_name,
                   m.mark_type, m.mark_name, m.marks
            FROM Students s
            JOIN Users us ON s.user_id = us.id
            LEFT JOIN Marks m ON m.student_id = s.user_id AND m.subject_id = %s
            WHERE s.class_id = %s
            ORDER BY s.register_number
        """, (subject_id, class_id))
        rows = cur.fetchall()

        # Aggregate per student
        students = {}
        for r in rows:
            sid = r['student_id']
            if sid not in students:
                students[sid] = {
                    'student_id': sid,
                    'register_number': r['register_number'],
                    'student_name': r['student_name'],
                    'marks': {},
                    'total': 0,
                    'count': 0
                }
            if r['mark_type'] and r['mark_name'] and r['marks'] is not None:
                key = f"{r['mark_type']}::{r['mark_name']}"
                students[sid]['marks'][key] = float(r['marks'])
                students[sid]['total'] += float(r['marks'])
                students[sid]['count'] += 1

        result = []
        for s in students.values():
            avg = s['total'] / s['count'] if s['count'] > 0 else 0
            s['average'] = round(avg, 2)
            s['grade']   = compute_grade(avg)
            result.append(s)

        return jsonify({'components': components, 'students': result}), 200
    finally:
        conn.close()

# Remove Subject Entirely (Optional cleanup logic)
@faculty_bp.route('/subjects/<int:subject_id>', methods=['DELETE'])
@token_required(allowed_roles=['faculty'])
def remove_subject(current_user, subject_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check authorization
        cur.execute("SELECT class_id FROM Subjects WHERE id = %s", (subject_id,))
        sub_res = cur.fetchone()
        if not sub_res:
            return jsonify({'message': 'Subject not found'}), 404
            
        cur.execute("SELECT role FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s AND role IN ('class_teacher', 'vice_class_teacher')",
                    (sub_res['class_id'], current_user['user_id']))
        if not cur.fetchone():
            return jsonify({'message': 'Unauthorized'}), 403
            
        cur.execute("DELETE FROM SubjectAssignments WHERE subject_id = %s", (subject_id,))
        cur.execute("DELETE FROM Subjects WHERE id = %s", (subject_id,))
        return jsonify({'message': 'Subject deleted successfully'}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# TIMETABLE SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

DAYS_ORDER = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

def _is_class_lead(cur, class_id, user_id):
    """Returns True if the user is a class_teacher or vice_class_teacher."""
    cur.execute(
        "SELECT role FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s "
        "AND role IN ('class_teacher', 'vice_class_teacher')",
        (class_id, user_id)
    )
    return bool(cur.fetchone())


@faculty_bp.route('/timetable/<int:class_id>', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_timetable(current_user, class_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        # Any faculty assigned to the class can view
        cur.execute("""
            SELECT 1 FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s
            UNION
            SELECT 1 FROM SubjectAssignments WHERE class_id = %s AND teacher_id = %s
        """, (class_id, current_user['user_id'],
              class_id, current_user['user_id']))
        if not cur.fetchone():
            return jsonify({'message': 'Unauthorized'}), 403

        cur.execute("""
            SELECT t.day, t.hour, t.subject_id, sub.name as subject_name,
                   sub.code as subject_code, u.name as teacher_name
            FROM Timetable t
            LEFT JOIN Subjects sub ON t.subject_id = sub.id
            LEFT JOIN SubjectAssignments sa ON sub.id = sa.subject_id AND sa.class_id = t.class_id
            LEFT JOIN Users u ON sa.teacher_id = u.id
            WHERE t.class_id = %s
            ORDER BY t.day, t.hour
        """, (class_id,))
        rows = cur.fetchall()

        # Structure: { day: { hour: {...} } }
        timetable = {d: {} for d in DAYS_ORDER}
        for row in rows:
            timetable[row['day']][row['hour']] = {
                'subject_id':   row['subject_id'],
                'subject_name': row['subject_name'],
                'subject_code': row['subject_code'],
                'teacher_name': row['teacher_name']
            }

        return jsonify(timetable), 200
    finally:
        conn.close()


@faculty_bp.route('/timetable', methods=['POST'])
@token_required(allowed_roles=['faculty'])
def upsert_timetable_slot(current_user):
    data       = request.json
    class_id   = data.get('class_id')
    day        = data.get('day')
    hour       = data.get('hour')
    subject_id = data.get('subject_id')

    if not all([class_id, day, hour]):
        return jsonify({'message': 'class_id, day, and hour are required'}), 400

    valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    if day not in valid_days:
        return jsonify({'message': f'day must be one of {valid_days}'}), 400
    if not (1 <= int(hour) <= 8):
        return jsonify({'message': 'hour must be between 1 and 8'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        if not _is_class_lead(cur, class_id, current_user['user_id']):
            return jsonify({'message': 'Unauthorized: Only class/vice-class teachers can edit the timetable'}), 403

        # UPSERT using ON CONFLICT (requires the UNIQUE constraint on class_id, day, hour)
        cur.execute("""
            INSERT INTO Timetable (class_id, day, hour, subject_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (class_id, day, hour)
            DO UPDATE SET subject_id = EXCLUDED.subject_id
        """, (class_id, day, int(hour), subject_id))

        log_activity(current_user['user_id'], 'TIMETABLE_UPDATED', entity_type='class', entity_id=class_id, new_data={'day': day, 'hour': hour, 'subject_id': subject_id}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Timetable slot saved'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


@faculty_bp.route('/timetable', methods=['DELETE'])
@token_required(allowed_roles=['faculty'])
def delete_timetable_slot(current_user):
    data     = request.json
    class_id = data.get('class_id')
    day      = data.get('day')
    hour     = data.get('hour')

    if not all([class_id, day, hour]):
        return jsonify({'message': 'class_id, day, and hour are required'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        if not _is_class_lead(cur, class_id, current_user['user_id']):
            return jsonify({'message': 'Unauthorized'}), 403

        cur.execute(
            "DELETE FROM Timetable WHERE class_id = %s AND day = %s AND hour = %s",
            (class_id, day, int(hour))
        )
        log_activity(current_user['user_id'], 'TIMETABLE_UPDATED', entity_type='class', entity_id=class_id, old_data={'day': day, 'hour': hour}, new_data={'day': day, 'hour': hour, 'subject_id': None}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Slot cleared'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()
