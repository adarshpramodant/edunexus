import os
import sys
import time
from datetime import datetime
from flask import Blueprint, request, jsonify

# Adjust path to import other modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection
from auth_middleware import token_required
from activity_logger import log_activity
from notification_routes import create_notification, notify_class_students

assignments_bp = Blueprint('assignments', __name__, url_prefix='/api/assignments')

# ─────────────────────────────────────────────────────────────────────────────
# Hierarchy Role Validation helper
# ─────────────────────────────────────────────────────────────────────────────
def check_teacher_hierarchy(cur, teacher_id, class_id, subject_id):
    """
    Returns True if teacher_id is the Class Teacher, Vice Class Teacher,
    or the Assigned Subject Teacher for the specific class_id and subject_id.
    """
    # 1. Check Class assignments (class_teacher, vice_class_teacher)
    cur.execute("""
        SELECT 1 FROM ClassAssignments 
        WHERE teacher_id = %s AND class_id = %s AND role IN ('class_teacher', 'vice_class_teacher')
    """, (teacher_id, class_id))
    if cur.fetchone():
        return True

    # 2. Check Subject assignments
    cur.execute("""
        SELECT 1 FROM SubjectAssignments
        WHERE teacher_id = %s AND class_id = %s AND subject_id = %s
    """, (teacher_id, class_id, subject_id))
    if cur.fetchone():
        return True

    return False

# Helper to verify assignment access for teachers
def verify_assignment_teacher_access(cur, user_id, assign_id):
    cur.execute("SELECT class_id, subject_id, created_by, marks_published, title, max_marks FROM Assignments WHERE id = %s", (assign_id,))
    assign = cur.fetchone()
    if not assign:
        return None, "Assignment not found"
    
    if assign['created_by'] == user_id:
        return assign, None
        
    if not check_teacher_hierarchy(cur, user_id, assign['class_id'], assign['subject_id']):
        return None, "Unauthorized. You do not teach this subject/class."
        
    return assign, None

# ─────────────────────────────────────────────────────────────────────────────
# 1. CREATE ASSIGNMENT
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('', methods=['POST'])
@token_required(allowed_roles=['admin', 'faculty'])
def create_assignment(current_user):
    data = request.json
    class_id = data.get('class_id')
    subject_id = data.get('subject_id')
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    max_marks = data.get('max_marks')
    deadline_str = data.get('deadline') # ISO datetime string 'YYYY-MM-DD HH:MM:SS'
    allow_resubmission = data.get('allow_resubmission', True)
    status = data.get('status', 'published') # 'draft' or 'published'

    if not all([class_id, subject_id, title, max_marks, deadline_str]):
        return jsonify({'message': 'class_id, subject_id, title, max_marks, and deadline are required.'}), 400

    try:
        max_marks_val = float(max_marks)
        if max_marks_val <= 0:
            return jsonify({'message': 'max_marks must be positive.'}), 400
    except (ValueError, TypeError):
        return jsonify({'message': 'max_marks must be numeric.'}), 400

    if status not in ('draft', 'published'):
        return jsonify({'message': 'Initial status must be draft or published.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Enforce Role Hierarchy for Faculty
        if current_user['role'] == 'faculty':
            if not check_teacher_hierarchy(cur, current_user['user_id'], class_id, subject_id):
                return jsonify({'message': 'Unauthorized. You do not teach this subject/class.'}), 403

        # Insert Assignment
        cur.execute("""
            INSERT INTO Assignments (class_id, subject_id, created_by, title, description, max_marks, deadline, allow_resubmission, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (class_id, subject_id, current_user['user_id'], title, description or None, max_marks_val, deadline_str, allow_resubmission, status))
        assign_id = cur.fetchone()['id']

        # Notify students if immediately published
        if status == 'published':
            cur.execute("SELECT name FROM Subjects WHERE id = %s", (subject_id,))
            sub_res = cur.fetchone()
            sub_name = sub_res['name'] if sub_res else 'Subject'
            notify_class_students(cur, class_id, 'New Assignment Published', 
                                  f'Assignment "{title}" published for {sub_name}. Deadline: {deadline_str}.', 'assignment')

        log_activity(current_user['user_id'], 'ASSIGNMENT_CREATED', entity_type='assignment', entity_id=assign_id,
                     new_data={'title': title, 'status': status}, cursor=cur)

        conn.commit()
        return jsonify({'message': 'Assignment created successfully.', 'assignment_id': assign_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'message': 'Creation failed: ' + str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 2. UPDATE ASSIGNMENT
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('/<int:assign_id>', methods=['PUT'])
@token_required(allowed_roles=['admin', 'faculty'])
def update_assignment(current_user, assign_id):
    data = request.json
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    max_marks = data.get('max_marks')
    deadline_str = data.get('deadline')
    allow_resubmission = data.get('allow_resubmission')
    status = data.get('status') # 'draft' | 'published'

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        assign, err = verify_assignment_teacher_access(cur, current_user['user_id'], assign_id)
        if err:
            return jsonify({'message': err}), 403 if err != "Assignment not found" else 404

        if assign['marks_published']:
            return jsonify({'message': 'Cannot edit assignment after grades are published.'}), 400

        # Validate values
        update_fields = []
        params = []

        if title:
            update_fields.append("title = %s")
            params.append(title)
        if description is not None:
            update_fields.append("description = %s")
            params.append(description or None)
        if max_marks is not None:
            try:
                max_marks_val = float(max_marks)
                if max_marks_val <= 0:
                    return jsonify({'message': 'max_marks must be positive.'}), 400
                update_fields.append("max_marks = %s")
                params.append(max_marks_val)
            except (ValueError, TypeError):
                return jsonify({'message': 'max_marks must be numeric.'}), 400
        if deadline_str:
            update_fields.append("deadline = %s")
            params.append(deadline_str)
        if allow_resubmission is not None:
            update_fields.append("allow_resubmission = %s")
            params.append(allow_resubmission)

        # Handle status transitions (notifications if moving to published)
        if status:
            if status not in ('draft', 'published'):
                return jsonify({'message': 'Invalid status. Can only be draft or published.'}), 400
            
            # If changing from draft to published, dispatch notifications
            cur.execute("SELECT status, class_id, title, subject_id FROM Assignments WHERE id = %s", (assign_id,))
            old = cur.fetchone()
            if old['status'] == 'draft' and status == 'published':
                cur.execute("SELECT name FROM Subjects WHERE id = %s", (old['subject_id'],))
                sub_res = cur.fetchone()
                sub_name = sub_res['name'] if sub_res else 'Subject'
                
                notify_class_students(cur, old['class_id'], 'New Assignment Published', 
                                      f'Assignment "{old["title"]}" has been published for {sub_name}.', 'assignment')
            
            update_fields.append("status = %s")
            params.append(status)

        if not update_fields:
            return jsonify({'message': 'No fields to update.'}), 400

        params.append(assign_id)
        query = f"UPDATE Assignments SET {', '.join(update_fields)} WHERE id = %s"
        cur.execute(query, tuple(params))

        log_activity(current_user['user_id'], 'ASSIGNMENT_UPDATED', entity_type='assignment', entity_id=assign_id, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Assignment updated successfully.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 3. CLOSE ASSIGNMENT (SOFT-CLOSE)
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('/<int:assign_id>/close', methods=['PUT'])
@token_required(allowed_roles=['admin', 'faculty'])
def close_assignment(current_user, assign_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        assign, err = verify_assignment_teacher_access(cur, current_user['user_id'], assign_id)
        if err:
            return jsonify({'message': err}), 403 if err != "Assignment not found" else 404

        cur.execute("""
            UPDATE Assignments 
            SET status = 'closed', is_active = FALSE, closed_at = CURRENT_TIMESTAMP 
            WHERE id = %s
        """, (assign_id,))

        log_activity(current_user['user_id'], 'ASSIGNMENT_CLOSED', entity_type='assignment', entity_id=assign_id, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Assignment successfully closed.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 4. DELETE ASSIGNMENT (SOFT-DELETE / ARCHIVE)
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('/<int:assign_id>', methods=['DELETE'])
@token_required(allowed_roles=['admin', 'faculty'])
def delete_assignment(current_user, assign_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        assign, err = verify_assignment_teacher_access(cur, current_user['user_id'], assign_id)
        if err:
            return jsonify({'message': err}), 403 if err != "Assignment not found" else 404

        cur.execute("""
            UPDATE Assignments 
            SET status = 'archived', is_active = FALSE 
            WHERE id = %s
        """, (assign_id,))

        log_activity(current_user['user_id'], 'ASSIGNMENT_ARCHIVED', entity_type='assignment', entity_id=assign_id, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Assignment archived successfully.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 5. LIST ASSIGNMENTS (ROLE SCOPED & FILTERED)
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def list_assignments(current_user):
    class_id = request.args.get('class_id')
    subject_id = request.args.get('subject_id')
    status_filter = request.args.get('status') # 'draft', 'published', 'closed'

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT a.id, a.class_id, a.subject_id, a.created_by, a.title, a.description, 
                   a.max_marks, a.deadline, a.allow_resubmission, a.status, a.is_active, 
                   a.closed_at, a.marks_published, a.created_at,
                   s.name as subject_name, s.code as subject_code,
                   d.name as department_name, sem.number as semester_number, c.section as class_section
            FROM Assignments a
            JOIN Classes c ON a.class_id = c.id
            JOIN Departments d ON c.department_id = d.id
            JOIN Semesters sem ON c.semester_id = sem.id
            JOIN Subjects s ON a.subject_id = s.id
            WHERE a.status != 'archived'
        """
        params = []

        # Role-based visibility scopes
        if current_user['role'] == 'admin':
            pass
        elif current_user['role'] == 'faculty':
            query += """
                AND (a.created_by = %s OR a.class_id IN (
                    SELECT class_id FROM ClassAssignments WHERE teacher_id = %s
                    UNION
                    SELECT class_id FROM SubjectAssignments WHERE teacher_id = %s
                ))
            """
            params.extend([current_user['user_id'], current_user['user_id'], current_user['user_id']])
        elif current_user['role'] == 'student':
            cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
            stu = cur.fetchone()
            stu_class = stu['class_id'] if stu else None
            
            if not stu_class:
                return jsonify([]), 200

            query += " AND a.class_id = %s AND a.status != 'draft' AND a.is_active = TRUE"
            params.append(stu_class)

        # Filters
        if class_id:
            query += " AND a.class_id = %s"
            params.append(class_id)
        if subject_id:
            query += " AND a.subject_id = %s"
            params.append(subject_id)
        if status_filter:
            query += " AND a.status = %s"
            params.append(status_filter)

        query += " ORDER BY a.created_at DESC"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        result = []
        for r in rows:
            # For students, left join their submission status
            sub_status = None
            sub_marks = None
            if current_user['role'] == 'student':
                cur.execute("SELECT status, marks FROM AssignmentSubmissions WHERE assignment_id = %s AND student_id = %s", (r['id'], current_user['user_id']))
                sub = cur.fetchone()
                if sub:
                    sub_status = sub['status']
                    sub_marks = float(sub['marks']) if sub['marks'] is not None else None

            result.append({
                'id': r['id'],
                'class_id': r['class_id'],
                'subject_id': r['subject_id'],
                'subject_name': r['subject_name'],
                'subject_code': r['subject_code'],
                'department_name': r['department_name'],
                'semester_number': r['semester_number'],
                'class_section': r['class_section'],
                'title': r['title'],
                'description': r['description'],
                'max_marks': float(r['max_marks']),
                'deadline': r['deadline'].isoformat() if r['deadline'] else None,
                'allow_resubmission': r['allow_resubmission'],
                'status': r['status'],
                'is_active': r['is_active'],
                'closed_at': r['closed_at'].isoformat() if r['closed_at'] else None,
                'marks_published': r['marks_published'],
                'created_at': r['created_at'].isoformat() if r['created_at'] else None,
                'submission_status': sub_status,
                'submission_marks': sub_marks
            })

        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': 'Error: ' + str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 6. GET ASSIGNMENT DETAIL
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('/<int:assign_id>', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def get_assignment_detail(current_user, assign_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT a.id, a.class_id, a.subject_id, a.title, a.description, a.max_marks, 
                   a.deadline, a.allow_resubmission, a.status, a.is_active, a.marks_published,
                   s.name as subject_name
            FROM Assignments a
            JOIN Subjects s ON a.subject_id = s.id
            WHERE a.id = %s AND a.status != 'archived'
        """, (assign_id,))
        assign = cur.fetchone()
        if not assign:
            return jsonify({'message': 'Assignment not found.'}), 404

        # Access check
        if current_user['role'] == 'student':
            cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
            stu = cur.fetchone()
            if not stu or stu['class_id'] != assign['class_id']:
                return jsonify({'message': 'Unauthorized to view this assignment.'}), 403

        # Get Student submission details if queried by student
        sub_details = None
        if current_user['role'] == 'student':
            cur.execute("""
                SELECT s.id, s.submitted_at, s.status, s.marks, s.feedback, 
                       s.submission_count, s.last_resubmitted_at, s.is_late,
                       d.original_filename, d.storage_path
                FROM AssignmentSubmissions s
                LEFT JOIN Documents d ON s.document_id = d.id
                WHERE s.assignment_id = %s AND s.student_id = %s
            """, (assign_id, current_user['user_id']))
            sub = cur.fetchone()
            if sub:
                sub_details = {
                    'id': sub['id'],
                    'submitted_at': sub['submitted_at'].isoformat() if sub['submitted_at'] else None,
                    'status': sub['status'],
                    'marks': float(sub['marks']) if sub['marks'] is not None else None,
                    'feedback': sub['feedback'],
                    'submission_count': sub['submission_count'],
                    'last_resubmitted_at': sub['last_resubmitted_at'].isoformat() if sub['last_resubmitted_at'] else None,
                    'is_late': sub['is_late'],
                    'filename': sub['original_filename'],
                    'storage_path': sub['storage_path']
                }

        result = {
            'id': assign['id'],
            'class_id': assign['class_id'],
            'subject_id': assign['subject_id'],
            'subject_name': assign['subject_name'],
            'title': assign['title'],
            'description': assign['description'],
            'max_marks': float(assign['max_marks']),
            'deadline': assign['deadline'].isoformat() if assign['deadline'] else None,
            'allow_resubmission': assign['allow_resubmission'],
            'status': assign['status'],
            'is_active': assign['is_active'],
            'marks_published': assign['marks_published'],
            'submission': sub_details
        }
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 7. SUBMIT ASSIGNMENT (STUDENT SCOPE)
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('/<int:assign_id>/submit', methods=['POST'])
@token_required(allowed_roles=['student'])
def submit_assignment(current_user, assign_id):
    data = request.json
    doc_id = data.get('document_id')

    if not doc_id:
        return jsonify({'message': 'document_id is required.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Get assignment configs
        cur.execute("SELECT class_id, deadline, allow_resubmission, status, is_active, title FROM Assignments WHERE id = %s", (assign_id,))
        assign = cur.fetchone()
        if not assign:
            return jsonify({'message': 'Assignment not found.'}), 404

        if assign['status'] != 'published' or not assign['is_active']:
            return jsonify({'message': 'Cannot submit. Assignment is draft, closed, or archived.'}), 400

        # Verify class scope
        cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
        stu = cur.fetchone()
        if not stu or stu['class_id'] != assign['class_id']:
            return jsonify({'message': 'Unauthorized. You do not belong to this class.'}), 403

        # Check existing submission
        cur.execute("SELECT id, submission_count FROM AssignmentSubmissions WHERE assignment_id = %s AND student_id = %s", (assign_id, current_user['user_id']))
        existing = cur.fetchone()

        now = datetime.now()
        is_late = now > assign['deadline']

        if existing:
            if not assign['allow_resubmission']:
                return jsonify({'message': 'Resubmissions are blocked for this assignment.'}), 400

            # Update existing submission (Resubmit)
            new_count = existing['submission_count'] + 1
            cur.execute("""
                UPDATE AssignmentSubmissions 
                SET document_id = %s, submitted_at = CURRENT_TIMESTAMP, last_resubmitted_at = CURRENT_TIMESTAMP,
                    status = 'submitted', submission_count = %s, is_late = %s
                WHERE id = %s
            """, (doc_id, new_count, is_late, existing['id']))
            sub_id = existing['id']
        else:
            # Insert initial submission
            cur.execute("""
                INSERT INTO AssignmentSubmissions (assignment_id, student_id, document_id, is_late, status, submission_count)
                VALUES (%s, %s, %s, %s, 'submitted', 1)
                RETURNING id
            """, (assign_id, current_user['user_id'], doc_id, is_late))
            sub_id = cur.fetchone()['id']

        log_activity(current_user['user_id'], 'ASSIGNMENT_SUBMITTED', entity_type='assignment_submission', entity_id=sub_id,
                     new_data={'assignment_title': assign['title'], 'is_late': is_late}, cursor=cur)

        conn.commit()
        return jsonify({'message': 'Assignment submitted successfully.', 'submission_id': sub_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 8. VIEW SUBMISSIONS LIST (FACULTY/ADMIN SCOPE)
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('/<int:assign_id>/submissions', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def view_submissions(current_user, assign_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        assign, err = verify_assignment_teacher_access(cur, current_user['user_id'], assign_id)
        if err:
            return jsonify({'message': err}), 403 if err != "Assignment not found" else 404

        # Retrieve all students enrolled in the class along with their submission status
        query = """
            SELECT s.user_id as student_id, u.name as student_name, s.register_number,
                   sub.id as submission_id, sub.submitted_at, sub.status as submission_status,
                   sub.marks, sub.feedback, sub.submission_count, sub.last_resubmitted_at, sub.is_late,
                   d.original_filename, d.id as doc_id
            FROM Students s
            JOIN Users u ON s.user_id = u.id
            LEFT JOIN AssignmentSubmissions sub ON s.user_id = sub.student_id AND sub.assignment_id = %s
            LEFT JOIN Documents d ON sub.document_id = d.id
            WHERE s.class_id = %s
            ORDER BY s.register_number ASC
        """
        cur.execute(query, (assign_id, assign['class_id']))
        rows = cur.fetchall()

        result = []
        for r in rows:
            result.append({
                'student_id': r['student_id'],
                'student_name': r['student_name'],
                'register_number': r['register_number'],
                'submission_id': r['submission_id'],
                'submitted_at': r['submitted_at'].isoformat() if r['submitted_at'] else None,
                'status': r['submission_status'] or 'pending',
                'marks': float(r['marks']) if r['marks'] is not None else None,
                'feedback': r['feedback'],
                'submission_count': r['submission_count'] or 0,
                'last_resubmitted_at': r['last_resubmitted_at'].isoformat() if r['last_resubmitted_at'] else None,
                'is_late': r['is_late'] or False,
                'document_id': r['doc_id'],
                'filename': r['original_filename']
            })

        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 9. EVALUATE SUBMISSION
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('/evaluate/<int:sub_id>', methods=['POST'])
@token_required(allowed_roles=['admin', 'faculty'])
def evaluate_submission(current_user, sub_id):
    data = request.json
    marks = data.get('marks')
    feedback = data.get('feedback', '').strip()

    if marks is None:
        return jsonify({'message': 'marks value is required.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Find submission and corresponding assignment configurations
        cur.execute("""
            SELECT s.*, a.max_marks, a.title as assignment_title, a.class_id, a.subject_id, a.created_by
            FROM AssignmentSubmissions s
            JOIN Assignments a ON s.assignment_id = a.id
            WHERE s.id = %s
        """, (sub_id,))
        sub = cur.fetchone()
        if not sub:
            return jsonify({'message': 'Submission record not found.'}), 404

        # Verify Hierarchy Access
        if current_user['role'] == 'faculty':
            if sub['created_by'] != current_user['user_id']:
                if not check_teacher_hierarchy(cur, current_user['user_id'], sub['class_id'], sub['subject_id']):
                    return jsonify({'message': 'Unauthorized. You do not teach this subject/class.'}), 403

        # Validate marks limit
        try:
            marks_val = float(marks)
            max_marks_val = float(sub['max_marks'])
            if not (0 <= marks_val <= max_marks_val):
                return jsonify({'message': f'Marks {marks_val} out of range (0-{max_marks_val}).'}), 400
        except (ValueError, TypeError):
            return jsonify({'message': 'Marks must be a numeric value.'}), 400

        # Update evaluation info
        cur.execute("""
            UPDATE AssignmentSubmissions 
            SET marks = %s, feedback = %s, status = 'evaluated', 
                evaluated_by = %s, evaluated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (marks_val, feedback or None, current_user['user_id'], sub_id))

        log_activity(current_user['user_id'], 'ASSIGNMENT_EVALUATED', entity_type='assignment_submission', entity_id=sub_id,
                     new_data={'marks': marks_val, 'assignment_title': sub['assignment_title']}, cursor=cur)

        conn.commit()
        return jsonify({'message': 'Submission evaluated successfully.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 10. PUBLISH MARKS (MANUAL MARKS PUBLICATION WORKFLOW)
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('/<int:assign_id>/publish-marks', methods=['POST'])
@token_required(allowed_roles=['admin', 'faculty'])
def publish_marks(current_user, assign_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        assign, err = verify_assignment_teacher_access(cur, current_user['user_id'], assign_id)
        if err:
            return jsonify({'message': err}), 403 if err != "Assignment not found" else 404

        if assign['marks_published']:
            return jsonify({'message': 'Marks are already published for this assignment.'}), 400

        # Fetch all evaluated submissions
        cur.execute("""
            SELECT student_id, marks 
            FROM AssignmentSubmissions 
            WHERE assignment_id = %s AND status = 'evaluated'
        """, (assign_id,))
        subs = cur.fetchall()

        if not subs:
            return jsonify({'message': 'No evaluated submissions found to publish.'}), 400

        published_count = 0
        for s in subs:
            stu_id = s['student_id']
            marks_val = float(s['marks'])

            # UPSERT into Marks table
            cur.execute("""
                SELECT id FROM Marks 
                WHERE student_id = %s AND subject_id = %s AND mark_type = 'Assignment' AND mark_name = %s
            """, (stu_id, assign['subject_id'], assign['title']))
            existing = cur.fetchone()

            if existing:
                cur.execute("""
                    UPDATE Marks SET marks = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (marks_val, current_user['user_id'], existing['id']))
            else:
                cur.execute("""
                    INSERT INTO Marks (student_id, subject_id, mark_type, mark_name, marks, updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (stu_id, assign['subject_id'], 'Assignment', assign['title'], marks_val, current_user['user_id']))

            # Dispatch notification
            create_notification(cur, stu_id, 'Assignment Marks Published',
                                f'Grades published for assignment "{assign["title"]}". Score: {marks_val}/{float(assign["max_marks"])}.', 'assignment')
            published_count += 1

        # Update assignment config
        cur.execute("UPDATE Assignments SET marks_published = TRUE WHERE id = %s", (assign_id,))

        log_activity(current_user['user_id'], 'ASSIGNMENT_MARKS_PUBLISHED', entity_type='assignment', entity_id=assign_id,
                     new_data={'published_records': published_count}, cursor=cur)

        conn.commit()
        return jsonify({'message': f'Grades successfully published for {published_count} students.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 11. ASSIGNMENT STATISTICS ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────
@assignments_bp.route('/<int:assign_id>/stats', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def get_assignment_stats(current_user, assign_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        assign, err = verify_assignment_teacher_access(cur, current_user['user_id'], assign_id)
        if err:
            return jsonify({'message': err}), 403 if err != "Assignment not found" else 404

        # Enrolled Students Count
        cur.execute("SELECT COUNT(*) as count FROM Students WHERE class_id = %s", (assign['class_id'],))
        total_students = cur.fetchone()['count']

        # Submissions Count
        cur.execute("SELECT COUNT(*) as count FROM AssignmentSubmissions WHERE assignment_id = %s", (assign_id,))
        total_submitted = cur.fetchone()['count']

        # Evaluated Count
        cur.execute("SELECT COUNT(*) as count FROM AssignmentSubmissions WHERE assignment_id = %s AND status = 'evaluated'", (assign_id,))
        total_evaluated = cur.fetchone()['count']

        # Pending evaluation
        pending_evaluation = total_submitted - total_evaluated

        # Late Submissions
        cur.execute("SELECT COUNT(*) as count FROM AssignmentSubmissions WHERE assignment_id = %s AND is_late = TRUE", (assign_id,))
        late_submissions = cur.fetchone()['count']

        # Grades stats (Average, Min, Max)
        cur.execute("""
            SELECT AVG(marks) as avg_score, MIN(marks) as min_score, MAX(marks) as max_score
            FROM AssignmentSubmissions
            WHERE assignment_id = %s AND status = 'evaluated'
        """, (assign_id,))
        grades = cur.fetchone()

        avg_score = float(grades['avg_score']) if grades['avg_score'] is not None else None
        min_score = float(grades['min_score']) if grades['min_score'] is not None else None
        max_score = float(grades['max_score']) if grades['max_score'] is not None else None

        result = {
            'total_students': total_students,
            'total_submitted': total_submitted,
            'total_evaluated': total_evaluated,
            'pending_evaluation': pending_evaluation,
            'late_submissions': late_submissions,
            'average_score': avg_score,
            'min_score': min_score,
            'max_score': max_score
        }

        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()
