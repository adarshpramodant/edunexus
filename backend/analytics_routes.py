import os
import sys
import csv
import io
import datetime
from flask import Blueprint, request, jsonify, make_response

# Adjust path to import db, auth_middleware, activity_logger
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection
from auth_middleware import token_required
from activity_logger import log_activity

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

# ─────────────────────────────────────────────────────────────────────────────
# Helper: Enforce Class/Teacher Hierarchy Security
# ─────────────────────────────────────────────────────────────────────────────
def check_teacher_hierarchy(cur, teacher_id, class_id):
    """
    Returns True if teacher_id is the Class Teacher, Vice Class Teacher,
    or an Assigned Subject Teacher for the specific class_id.
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
        WHERE teacher_id = %s AND class_id = %s
    """, (teacher_id, class_id))
    if cur.fetchone():
        return True

    return False

def get_user_institution(cur, user_id):
    cur.execute("SELECT institution_id FROM Users WHERE id = %s", (user_id,))
    res = cur.fetchone()
    return res['institution_id'] if res else None

# Helper: Fetch active thresholds (or return standard defaults)
def get_active_thresholds(cur, inst_id):
    cur.execute("SELECT * FROM AnalyticsThresholds WHERE institution_id = %s", (inst_id,))
    row = cur.fetchone()
    if row:
        return {
            'attendance': float(row['attendance_threshold']),
            'assignment': float(row['assignment_threshold']),
            'marks': float(row['marks_threshold'])
        }
    return {
        'attendance': 75.00,
        'assignment': 60.00,
        'marks': 50.00
    }

# Helper: Determine trend for a single student based on Marks history
def detect_student_trend(cur, student_id):
    # Fetch all marks for this student, ordered by updated_at or id
    cur.execute("""
        SELECT marks FROM Marks 
        WHERE student_id = %s 
        ORDER BY updated_at ASC, id ASC
    """, (student_id,))
    rows = cur.fetchall()
    
    if len(rows) < 2:
        return 'STABLE'

    marks_list = [float(r['marks']) for r in rows if r['marks'] is not None]
    if len(marks_list) < 2:
        return 'STABLE'

    half = len(marks_list) // 2
    early_avg = sum(marks_list[:half]) / half
    late_avg = sum(marks_list[half:]) / (len(marks_list) - half)

    diff = late_avg - early_avg
    if diff > 2.00:
        return 'IMPROVING'
    elif diff < -2.00:
        return 'DECLINING'
    return 'STABLE'

# Helper: Compute risk reasons and severity levels
def compute_risk_profile(student, thresholds):
    reasons = []
    attendance = float(student['attendance_percentage'])
    assignment = float(student['assignment_completion_percentage'])
    marks = float(student['average_marks'])

    att_t = thresholds['attendance']
    assign_t = thresholds['assignment']
    marks_t = thresholds['marks']

    # 1. Risk reason checks
    if attendance < att_t:
        reasons.append('LOW_ATTENDANCE')
    if assignment < assign_t:
        reasons.append('MISSING_ASSIGNMENTS')
    if marks < marks_t:
        reasons.append('LOW_MARKS')

    # 2. Severity levels calculations
    crossed_count = len(reasons)
    severity = 'LOW'
    
    if crossed_count == 3:
        severity = 'CRITICAL'
    elif crossed_count == 2:
        severity = 'HIGH'
    elif crossed_count == 1:
        severity = 'MEDIUM'
    else:
        # LOW checks (warning boundary)
        is_close_att = (attendance >= att_t and attendance < att_t + 5.0)
        is_close_assign = (assignment >= assign_t and assignment < assign_t + 10.0)
        is_close_marks = (marks >= marks_t and marks < marks_t + 5.0)
        if is_close_att or is_close_assign or is_close_marks:
            severity = 'LOW'
        else:
            severity = 'NONE'

    return reasons, severity

# ─────────────────────────────────────────────────────────────────────────────
# 1. THRESHOLD SETTINGS (`GET /settings`, `POST /settings`)
# ─────────────────────────────────────────────────────────────────────────────
@analytics_bp.route('/settings', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def get_settings(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify({'message': 'Institution context not found.'}), 400
        
        t = get_active_thresholds(cur, inst_id)
        return jsonify(t), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

@analytics_bp.route('/settings', methods=['POST'])
@token_required(allowed_roles=['admin'])
def update_settings(current_user):
    data = request.json
    att_t = data.get('attendance')
    assign_t = data.get('assignment')
    marks_t = data.get('marks')

    if att_t is None or assign_t is None or marks_t is None:
        return jsonify({'message': 'attendance, assignment, and marks thresholds are required.'}), 400

    try:
        att_v = float(att_t)
        assign_v = float(assign_t)
        marks_v = float(marks_t)
        if not (0 <= att_v <= 100 and 0 <= assign_v <= 100 and 0 <= marks_v <= 100):
            return jsonify({'message': 'Threshold percentages must lie between 0 and 100.'}), 400
    except ValueError:
        return jsonify({'message': 'Invalid numeric threshold percentage.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify({'message': 'Institution context not found.'}), 400

        cur.execute("""
            INSERT INTO AnalyticsThresholds (institution_id, attendance_threshold, assignment_threshold, marks_threshold, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (institution_id) DO UPDATE 
            SET attendance_threshold = EXCLUDED.attendance_threshold,
                assignment_threshold = EXCLUDED.assignment_threshold,
                marks_threshold = EXCLUDED.marks_threshold,
                updated_at = CURRENT_TIMESTAMP
        """, (inst_id, att_v, assign_v, marks_v))

        log_activity(current_user['user_id'], 'ANALYTICS_SETTINGS_UPDATED', entity_type='institution', entity_id=str(inst_id),
                     new_data={'attendance': att_v, 'assignment': assign_v, 'marks': marks_v}, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Analytics thresholds updated successfully.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 2. AT-RISK STUDENTS LIST (`GET /at-risk`)
# ─────────────────────────────────────────────────────────────────────────────
@analytics_bp.route('/at-risk', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def list_at_risk_students(current_user):
    class_id_filter = request.args.get('class_id')
    reason_filter = request.args.get('reason') # 'LOW_ATTENDANCE', 'MISSING_ASSIGNMENTS', 'LOW_MARKS'
    severity_filter = request.args.get('severity') # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    search_filter = request.args.get('search', '').strip()
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify([]), 200

        thresholds = get_active_thresholds(cur, inst_id)

        # Build SQL query scoped by Admin vs Faculty
        query = """
            SELECT a.*
            FROM vw_StudentPerformanceAnalytics a
            WHERE a.institution_id = %s
        """
        params = [inst_id]

        if current_user['role'] == 'faculty':
            if class_id_filter:
                if not check_teacher_hierarchy(cur, current_user['user_id'], int(class_id_filter)):
                    return jsonify({'message': 'Unauthorized class scope.'}), 403
                query += " AND a.class_id = %s"
                params.append(int(class_id_filter))
            else:
                # Faculty sees students only in classes they teach
                query += """
                    AND a.class_id IN (
                        SELECT class_id FROM ClassAssignments WHERE teacher_id = %s
                        UNION
                        SELECT class_id FROM SubjectAssignments WHERE teacher_id = %s
                    )
                """
                params.extend([current_user['user_id'], current_user['user_id']])
        else:
            if class_id_filter:
                query += " AND a.class_id = %s"
                params.append(int(class_id_filter))

        if search_filter:
            query += " AND (a.student_name ILIKE %s OR a.register_number ILIKE %s)"
            params.extend([f"%{search_filter}%", f"%{search_filter}%"])

        query += " ORDER BY a.student_name ASC"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        # Compute dynamic at-risk profiles, reason tags, and severity
        at_risk_list = []
        for r in rows:
            reasons, severity = compute_risk_profile(r, thresholds)
            
            # Filter logically in memory to support dynamic custom configurations
            if severity == 'NONE':
                continue
            if reason_filter and reason_filter not in reasons:
                continue
            if severity_filter and severity_filter != severity:
                continue

            trend = detect_student_trend(cur, r['student_id'])
            
            at_risk_list.append({
                'student_id': r['student_id'],
                'student_name': r['student_name'],
                'register_number': r['register_number'],
                'class_id': r['class_id'],
                'class_section': r['class_section'],
                'department_name': r['department_name'],
                'semester_number': r['semester_number'],
                'attendance_percentage': float(r['attendance_percentage']),
                'assignment_completion_percentage': float(r['assignment_completion_percentage']),
                'average_marks': float(r['average_marks']),
                'risk_reasons': reasons,
                'severity': severity,
                'trend': trend
            })

        # Apply in-memory pagination
        paginated = at_risk_list[offset:offset+limit]
        
        log_activity(current_user['user_id'], 'ANALYTICS_REPORT_GENERATED', entity_type='class_report', entity_id='at-risk',
                     new_data={'class_id': class_id_filter, 'results_count': len(at_risk_list)}, cursor=cur)
        conn.commit()

        return jsonify({
            'total': len(at_risk_list),
            'limit': limit,
            'offset': offset,
            'students': paginated
        }), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 3. TOP PERFORMERS LIST (`GET /top-performers`)
# ─────────────────────────────────────────────────────────────────────────────
@analytics_bp.route('/top-performers', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def list_top_performers(current_user):
    class_id_filter = request.args.get('class_id')
    search_filter = request.args.get('search', '').strip()
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify([]), 200

        # Build SQL query scoped by Admin vs Faculty
        query = """
            SELECT a.*
            FROM vw_StudentPerformanceAnalytics a
            WHERE a.institution_id = %s AND a.average_marks >= 80.00
        """
        params = [inst_id]

        if current_user['role'] == 'faculty':
            if class_id_filter:
                if not check_teacher_hierarchy(cur, current_user['user_id'], int(class_id_filter)):
                    return jsonify({'message': 'Unauthorized class scope.'}), 403
                query += " AND a.class_id = %s"
                params.append(int(class_id_filter))
            else:
                query += """
                    AND a.class_id IN (
                        SELECT class_id FROM ClassAssignments WHERE teacher_id = %s
                        UNION
                        SELECT class_id FROM SubjectAssignments WHERE teacher_id = %s
                    )
                """
                params.extend([current_user['user_id'], current_user['user_id']])
        else:
            if class_id_filter:
                query += " AND a.class_id = %s"
                params.append(int(class_id_filter))

        if search_filter:
            query += " AND (a.student_name ILIKE %s OR a.register_number ILIKE %s)"
            params.extend([f"%{search_filter}%", f"%{search_filter}%"])

        query += " ORDER BY a.average_marks DESC"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        top_list = []
        for r in rows:
            trend = detect_student_trend(cur, r['student_id'])
            top_list.append({
                'student_id': r['student_id'],
                'student_name': r['student_name'],
                'register_number': r['register_number'],
                'class_id': r['class_id'],
                'class_section': r['class_section'],
                'department_name': r['department_name'],
                'semester_number': r['semester_number'],
                'average_marks': float(r['average_marks']),
                'attendance_percentage': float(r['attendance_percentage']),
                'assignment_completion_percentage': float(r['assignment_completion_percentage']),
                'trend': trend
            })

        paginated = top_list[offset:offset+limit]
        
        log_activity(current_user['user_id'], 'ANALYTICS_REPORT_GENERATED', entity_type='class_report', entity_id='top-performers',
                     new_data={'class_id': class_id_filter, 'results_count': len(top_list)}, cursor=cur)
        conn.commit()

        return jsonify({
            'total': len(top_list),
            'limit': limit,
            'offset': offset,
            'students': paginated
        }), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 4. CLASS PERFORMANCE REPORT (`GET /class/<int:class_id>`)
# ─────────────────────────────────────────────────────────────────────────────
@analytics_bp.route('/class/<int:class_id>', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def get_class_report(current_user, class_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify({'message': 'Institution context not found.'}), 400

        # Enforce faculty class context boundaries
        if current_user['role'] == 'faculty' and not check_teacher_hierarchy(cur, current_user['user_id'], class_id):
            return jsonify({'message': 'Unauthorized class scope.'}), 403

        # 1. Fetch Class details
        cur.execute("""
            SELECT c.*, dept.name AS department_name, sem.number AS semester_number 
            FROM Classes c
            JOIN Departments dept ON c.department_id = dept.id
            JOIN Semesters sem ON c.semester_id = sem.id
            WHERE c.id = %s
        """, (class_id,))
        cls_row = cur.fetchone()
        if not cls_row:
            return jsonify({'message': 'Class not found.'}), 404

        thresholds = get_active_thresholds(cur, inst_id)

        # 2. Fetch all students in this class
        cur.execute("""
            SELECT a.*
            FROM vw_StudentPerformanceAnalytics a
            WHERE a.class_id = %s
        """, (class_id,))
        students = cur.fetchall()

        if not students:
            return jsonify({
                'class_id': class_id,
                'class_section': cls_row['section'],
                'department_name': cls_row['department_name'],
                'semester_number': cls_row['semester_number'],
                'total_students': 0,
                'average_attendance': 100.0,
                'average_assignment_completion': 100.0,
                'average_class_marks': 0.0,
                'at_risk_students_count': 0,
                'top_performers_count': 0,
                'marks_distribution': { 'A+': 0, 'A': 0, 'B+': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0 }
            }), 200

        # 3. Aggregate metrics
        total_st = len(students)
        sum_att = 0.0
        sum_assign = 0.0
        sum_marks = 0.0
        at_risk_cnt = 0
        top_perf_cnt = 0
        dist = { 'A+': 0, 'A': 0, 'B+': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0 }

        for s in students:
            sum_att += float(s['attendance_percentage'])
            sum_assign += float(s['assignment_completion_percentage'])
            m_avg = float(s['average_marks'])
            sum_marks += m_avg

            # At-risk & top performers
            reasons, severity = compute_risk_profile(s, thresholds)
            if severity != 'NONE':
                at_risk_cnt += 1
            if m_avg >= 80.00:
                top_perf_cnt += 1

            # Grading distribution bands
            if m_avg >= 90: dist['A+'] += 1
            elif m_avg >= 80: dist['A'] += 1
            elif m_avg >= 70: dist['B+'] += 1
            elif m_avg >= 60: dist['B'] += 1
            elif m_avg >= 50: dist['C'] += 1
            elif m_avg >= 40: dist['D'] += 1
            else: dist['F'] += 1

        log_activity(current_user['user_id'], 'ANALYTICS_REPORT_GENERATED', entity_type='class_report', entity_id=str(class_id), cursor=cur)
        conn.commit()

        return jsonify({
            'class_id': class_id,
            'class_section': cls_row['section'],
            'department_name': cls_row['department_name'],
            'semester_number': cls_row['semester_number'],
            'total_students': total_st,
            'average_attendance': round(sum_att / total_st, 2),
            'average_assignment_completion': round(sum_assign / total_st, 2),
            'average_class_marks': round(sum_marks / total_st, 2),
            'at_risk_students_count': at_risk_cnt,
            'top_performers_count': top_perf_cnt,
            'marks_distribution': dist
        }), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 5. SUBJECT RISK ANALYSIS REPORT (`GET /subject/<int:subject_id>`)
# ─────────────────────────────────────────────────────────────────────────────
@analytics_bp.route('/subject/<int:subject_id>', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def get_subject_report(current_user, subject_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Get Subject details
        cur.execute("SELECT * FROM Subjects WHERE id = %s", (subject_id,))
        sub = cur.fetchone()
        if not sub:
            return jsonify({'message': 'Subject not found.'}), 404

        inst_id = get_user_institution(cur, current_user['user_id'])
        # Faculty boundary check
        if current_user['role'] == 'faculty' and not check_teacher_hierarchy(cur, current_user['user_id'], sub['class_id']):
            return jsonify({'message': 'Unauthorized class scope.'}), 403

        # Query subject risk analysis view
        cur.execute("SELECT * FROM vw_SubjectRiskAnalysis WHERE subject_id = %s", (subject_id,))
        row = cur.fetchone()
        
        if not row:
            return jsonify({
                'subject_id': subject_id,
                'subject_name': sub['name'],
                'subject_code': sub['code'],
                'class_id': sub['class_id'],
                'average_marks': 0.0,
                'highest_marks': 0.0,
                'lowest_marks': 0.0,
                'graded_students_count': 0,
                'subject_attendance_percentage': 100.0,
                'total_hours': 0,
                'total_absences': 0
            }), 200

        log_activity(current_user['user_id'], 'ANALYTICS_REPORT_GENERATED', entity_type='subject_report', entity_id=str(subject_id), cursor=cur)
        conn.commit()

        return jsonify({
            'subject_id': int(row['subject_id']),
            'subject_name': row['subject_name'],
            'subject_code': row['subject_code'] or '—',
            'class_id': int(row['class_id']),
            'class_section': row['class_section'],
            'department_name': row['department_name'],
            'semester_number': int(row['semester_number']),
            'average_marks': float(row['average_marks']),
            'highest_marks': float(row['highest_marks']),
            'lowest_marks': float(row['lowest_marks']),
            'graded_students_count': int(row['graded_students_count']),
            'subject_attendance_percentage': float(row['subject_attendance_percentage']),
            'total_hours': int(row['total_hours']),
            'total_absences': int(row['total_absences'])
        }), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 6. FACULTY SUMMARY METRICS (`GET /summary`)
# ─────────────────────────────────────────────────────────────────────────────
@analytics_bp.route('/summary', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def get_faculty_summary(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify({}), 200

        thresholds = get_active_thresholds(cur, inst_id)

        # Scoped student fetch
        query = "SELECT * FROM vw_StudentPerformanceAnalytics WHERE institution_id = %s"
        params = [inst_id]

        if current_user['role'] == 'faculty':
            query += """
                AND class_id IN (
                    SELECT class_id FROM ClassAssignments WHERE teacher_id = %s
                    UNION
                    SELECT class_id FROM SubjectAssignments WHERE teacher_id = %s
                )
            """
            params.extend([current_user['user_id'], current_user['user_id']])

        cur.execute(query, tuple(params))
        students = cur.fetchall()

        total_st = len(students)
        at_risk_cnt = 0
        top_perf_cnt = 0
        sum_att = 0.0
        sum_assign = 0.0

        for s in students:
            sum_att += float(s['attendance_percentage'])
            sum_assign += float(s['assignment_completion_percentage'])

            reasons, severity = compute_risk_profile(s, thresholds)
            if severity != 'NONE':
                at_risk_cnt += 1
            if float(s['average_marks']) >= 80.00:
                top_perf_cnt += 1

        avg_att = round(sum_att / total_st, 2) if total_st > 0 else 100.0
        avg_assign = round(sum_assign / total_st, 2) if total_st > 0 else 100.0

        return jsonify({
            'total_students': total_st,
            'at_risk_count': at_risk_cnt,
            'top_performers_count': top_perf_cnt,
            'average_attendance': avg_att,
            'average_assignment_completion': avg_assign
        }), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 7. STUDENT PERSONAL ANALYTICS (`GET /student`)
# ─────────────────────────────────────────────────────────────────────────────
@analytics_bp.route('/student', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def get_student_personal_analytics(current_user):
    target_student_id = request.args.get('student_id')

    # Security scoping: Student role can ONLY query their own ID
    if current_user['role'] == 'student':
        student_id = current_user['user_id']
    else:
        if not target_student_id:
            return jsonify({'message': 'student_id parameter is required for administrators and faculty.'}), 400
        student_id = int(target_student_id)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify({'message': 'Institution context not found.'}), 400

        # Scoping check for Faculty
        if current_user['role'] == 'faculty':
            cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (student_id,))
            stu_cls = cur.fetchone()
            if not stu_cls or not check_teacher_hierarchy(cur, current_user['user_id'], stu_cls['class_id']):
                return jsonify({'message': 'Unauthorized class scope.'}), 403

        # Fetch student stats
        cur.execute("SELECT * FROM vw_StudentPerformanceAnalytics WHERE student_id = %s", (student_id,))
        student = cur.fetchone()
        if not student:
            return jsonify({'message': 'Student analytics profile not found.'}), 404

        thresholds = get_active_thresholds(cur, inst_id)
        reasons, severity = compute_risk_profile(student, thresholds)
        trend = detect_student_trend(cur, student_id)

        # Get class averages to compare against
        cur.execute("""
            SELECT ROUND(AVG(attendance_percentage), 2) AS class_avg_att,
                   ROUND(AVG(assignment_completion_percentage), 2) AS class_avg_assign,
                   ROUND(AVG(average_marks), 2) AS class_avg_marks
            FROM vw_StudentPerformanceAnalytics
            WHERE class_id = %s
        """, (student['class_id'],))
        class_avgs = cur.fetchone()

        # Compute rank inside class
        cur.execute("""
            SELECT student_id, RANK() OVER (ORDER BY average_marks DESC) as rank_pos
            FROM vw_StudentPerformanceAnalytics
            WHERE class_id = %s
        """, (student['class_id'],))
        ranks = cur.fetchall()
        class_rank = 1
        for r in ranks:
            if r['student_id'] == student_id:
                class_rank = r['rank_pos']
                break

        log_activity(current_user['user_id'], 'ANALYTICS_REPORT_GENERATED', entity_type='student_analytics', entity_id=str(student_id), cursor=cur)
        conn.commit()

        return jsonify({
            'student_id': student_id,
            'student_name': student['student_name'],
            'register_number': student['register_number'],
            'class_id': student['class_id'],
            'class_section': student['class_section'],
            'department_name': student['department_name'],
            'semester_number': student['semester_number'],
            'attendance_percentage': float(student['attendance_percentage']),
            'assignment_completion_percentage': float(student['assignment_completion_percentage']),
            'average_marks': float(student['average_marks']),
            'class_average_attendance': float(class_avgs['class_avg_att']) if class_avgs['class_avg_att'] else 100.0,
            'class_average_assignment_completion': float(class_avgs['class_avg_assign']) if class_avgs['class_avg_assign'] else 100.0,
            'class_average_marks': float(class_avgs['class_avg_marks']) if class_avgs['class_avg_marks'] else 0.0,
            'class_rank': int(class_rank),
            'class_total_students': len(ranks),
            'risk_reasons': reasons,
            'severity': severity,
            'trend': trend
        }), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 8. CSV EXPORT ENDPOINT (`GET /export/csv`)
# ─────────────────────────────────────────────────────────────────────────────
@analytics_bp.route('/export/csv', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def export_csv(current_user):
    class_id_filter = request.args.get('class_id')
    export_type = request.args.get('type', 'at-risk') # 'at-risk' or 'top-performers'

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify({'message': 'Institution context not found.'}), 400

        thresholds = get_active_thresholds(cur, inst_id)

        # 1. Fetch Students
        query = """
            SELECT a.*
            FROM vw_StudentPerformanceAnalytics a
            WHERE a.institution_id = %s
        """
        params = [inst_id]

        if current_user['role'] == 'faculty':
            if class_id_filter:
                if not check_teacher_hierarchy(cur, current_user['user_id'], int(class_id_filter)):
                    return jsonify({'message': 'Unauthorized class scope.'}), 403
                query += " AND a.class_id = %s"
                params.append(int(class_id_filter))
            else:
                query += """
                    AND a.class_id IN (
                        SELECT class_id FROM ClassAssignments WHERE teacher_id = %s
                        UNION
                        SELECT class_id FROM SubjectAssignments WHERE teacher_id = %s
                    )
                """
                params.extend([current_user['user_id'], current_user['user_id']])
        else:
            if class_id_filter:
                query += " AND a.class_id = %s"
                params.append(int(class_id_filter))

        query += " ORDER BY a.student_name ASC"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        # 2. Build CSV In-Memory Stream
        output = io.StringIO()
        writer = csv.writer(output)

        if export_type == 'at-risk':
            writer.writerow(['Register Number', 'Student Name', 'Class', 'Department', 'Semester', 'Attendance %', 'Assignment Completion %', 'Average Marks', 'Risk Reasons', 'Severity', 'Trend'])
            for r in rows:
                reasons, severity = compute_risk_profile(r, thresholds)
                if severity == 'NONE':
                    continue
                trend = detect_student_trend(cur, r['student_id'])
                writer.writerow([
                    r['register_number'],
                    r['student_name'],
                    r['class_section'],
                    r['department_name'],
                    r['semester_number'],
                    f"{float(r['attendance_percentage']):.2f}%",
                    f"{float(r['assignment_completion_percentage']):.2f}%",
                    f"{float(r['average_marks']):.2f}",
                    ";".join(reasons),
                    severity,
                    trend
                ])
        else:
            writer.writerow(['Register Number', 'Student Name', 'Class', 'Department', 'Semester', 'Average Marks', 'Attendance %', 'Assignment Completion %', 'Trend'])
            for r in rows:
                if float(r['average_marks']) < 80.00:
                    continue
                trend = detect_student_trend(cur, r['student_id'])
                writer.writerow([
                    r['register_number'],
                    r['student_name'],
                    r['class_section'],
                    r['department_name'],
                    r['semester_number'],
                    f"{float(r['average_marks']):.2f}",
                    f"{float(r['attendance_percentage']):.2f}%",
                    f"{float(r['assignment_completion_percentage']):.2f}%",
                    trend
                ])

        log_activity(current_user['user_id'], 'ANALYTICS_EXPORT_CREATED', entity_type='export', entity_id=export_type,
                     new_data={'class_id': class_id_filter, 'format': 'csv'}, cursor=cur)
        conn.commit()

        # Stream response
        res = make_response(output.getvalue())
        res.headers['Content-Disposition'] = f"attachment; filename=EduNexus_{export_type}_Report_{datetime.datetime.now().strftime('%Y%md')}.csv"
        res.headers['Content-Type'] = 'text/csv'
        return res

    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 9. PDF EXPORT ENDPOINT (`GET /export/pdf`)
# ─────────────────────────────────────────────────────────────────────────────
@analytics_bp.route('/export/pdf', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def export_pdf(current_user):
    class_id = request.args.get('class_id')
    if not class_id:
        return jsonify({'message': 'class_id parameter is required for PDF generation.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        class_id_val = int(class_id)
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify({'message': 'Institution context not found.'}), 400

        # Faculty security check
        if current_user['role'] == 'faculty' and not check_teacher_hierarchy(cur, current_user['user_id'], class_id_val):
            return jsonify({'message': 'Unauthorized class scope.'}), 403

        # Fetch Class info
        cur.execute("""
            SELECT c.*, dept.name AS department_name, sem.number AS semester_number 
            FROM Classes c
            JOIN Departments dept ON c.department_id = dept.id
            JOIN Semesters sem ON c.semester_id = sem.id
            WHERE c.id = %s
        """, (class_id_val,))
        cls_row = cur.fetchone()
        if not cls_row:
            return jsonify({'message': 'Class not found.'}), 404

        thresholds = get_active_thresholds(cur, inst_id)

        # Fetch student listing
        cur.execute("""
            SELECT a.*
            FROM vw_StudentPerformanceAnalytics a
            WHERE a.class_id = %s
            ORDER BY a.student_name ASC
        """, (class_id_val,))
        students = cur.fetchall()

        # Build ReportLab PDF flowable stream
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=36, rightMargin=36,
            topMargin=40, bottomMargin=40,
            title=f"Class Performance Report - {cls_row['department_name']}"
        )

        styles = getSampleStyleSheet()
        TITLE = ParagraphStyle('T', fontName='Helvetica-Bold', fontSize=15, textColor=colors.HexColor('#1e1b4b'), alignment=1, spaceAfter=4)
        SUBTITLE = ParagraphStyle('Sub', fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#64748b'), alignment=1, spaceAfter=10)
        CELL_BOLD = ParagraphStyle('CB', fontName='Helvetica-Bold', fontSize=8, textColor=colors.HexColor('#1e1b4b'))
        CELL_BODY = ParagraphStyle('C', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#1e1b4b'))
        LABEL_COL = colors.HexColor('#3730a3')
        BORDER_COL = colors.HexColor('#cbd5e1')

        story = []
        story.append(Paragraph('EduNexus Academic Performance Analytics', TITLE))
        story.append(Paragraph(
            f"Class: {cls_row['department_name']} &nbsp;|&nbsp; Sem: {cls_row['semester_number']} &nbsp;|&nbsp; Sec: {cls_row['section']} &nbsp;|&nbsp; Date: {datetime.date.today().strftime('%Y-%m-%d')}",
            SUBTITLE
        ))
        story.append(HRFlowable(width=523, color=BORDER_COL, thickness=0.5, spaceAfter=10))

        # Metrics Counters Card
        total_st = len(students)
        at_risk_cnt = 0
        sum_att = 0.0
        sum_assign = 0.0
        sum_marks = 0.0

        for s in students:
            sum_att += float(s['attendance_percentage'])
            sum_assign += float(s['assignment_completion_percentage'])
            sum_marks += float(s['average_marks'])
            _, severity = compute_risk_profile(s, thresholds)
            if severity != 'NONE':
                at_risk_cnt += 1

        avg_att = round(sum_att / total_st, 2) if total_st > 0 else 100.0
        avg_assign = round(sum_assign / total_st, 2) if total_st > 0 else 100.0
        avg_marks = round(sum_marks / total_st, 2) if total_st > 0 else 0.0

        metric_row = [
            [Paragraph('<b>Total Students</b>', CELL_BOLD), Paragraph('<b>At-Risk Count</b>', CELL_BOLD), Paragraph('<b>Avg Attendance</b>', CELL_BOLD), Paragraph('<b>Avg Completion</b>', CELL_BOLD), Paragraph('<b>Avg Marks</b>', CELL_BOLD)],
            [Paragraph(str(total_st), CELL_BODY), Paragraph(str(at_risk_cnt), CELL_BODY), Paragraph(f"{avg_att}%", CELL_BODY), Paragraph(f"{avg_assign}%", CELL_BODY), Paragraph(f"{avg_marks}", CELL_BODY)]
        ]
        metric_table = Table(metric_row, colWidths=[104]*5)
        metric_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e0e7ff')),
            ('GRID', (0,0), (-1,-1), 0.5, BORDER_COL),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(metric_table)
        story.append(Spacer(1, 15))

        # Main Roster Table
        roster_rows = [[
            Paragraph('<b>Reg Number</b>', CELL_BOLD),
            Paragraph('<b>Student Name</b>', CELL_BOLD),
            Paragraph('<b>Att %</b>', CELL_BOLD),
            Paragraph('<b>Assign %</b>', CELL_BOLD),
            Paragraph('<b>Avg Mark</b>', CELL_BOLD),
            Paragraph('<b>Severity</b>', CELL_BOLD),
            Paragraph('<b>Trend</b>', CELL_BOLD),
        ]]

        for s in students:
            reasons, severity = compute_risk_profile(s, thresholds)
            trend = detect_student_trend(cur, s['student_id'])
            
            # Severity color coding
            sev_c = '#10b981' if severity == 'NONE' else '#fbbf24' if severity == 'LOW' else '#f59e0b' if severity == 'MEDIUM' else '#ef4444' if severity == 'HIGH' else '#b91c1c'
            trend_c = '#10b981' if trend == 'IMPROVING' else '#ef4444' if trend == 'DECLINING' else '#64748b'

            roster_rows.append([
                Paragraph(s['register_number'], CELL_BODY),
                Paragraph(s['student_name'][:25], CELL_BODY),
                Paragraph(f"{float(s['attendance_percentage']):.1f}%", CELL_BODY),
                Paragraph(f"{float(s['assignment_completion_percentage']):.1f}%", CELL_BODY),
                Paragraph(f"{float(s['average_marks']):.1f}", CELL_BODY),
                Paragraph(f'<font color="{sev_c}"><b>{severity}</b></font>', CELL_BODY),
                Paragraph(f'<font color="{trend_c}"><b>{trend}</b></font>', CELL_BODY),
            ])

        roster_table = Table(roster_rows, colWidths=[75, 130, 55, 55, 55, 75, 78], repeatRows=1)
        roster_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), LABEL_COL),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 0.4, BORDER_COL),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(roster_table)

        doc.build(story)

        log_activity(current_user['user_id'], 'ANALYTICS_EXPORT_CREATED', entity_type='export', entity_id='pdf_report',
                     new_data={'class_id': class_id_val, 'format': 'pdf'}, cursor=cur)
        conn.commit()

        # Build response stream
        res = make_response(buf.getvalue())
        res.headers['Content-Disposition'] = f"attachment; filename=EduNexus_Class_Report_{cls_row['department_name']}_{datetime.date.today().strftime('%Y%md')}.pdf"
        res.headers['Content-Type'] = 'application/pdf'
        return res

    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()
