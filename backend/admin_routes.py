from flask import Blueprint, request, jsonify
from db import get_db_connection
from auth_middleware import token_required
from activity_logger import log_activity

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

def get_admin_institution(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT institution_id FROM Users WHERE id = %s", (user_id,))
    res = cur.fetchone()
    conn.close()
    return res['institution_id'] if res else None

# --- Dashboard Overview ---
@admin_bp.route('/dashboard', methods=['GET'])
@token_required(allowed_roles=['admin'])
def get_dashboard_stats(current_user):
    inst_id = get_admin_institution(current_user['user_id'])
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM Users WHERE institution_id = %s AND role = 'student'", (inst_id,))
    student_count = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) FROM Users WHERE institution_id = %s AND role = 'faculty'", (inst_id,))
    faculty_count = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) FROM Departments WHERE institution_id = %s", (inst_id,))
    dept_count = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) FROM Classes c JOIN Departments d ON c.department_id = d.id WHERE d.institution_id = %s", (inst_id,))
    class_count = cur.fetchone()['count']
    
    conn.close()
    return jsonify({
        'students': student_count,
        'faculty': faculty_count,
        'departments': dept_count,
        'classes': class_count
    }), 200

# --- Departments Setup ---
@admin_bp.route('/departments', methods=['GET', 'POST', 'DELETE'])
@token_required(allowed_roles=['admin'])
def handle_departments(current_user):
    inst_id = get_admin_institution(current_user['user_id'])
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'GET':
        cur.execute("SELECT * FROM Departments WHERE institution_id = %s", (inst_id,))
        departments = cur.fetchall()
        conn.close()
        return jsonify(departments), 200
        
    elif request.method == 'POST':
        name = request.json.get('name')
        if not name:
            return jsonify({'message': 'Department name is required'}), 400
            
        cur.execute("INSERT INTO Departments (name, institution_id) VALUES (%s, %s) RETURNING *", (name, inst_id))
        dept = cur.fetchone()
        conn.close()
        return jsonify(dept), 201
        
    elif request.method == 'DELETE':
        dept_id = request.args.get('id')
        cur.execute("DELETE FROM Departments WHERE id = %s AND institution_id = %s", (dept_id, inst_id))
        conn.close()
        return jsonify({'message': 'Deleted successfully'}), 200

# --- Semesters Setup ---
@admin_bp.route('/semesters', methods=['GET', 'POST', 'DELETE'])
@token_required(allowed_roles=['admin'])
def handle_semesters(current_user):
    inst_id = get_admin_institution(current_user['user_id'])
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'GET':
        cur.execute("SELECT * FROM Semesters WHERE institution_id = %s ORDER BY number ASC", (inst_id,))
        semesters = cur.fetchall()
        conn.close()
        return jsonify(semesters), 200
        
    elif request.method == 'POST':
        number = request.json.get('number')
        if not number:
            return jsonify({'message': 'Semester number is required'}), 400
            
        cur.execute("INSERT INTO Semesters (number, institution_id) VALUES (%s, %s) RETURNING *", (number, inst_id))
        sem = cur.fetchone()
        conn.close()
        return jsonify(sem), 201

# --- User Management (Adding Students & Faculty) ---
@admin_bp.route('/users/add', methods=['POST'])
@token_required(allowed_roles=['admin'])
def add_user_to_institution(current_user):
    inst_id = get_admin_institution(current_user['user_id'])
    email = request.json.get('email')
    user_role = request.json.get('role') # 'student' or 'faculty'
    
    if not email or not user_role:
        return jsonify({'message': 'Email and role are required'}), 400
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id, role, institution_id FROM Users WHERE email = %s", (email,))
    user = cur.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'message': 'User with this email has not registered yet. They must sign up first.'}), 404
        
    if user['role'] != user_role:
        conn.close()
        return jsonify({'message': f"User registered as {user['role']}, but you are trying to add them as {user_role}."}), 400
        
    if user['institution_id']:
        if user['institution_id'] == inst_id:
            return jsonify({'message': 'User is already in your institution.'}), 400
        else:
            return jsonify({'message': 'User is already assigned to a different institution.'}), 400
            
    # Add to institution
    cur.execute("UPDATE Users SET institution_id = %s WHERE email = %s RETURNING id", (inst_id, email))
    updated_user_id = cur.fetchone()['id']
    
    # Specifics
    if user_role == 'student':
        register_number = request.json.get('register_number')
        class_id = request.json.get('class_id')
        if not register_number:
            conn.close()
            return jsonify({'message': 'Register number is required for students'}), 400
        cur.execute("INSERT INTO Students (user_id, register_number, class_id) VALUES (%s, %s, %s)", 
                    (updated_user_id, register_number, class_id))
        log_activity(current_user['user_id'], 'STUDENT_CREATED', entity_type='student', entity_id=updated_user_id, new_data={'email': email, 'register_number': register_number, 'class_id': class_id}, cursor=cur)
    elif user_role == 'faculty':
        cur.execute("INSERT INTO Teachers (user_id) VALUES (%s)", (updated_user_id,))
        log_activity(current_user['user_id'], 'FACULTY_CREATED', entity_type='faculty', entity_id=updated_user_id, new_data={'email': email}, cursor=cur)
        
    conn.close()
    return jsonify({'message': f"{user_role.capitalize()} successfully added to institution."}), 200

# --- Classes & Subjects ---
@admin_bp.route('/classes', methods=['GET', 'POST'])
@token_required(allowed_roles=['admin'])
def handle_classes(current_user):
    inst_id = get_admin_institution(current_user['user_id'])
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'GET':
        query = """
            SELECT c.id, d.name as department, s.number as semester, c.section
            FROM Classes c
            JOIN Departments d ON c.department_id = d.id
            JOIN Semesters s ON c.semester_id = s.id
            WHERE d.institution_id = %s
        """
        cur.execute(query, (inst_id,))
        classes = cur.fetchall()
        conn.close()
        return jsonify(classes), 200
        
    elif request.method == 'POST':
        data = request.json
        cur.execute("INSERT INTO Classes (department_id, semester_id, section) VALUES (%s, %s, %s) RETURNING *", 
                   (data['department_id'], data['semester_id'], data['section']))
        new_class = cur.fetchone()
        return jsonify(new_class), 201

# --- Faculty Assignment Setup ---
@admin_bp.route('/faculty', methods=['GET'])
@token_required(allowed_roles=['admin'])
def get_faculty(current_user):
    inst_id = get_admin_institution(current_user['user_id'])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email FROM Users WHERE institution_id = %s AND role = 'faculty' ORDER BY name ASC", (inst_id,))
    faculty = cur.fetchall()
    conn.close()
    return jsonify(faculty), 200

@admin_bp.route('/class-assignments', methods=['GET'])
@token_required(allowed_roles=['admin'])
def get_class_assignments(current_user):
    inst_id = get_admin_institution(current_user['user_id'])
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
        SELECT ca.id as mapping_id, u.id as teacher_id, u.name as teacher_name, 
               c.id as class_id, CONCAT(d.name, ' | Sem ', s.number, ' | Sec ', c.section) as class_name, 
               ca.role
        FROM ClassAssignments ca
        JOIN Users u ON ca.teacher_id = u.id
        JOIN Classes c ON ca.class_id = c.id
        JOIN Departments d ON c.department_id = d.id
        JOIN Semesters s ON c.semester_id = s.id
        WHERE d.institution_id = %s
        ORDER BY d.name, s.number, c.section, ca.role
    """
    cur.execute(query, (inst_id,))
    assignments = cur.fetchall()
    conn.close()
    return jsonify(assignments), 200

@admin_bp.route('/assign-faculty', methods=['POST'])
@token_required(allowed_roles=['admin'])
def assign_faculty(current_user):
    inst_id = get_admin_institution(current_user['user_id'])
    data = request.json
    teacher_id = data.get('teacher_id')
    class_id = data.get('class_id')
    role = data.get('role')
    
    if not all([teacher_id, class_id, role]):
        return jsonify({'message': 'Missing required fields'}), 400
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if identical assignment exists
        cur.execute("SELECT id FROM ClassAssignments WHERE teacher_id = %s AND class_id = %s AND role = %s",
                    (teacher_id, class_id, role))
        if cur.fetchone():
            return jsonify({'message': 'This exact assignment already exists'}), 400
            
        # Prevent >1 class teacher or vice class teacher per class
        if role in ['class_teacher', 'vice_class_teacher']:
            cur.execute("SELECT id FROM ClassAssignments WHERE class_id = %s AND role = %s", (class_id, role))
            if cur.fetchone():
                return jsonify({'message': f'This class already has a {role.replace("_", " ")}'}), 400
                
        # Insert Assignment
        cur.execute("INSERT INTO ClassAssignments (teacher_id, class_id, role) VALUES (%s, %s, %s)",
                    (teacher_id, class_id, role))
        
        return jsonify({'message': 'Faculty assigned successfully'}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# --- Admin Management System (Lifecycle Ops) ---

@admin_bp.route('/remove-faculty', methods=['DELETE'])
@token_required(allowed_roles=['admin'])
def remove_faculty_assignment(current_user):
    data = request.json
    teacher_id = data.get('teacher_id')
    class_id = data.get('class_id')

    if not all([teacher_id, class_id]):
        return jsonify({'message': 'teacher_id and class_id are required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Safety: check what role this teacher has
        cur.execute(
            "SELECT role FROM ClassAssignments WHERE teacher_id = %s AND class_id = %s",
            (teacher_id, class_id)
        )
        rows = cur.fetchall()
        if not rows:
            return jsonify({'message': 'Assignment not found'}), 404

        roles_being_removed = [r['role'] for r in rows]

        # Safety: if removing a class_teacher, warn (unless forced)
        if 'class_teacher' in roles_being_removed and not data.get('force'):
            return jsonify({
                'message': 'This teacher is the Class Teacher. Removing them will leave the class without a Class Teacher. Send force=true to confirm.',
                'needs_confirmation': True
            }), 409

        # Safety: check this isn't the LAST teacher for the class
        cur.execute(
            "SELECT COUNT(DISTINCT teacher_id) AS cnt FROM ClassAssignments WHERE class_id = %s AND teacher_id != %s",
            (class_id, teacher_id)
        )
        other_teachers = cur.fetchone()['cnt']
        # Also check SubjectAssignments
        cur.execute(
            "SELECT COUNT(DISTINCT teacher_id) AS cnt FROM SubjectAssignments WHERE class_id = %s AND teacher_id != %s",
            (class_id, teacher_id)
        )
        other_subject_teachers = cur.fetchone()['cnt']

        if other_teachers == 0 and other_subject_teachers == 0 and not data.get('force'):
            return jsonify({
                'message': 'This is the last teacher assigned to this class. Removing them will leave the class with no teachers. Send force=true to confirm.',
                'needs_confirmation': True
            }), 409

        # Proceed: delete class assignment AND related subject assignments
        cur.execute("DELETE FROM SubjectAssignments WHERE teacher_id = %s AND class_id = %s", (teacher_id, class_id))
        cur.execute("DELETE FROM ClassAssignments WHERE teacher_id = %s AND class_id = %s", (teacher_id, class_id))
        log_activity(current_user['user_id'], 'FACULTY_REMOVED', entity_type='faculty', entity_id=teacher_id, old_data={'class_id': class_id, 'roles': roles_being_removed}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Faculty removed from class'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

@admin_bp.route('/transfer-faculty', methods=['PUT'])
@token_required(allowed_roles=['admin'])
def transfer_faculty(current_user):
    data = request.json
    teacher_id = data.get('teacher_id')
    old_class_id = data.get('old_class_id')
    new_class_id = data.get('new_class_id')
    role = data.get('role')
    
    if old_class_id == new_class_id:
        return jsonify({'message': 'New class must be different from old class'}), 400
        
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check duplicate role on new class
        if role in ['class_teacher', 'vice_class_teacher']:
            cur.execute("SELECT id FROM ClassAssignments WHERE class_id = %s AND role = %s", (new_class_id, role))
            if cur.fetchone():
                return jsonify({'message': f'New class already has a {role.replace("_", " ")}'}), 400
                
        # Move
        cur.execute("DELETE FROM ClassAssignments WHERE teacher_id = %s AND class_id = %s AND role = %s", 
                   (teacher_id, old_class_id, role))
        cur.execute("INSERT INTO ClassAssignments (teacher_id, class_id, role) VALUES (%s, %s, %s)",
                   (teacher_id, new_class_id, role))
        log_activity(current_user['user_id'], 'FACULTY_TRANSFERRED', entity_type='faculty', entity_id=teacher_id, old_data={'class_id': old_class_id, 'role': role}, new_data={'class_id': new_class_id, 'role': role}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Faculty transferred successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

@admin_bp.route('/students', methods=['GET'])
@token_required(allowed_roles=['admin'])
def get_all_students(current_user):
    inst_id = get_admin_institution(current_user['user_id'])
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
        SELECT s.user_id, u.name, s.register_number, c.id as class_id,
               CONCAT(d.name, ' | Sem ', sem.number, ' | Sec ', c.section) as class_name
        FROM Students s
        JOIN Users u ON s.user_id = u.id
        LEFT JOIN Classes c ON s.class_id = c.id
        LEFT JOIN Departments d ON c.department_id = d.id
        LEFT JOIN Semesters sem ON c.semester_id = sem.id
        WHERE u.institution_id = %s
        ORDER BY s.register_number
    """
    cur.execute(query, (inst_id,))
    students = cur.fetchall()
    conn.close()
    return jsonify(students), 200

@admin_bp.route('/remove-student', methods=['DELETE'])
@token_required(allowed_roles=['admin'])
def remove_student(current_user):
    """Hard remove — deletes from Students table, keeps User account."""
    data = request.json
    user_id = data.get('user_id')

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Get registration number for logging details
        cur.execute("SELECT register_number, class_id FROM Students WHERE user_id = %s", (user_id,))
        stu_res = cur.fetchone()
        old_data = {'register_number': stu_res['register_number'], 'class_id': stu_res['class_id']} if stu_res else None

        cur.execute("DELETE FROM Students WHERE user_id = %s", (user_id,))
        log_activity(current_user['user_id'], 'STUDENT_REMOVED', entity_type='student', entity_id=user_id, old_data=old_data, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Student removed from institution successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/remove-student-from-class', methods=['POST'])
@token_required(allowed_roles=['admin'])
def remove_student_from_class(current_user):
    """Soft unlink — sets class_id to NULL, student stays in institution."""
    data = request.json
    student_id = data.get('student_id')

    if not student_id:
        return jsonify({'message': 'student_id is required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (student_id,))
        old_class_res = cur.fetchone()
        old_class_id = old_class_res['class_id'] if old_class_res else None

        cur.execute("SELECT user_id FROM Students WHERE user_id = %s", (student_id,))
        if not cur.fetchone():
            return jsonify({'message': 'Student not found'}), 404

        cur.execute("UPDATE Students SET class_id = NULL WHERE user_id = %s", (student_id,))
        log_activity(current_user['user_id'], 'STUDENT_TRANSFERRED', entity_type='student', entity_id=student_id, old_data={'class_id': old_class_id}, new_data={'class_id': None}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Student removed from class (account preserved)'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/remove-faculty-from-class', methods=['POST'])
@token_required(allowed_roles=['admin'])
def remove_faculty_from_class(current_user):
    """Remove faculty from a specific class (ClassAssignment + SubjectAssignment)."""
    data = request.json
    teacher_id = data.get('teacher_id')
    class_id   = data.get('class_id')

    if not all([teacher_id, class_id]):
        return jsonify({'message': 'teacher_id and class_id are required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM SubjectAssignments WHERE teacher_id = %s AND class_id = %s", (teacher_id, class_id))
        cur.execute("DELETE FROM ClassAssignments WHERE teacher_id = %s AND class_id = %s", (teacher_id, class_id))
        log_activity(current_user['user_id'], 'FACULTY_REMOVED', entity_type='faculty', entity_id=teacher_id, old_data={'class_id': class_id}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Faculty removed from class'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/reassign-subject', methods=['POST'])
@token_required(allowed_roles=['admin'])
def reassign_subject(current_user):
    """Change the teacher assigned to a subject."""
    data = request.json
    subject_id     = data.get('subject_id')
    new_teacher_id = data.get('new_teacher_id')

    if not all([subject_id, new_teacher_id]):
        return jsonify({'message': 'subject_id and new_teacher_id are required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT teacher_id FROM SubjectAssignments WHERE subject_id = %s", (subject_id,))
        old_res = cur.fetchone()
        old_teacher_id = old_res['teacher_id'] if old_res else None

        cur.execute("SELECT id, class_id FROM SubjectAssignments WHERE subject_id = %s", (subject_id,))
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE SubjectAssignments SET teacher_id = %s WHERE subject_id = %s",
                (new_teacher_id, subject_id)
            )
        else:
            # Need class_id from the subject
            cur.execute("SELECT class_id FROM Subjects WHERE id = %s", (subject_id,))
            sub = cur.fetchone()
            if not sub:
                return jsonify({'message': 'Subject not found'}), 404
            cur.execute(
                "INSERT INTO SubjectAssignments (teacher_id, class_id, subject_id) VALUES (%s, %s, %s)",
                (new_teacher_id, sub['class_id'], subject_id)
            )
        log_activity(current_user['user_id'], 'SUBJECT_TEACHER_CHANGED', entity_type='subject', entity_id=subject_id, old_data={'teacher_id': old_teacher_id}, new_data={'teacher_id': new_teacher_id}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Subject reassigned successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/faculty-detailed', methods=['GET'])
@token_required(allowed_roles=['admin'])
def get_faculty_detailed(current_user):
    """Return all faculty with their class assignments and subject assignments."""
    inst_id = get_admin_institution(current_user['user_id'])
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name, email FROM Users WHERE institution_id = %s AND role = 'faculty' ORDER BY name",
            (inst_id,)
        )
        faculty_list = cur.fetchall()

        for f in faculty_list:
            # Class assignments
            cur.execute("""
                SELECT ca.id AS mapping_id, ca.class_id, ca.role,
                       CONCAT(d.name, ' | Sem ', sem.number, ' | Sec ', c.section) AS class_name
                FROM ClassAssignments ca
                JOIN Classes c ON ca.class_id = c.id
                JOIN Departments d ON c.department_id = d.id
                JOIN Semesters sem ON c.semester_id = sem.id
                WHERE ca.teacher_id = %s
                ORDER BY d.name, sem.number
            """, (f['id'],))
            f['assignments'] = cur.fetchall()

            # Subject assignments
            cur.execute("""
                SELECT sa.id, sa.class_id, sa.subject_id, sub.name AS subject_name,
                       CONCAT(d.name, ' | Sem ', sem.number, ' | Sec ', c.section) AS class_name
                FROM SubjectAssignments sa
                JOIN Subjects sub ON sa.subject_id = sub.id
                JOIN Classes c ON sa.class_id = c.id
                JOIN Departments d ON c.department_id = d.id
                JOIN Semesters sem ON c.semester_id = sem.id
                WHERE sa.teacher_id = %s
                ORDER BY d.name, sem.number
            """, (f['id'],))
            f['subjects'] = cur.fetchall()

        return jsonify(faculty_list), 200
    finally:
        conn.close()

@admin_bp.route('/transfer-student', methods=['PUT'])
@token_required(allowed_roles=['admin'])
def transfer_student(current_user):
    data = request.json
    user_id = data.get('user_id')
    new_class_id = data.get('new_class_id')
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Get old class_id
        cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (user_id,))
        old_class_res = cur.fetchone()
        old_class_id = old_class_res['class_id'] if old_class_res else None

        # Verify valid student constraint mapping
        cur.execute("UPDATE Students SET class_id = %s WHERE user_id = %s", (new_class_id, user_id))
        log_activity(current_user['user_id'], 'STUDENT_TRANSFERRED', entity_type='student', entity_id=user_id, old_data={'class_id': old_class_id}, new_data={'class_id': new_class_id}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Student transferred successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# --- Semester Promotion System ---

@admin_bp.route('/promote-semester', methods=['POST'])
@token_required(allowed_roles=['admin'])
def promote_semester(current_user):
    inst_id = get_admin_institution(current_user['user_id'])
    mode = request.json.get('mode', 'keep_history') # 'keep_history' or 'reset'
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get all students
        query = """
            SELECT s.user_id, s.class_id, c.department_id, c.section, c.semester_id, sem.number
            FROM Students s
            JOIN Classes c ON s.class_id = c.id
            JOIN Semesters sem ON c.semester_id = sem.id
            WHERE sem.institution_id = %s
        """
        cur.execute(query, (inst_id,))
        students = cur.fetchall()
        
        # Get all semesters to figure out next semester
        cur.execute("SELECT id, number FROM Semesters WHERE institution_id = %s ORDER BY number ASC", (inst_id,))
        all_sems = cur.fetchall()
        if not all_sems:
            return jsonify({'message': 'No semesters defined'}), 400
            
        max_sem = all_sems[-1]['number']
        sem_map = { s['number']: s['id'] for s in all_sems }
        
        promoted_classes = set()
        
        for student in students:
            curr_num = student['number']
            if curr_num >= max_sem:
                 # Final semester, do not promote
                continue
            
            next_num = curr_num + 1
            if next_num not in sem_map:
                continue
                
            next_sem_id = sem_map[next_num]
            curr_class_id = student['class_id']
            if curr_class_id:
                promoted_classes.add(curr_class_id)
            
            # Find or insert new class
            cur.execute("""
                SELECT id FROM Classes WHERE department_id = %s AND semester_id = %s AND section = %s
            """, (student['department_id'], next_sem_id, student['section']))
            new_class = cur.fetchone()
            
            if new_class:
                new_class_id = new_class['id']
            else:
                cur.execute("""
                    INSERT INTO Classes (department_id, semester_id, section) VALUES (%s, %s, %s) RETURNING id
                """, (student['department_id'], next_sem_id, student['section']))
                new_class_id = cur.fetchone()['id']
                
            # Data Handling
            if mode == 'keep_history':
                # Save Attendance to History
                cur.execute("""
                    INSERT INTO AttendanceHistory (student_id, class_id, date, hour, subject_id, semester_id, status, updated_by)
                    SELECT student_id, class_id, date, hour, subject_id, %s, status, updated_by
                    FROM Attendance WHERE student_id = %s AND class_id = %s
                """, (student['semester_id'], student['user_id'], curr_class_id))
                
                # Save Marks to History
                cur.execute("""
                    INSERT INTO MarksHistory (student_id, subject_id, semester_id, mark_type, mark_name, marks, updated_by)
                    SELECT m.student_id, m.subject_id, %s, m.mark_type, m.mark_name, m.marks, m.updated_by
                    FROM Marks m
                    JOIN Subjects sub ON m.subject_id = sub.id
                    WHERE m.student_id = %s AND sub.class_id = %s
                """, (student['semester_id'], student['user_id'], curr_class_id))
                
            # Clear current arrays (Always happens regardless of keep or reset)
            cur.execute("DELETE FROM Attendance WHERE student_id = %s AND class_id = %s", (student['user_id'], curr_class_id))
            cur.execute("""
                DELETE FROM Marks 
                WHERE id IN (
                    SELECT m.id FROM Marks m 
                    JOIN Subjects sub ON m.subject_id = sub.id 
                    WHERE m.student_id = %s AND sub.class_id = %s
                )
            """, (student['user_id'], curr_class_id))
            
            # Update pointer
            cur.execute("UPDATE Students SET class_id = %s WHERE user_id = %s", (new_class_id, student['user_id']))
            
        # Subject Reset (Remove assignments)
        if promoted_classes:
            class_ids_tuple = tuple(promoted_classes)
            cur.execute("DELETE FROM SubjectAssignments WHERE class_id IN %s", (class_ids_tuple,))
        
        log_activity(current_user['user_id'], 'PROMOTION_EXECUTED', entity_type='institution', entity_id=inst_id, new_data={'mode': mode}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'All students successfully promoted to the next semester!'}), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'message': 'Error during promotion: ' + str(e)}), 500
    finally:
        conn.close()
