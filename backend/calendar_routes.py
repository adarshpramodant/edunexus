import os
import sys
import json
from datetime import datetime
from flask import Blueprint, request, jsonify

# Adjust path to import db
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection
from auth_middleware import token_required
from activity_logger import log_activity
from notification_routes import create_notification, notify_class_students, notify_class_faculty

calendar_bp = Blueprint('calendar', __name__, url_prefix='/api/calendar')

# ─────────────────────────────────────────────────────────────────────────────
# Hierarchy Role Validation helper
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

# Shared helper to fetch a user's institution ID
def get_user_institution(cur, user_id):
    cur.execute("SELECT institution_id FROM Users WHERE id = %s", (user_id,))
    res = cur.fetchone()
    return res['institution_id'] if res else None

# Helper to verify event access/ownership
def verify_event_access(cur, user_id, role, event_id):
    cur.execute("SELECT * FROM AcademicEvents WHERE id = %s AND is_active = TRUE", (event_id,))
    event = cur.fetchone()
    if not event:
        return None, "Event not found"

    if role == 'admin':
        return event, None

    if role == 'faculty':
        if event['created_by'] == user_id:
            return event, None
        return None, "Unauthorized. You did not create this event."

    return None, "Unauthorized. Students cannot modify events."

# Helper to dynamically notify users based on event target scope
def notify_event_users(cur, inst_id, event, title_prefix, notif_action_text):
    title = f"{title_prefix}: {event['title']}"
    # Use clean formatting for datetimes in notifications
    start_str = event['start_date'].strftime('%Y-%m-%d %H:%M') if isinstance(event['start_date'], datetime) else str(event['start_date'])
    message = f"Event '{event['title']}' ({event['event_type']}) has been {notif_action_text}. Starts: {start_str}."
    
    if event['target_class_id']:
        notify_class_students(cur, event['target_class_id'], title, message, 'system')
        notify_class_faculty(cur, event['target_class_id'], title, message, 'system')
    else:
        # Institution-wide role-based scoping
        if event['target_role'] in ('all', None):
            cur.execute("SELECT id FROM Users WHERE institution_id = %s AND id != %s", (inst_id, event['created_by']))
        elif event['target_role'] == 'student':
            cur.execute("SELECT id FROM Users WHERE institution_id = %s AND role = 'student'", (inst_id,))
        elif event['target_role'] == 'faculty':
            cur.execute("SELECT id FROM Users WHERE institution_id = %s AND role = 'faculty'", (inst_id,))
        else:
            return
        
        users = cur.fetchall()
        for u in users:
            create_notification(cur, u['id'], title, message, 'system')

# ─────────────────────────────────────────────────────────────────────────────
# 1. CREATE EVENT
# ─────────────────────────────────────────────────────────────────────────────
@calendar_bp.route('/events', methods=['POST'])
@token_required(allowed_roles=['admin', 'faculty'])
def create_event(current_user):
    data = request.json
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    event_type = data.get('event_type')
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    target_role = data.get('target_role') # 'student', 'faculty', 'admin', 'all'
    target_class_id = data.get('target_class_id')
    status = data.get('status', 'published') # 'draft', 'published'
    document_id = data.get('document_id')
    event_color = data.get('event_color', 'indigo').strip()
    recurrence_pattern = data.get('recurrence_pattern', 'none')

    if not all([title, event_type, start_date_str, end_date_str]):
        return jsonify({'message': 'title, event_type, start_date, and end_date are required.'}), 400

    valid_types = ('holiday', 'internal_exam', 'university_exam', 'lab_exam', 'assignment_deadline', 'survey_deadline', 'project_review', 'seminar', 'workshop', 'event', 'other')
    if event_type not in valid_types:
        return jsonify({'message': f'Invalid event_type. Must be one of {valid_types}'}), 400

    if status not in ('draft', 'published'):
        return jsonify({'message': 'Initial status must be draft or published.'}), 400

    valid_recurrence = ('none', 'daily', 'weekly', 'monthly', 'yearly')
    if recurrence_pattern not in valid_recurrence:
        return jsonify({'message': f'Invalid recurrence_pattern. Must be one of {valid_recurrence}'}), 400

    try:
        start_date = datetime.strptime(start_date_str.replace('T', ' '), '%Y-%m-%d %H:%M:%S' if len(start_date_str) > 16 else '%Y-%m-%d %H:%M')
        end_date = datetime.strptime(end_date_str.replace('T', ' '), '%Y-%m-%d %H:%M:%S' if len(end_date_str) > 16 else '%Y-%m-%d %H:%M')
        if end_date < start_date:
            return jsonify({'message': 'end_date cannot be earlier than start_date.'}), 400
    except ValueError as e:
        return jsonify({'message': 'Invalid datetime format. Use YYYY-MM-DD HH:MM.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify({'message': 'Institution context not found.'}), 400

        # Enforce Faculty Role Hierarchy limits
        if current_user['role'] == 'faculty':
            if not target_class_id:
                return jsonify({'message': 'Faculty can only create class-level events.'}), 403
            if not check_teacher_hierarchy(cur, current_user['user_id'], target_class_id):
                return jsonify({'message': 'Unauthorized. You do not teach this target class.'}), 403

        # Target class parsing
        target_class_val = int(target_class_id) if target_class_id else None
        document_val = int(document_id) if document_id else None

        # Insert Event
        cur.execute("""
            INSERT INTO AcademicEvents (institution_id, title, description, event_type, start_date, end_date, target_role, target_class_id, created_by, status, document_id, event_color, recurrence_pattern)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (inst_id, title, description or None, event_type, start_date, end_date, target_role or None, target_class_val, current_user['user_id'], status, document_val, event_color, recurrence_pattern))
        event_id = cur.fetchone()['id']

        # Notify relevant users if published immediately
        if status == 'published':
            event_obj = {
                'title': title, 'event_type': event_type, 'start_date': start_date,
                'target_class_id': target_class_val, 'target_role': target_role, 'created_by': current_user['user_id']
            }
            notify_event_users(cur, inst_id, event_obj, 'New Event', 'published')

        log_activity(current_user['user_id'], 'EVENT_CREATED', entity_type='academic_event', entity_id=event_id,
                     new_data={'title': title, 'event_type': event_type, 'status': status}, cursor=cur)

        conn.commit()
        return jsonify({'message': 'Academic event created successfully.', 'event_id': event_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'message': 'Creation failed: ' + str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 2. UPDATE EVENT
# ─────────────────────────────────────────────────────────────────────────────
@calendar_bp.route('/events/<int:event_id>', methods=['PUT'])
@token_required(allowed_roles=['admin', 'faculty'])
def update_event(current_user, event_id):
    data = request.json
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    event_type = data.get('event_type')
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    target_role = data.get('target_role')
    target_class_id = data.get('target_class_id')
    status = data.get('status') # 'draft', 'published', 'completed'
    document_id = data.get('document_id')
    event_color = data.get('event_color')
    recurrence_pattern = data.get('recurrence_pattern')

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        event, err = verify_event_access(cur, current_user['user_id'], current_user['role'], event_id)
        if err:
            return jsonify({'message': err}), 403 if err != "Event not found" else 404

        update_fields = []
        params = []

        if title:
            update_fields.append("title = %s")
            params.append(title)
        if description is not None:
            update_fields.append("description = %s")
            params.append(description or None)
        if event_type:
            valid_types = ('holiday', 'internal_exam', 'university_exam', 'lab_exam', 'assignment_deadline', 'survey_deadline', 'project_review', 'seminar', 'workshop', 'event', 'other')
            if event_type not in valid_types:
                return jsonify({'message': 'Invalid event_type.'}), 400
            update_fields.append("event_type = %s")
            params.append(event_type)
        
        # Datetime parse
        start_date_val = None
        end_date_val = None
        if start_date_str or end_date_str:
            s_str = start_date_str if start_date_str else event['start_date'].strftime('%Y-%m-%d %H:%M')
            e_str = end_date_str if end_date_str else event['end_date'].strftime('%Y-%m-%d %H:%M')
            try:
                start_date_val = datetime.strptime(s_str.replace('T', ' '), '%Y-%m-%d %H:%M:%S' if len(s_str) > 16 else '%Y-%m-%d %H:%M')
                end_date_val = datetime.strptime(e_str.replace('T', ' '), '%Y-%m-%d %H:%M:%S' if len(e_str) > 16 else '%Y-%m-%d %H:%M')
                if end_date_val < start_date_val:
                    return jsonify({'message': 'end_date cannot be earlier than start_date.'}), 400
            except ValueError:
                return jsonify({'message': 'Invalid datetime format.'}), 400
            
            if start_date_str:
                update_fields.append("start_date = %s")
                params.append(start_date_val)
            if end_date_str:
                update_fields.append("end_date = %s")
                params.append(end_date_val)

        if target_role is not None:
            if target_role and target_role not in ('student', 'faculty', 'admin', 'all'):
                return jsonify({'message': 'Invalid target_role.'}), 400
            update_fields.append("target_role = %s")
            params.append(target_role or None)

        if target_class_id is not None:
            # Enforce hierarchy scoping
            if current_user['role'] == 'faculty' and target_class_id:
                if not check_teacher_hierarchy(cur, current_user['user_id'], target_class_id):
                    return jsonify({'message': 'Unauthorized class scope.'}), 403
            update_fields.append("target_class_id = %s")
            params.append(int(target_class_id) if target_class_id else None)

        if document_id is not None:
            update_fields.append("document_id = %s")
            params.append(int(document_id) if document_id else None)

        if event_color is not None:
            update_fields.append("event_color = %s")
            params.append(event_color.strip() or 'indigo')

        if recurrence_pattern is not None:
            if recurrence_pattern not in ('none', 'daily', 'weekly', 'monthly', 'yearly'):
                return jsonify({'message': 'Invalid recurrence pattern.'}), 400
            update_fields.append("recurrence_pattern = %s")
            params.append(recurrence_pattern)

        # Handle status transitions and audits
        notify_publish = False
        if status:
            if status not in ('draft', 'published', 'completed'):
                return jsonify({'message': 'Invalid status.'}), 400
            
            # If changing from draft to published, dispatch notifications
            if event['status'] == 'draft' and status == 'published':
                notify_publish = True
            
            update_fields.append("status = %s")
            params.append(status)

        if not update_fields:
            return jsonify({'message': 'No fields to update.'}), 400

        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(event_id)
        
        query = f"UPDATE AcademicEvents SET {', '.join(update_fields)} WHERE id = %s"
        cur.execute(query, tuple(params))

        # Query updated row for notifications
        cur.execute("SELECT * FROM AcademicEvents WHERE id = %s", (event_id,))
        updated_event = cur.fetchone()

        if notify_publish:
            notify_event_users(cur, inst_id, updated_event, 'New Event Published', 'published')
            log_activity(current_user['user_id'], 'EVENT_PUBLISHED', entity_type='academic_event', entity_id=event_id, cursor=cur)
        else:
            notify_event_users(cur, inst_id, updated_event, 'Event Updated', 'updated')
            log_activity(current_user['user_id'], 'EVENT_UPDATED', entity_type='academic_event', entity_id=event_id, cursor=cur)

        conn.commit()
        return jsonify({'message': 'Academic event updated successfully.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 3. SOFT-DELETE EVENT (CANCEL EVENT)
# ─────────────────────────────────────────────────────────────────────────────
@calendar_bp.route('/events/<int:event_id>', methods=['DELETE'])
@token_required(allowed_roles=['admin', 'faculty'])
def delete_event(current_user, event_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        event, err = verify_event_access(cur, current_user['user_id'], current_user['role'], event_id)
        if err:
            return jsonify({'message': err}), 403 if err != "Event not found" else 404

        # Soft delete logic: sets is_active = FALSE and status = 'cancelled'
        cur.execute("""
            UPDATE AcademicEvents 
            SET is_active = FALSE, status = 'cancelled', updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s
        """, (event_id,))

        # Notify relevant users of event cancellation
        notify_event_users(cur, inst_id, event, 'Event Cancelled', 'cancelled')

        log_activity(current_user['user_id'], 'EVENT_DELETED', entity_type='academic_event', entity_id=event_id, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Academic event successfully deleted.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 4. LIST EVENTS (ROLE SCOPED & FILTERED)
# ─────────────────────────────────────────────────────────────────────────────
@calendar_bp.route('/events', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def list_events(current_user):
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    event_type_filter = request.args.get('event_type')
    class_id_filter = request.args.get('class_id')
    status_filter = request.args.get('status')
    search_filter = request.args.get('search', '').strip()
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify([]), 200

        query = """
            SELECT e.*, d.original_filename as doc_filename, d.storage_path as doc_storage_path,
                   u.name as creator_name, c.section as class_section, dept.name as department_name, sem.number as semester_number
            FROM AcademicEvents e
            LEFT JOIN Documents d ON e.document_id = d.id
            LEFT JOIN Users u ON e.created_by = u.id
            LEFT JOIN Classes c ON e.target_class_id = c.id
            LEFT JOIN Departments dept ON c.department_id = dept.id
            LEFT JOIN Semesters sem ON c.semester_id = sem.id
            WHERE e.institution_id = %s AND e.is_active = TRUE
        """
        params = [inst_id]

        # 1. Role-based scoping
        if current_user['role'] == 'admin':
            # Admin sees all active events
            pass
        elif current_user['role'] == 'faculty':
            # Faculty sees public events, events they created, or classes they teach
            query += """
                AND (e.created_by = %s OR e.target_role IN ('faculty', 'all') OR (e.target_role IS NULL AND e.target_class_id IS NULL) OR e.target_class_id IN (
                    SELECT class_id FROM ClassAssignments WHERE teacher_id = %s
                    UNION
                    SELECT class_id FROM SubjectAssignments WHERE teacher_id = %s
                ))
            """
            params.extend([current_user['user_id'], current_user['user_id'], current_user['user_id']])
        elif current_user['role'] == 'student':
            # Student sees public/student scoped institutional events, or class-scoped events
            cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
            stu = cur.fetchone()
            stu_class = stu['class_id'] if stu else None
            
            if not stu_class:
                # Student not assigned to class yet, only sees general public ones
                query += " AND e.target_class_id IS NULL AND (e.target_role IN ('student', 'all') OR e.target_role IS NULL)"
            else:
                query += """
                    AND (
                        (e.target_class_id IS NULL AND (e.target_role IN ('student', 'all') OR e.target_role IS NULL))
                        OR e.target_class_id = %s
                    )
                """
                params.append(stu_class)
            
            # Students are strictly blocked from drafts
            query += " AND e.status != 'draft'"

        # 2. Filters
        if start_str and end_str:
            query += " AND e.start_date <= %s AND e.end_date >= %s"
            params.extend([end_str, start_str])
        elif start_str:
            query += " AND e.start_date >= %s"
            params.append(start_str)
        elif end_str:
            query += " AND e.end_date <= %s"
            params.append(end_str)

        if event_type_filter:
            query += " AND e.event_type = %s"
            params.append(event_type_filter)

        if class_id_filter:
            query += " AND e.target_class_id = %s"
            params.append(int(class_id_filter))

        if status_filter:
            query += " AND e.status = %s"
            params.append(status_filter)

        if search_filter:
            query += " AND (e.title ILIKE %s OR e.description ILIKE %s)"
            params.extend([f"%{search_filter}%", f"%{search_filter}%"])

        query += " ORDER BY e.start_date ASC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        result = []
        for r in rows:
            result.append({
                'id': r['id'],
                'title': r['title'],
                'description': r['description'],
                'event_type': r['event_type'],
                'start_date': r['start_date'].isoformat(),
                'end_date': r['end_date'].isoformat(),
                'target_role': r['target_role'],
                'target_class_id': r['target_class_id'],
                'class_section': r['class_section'],
                'department_name': r['department_name'],
                'semester_number': r['semester_number'],
                'created_by': r['created_by'],
                'creator_name': r['creator_name'],
                'status': r['status'],
                'document_id': r['document_id'],
                'doc_filename': r['doc_filename'],
                'doc_storage_path': r['doc_storage_path'],
                'event_color': r['event_color'],
                'recurrence_pattern': r['recurrence_pattern'],
                'is_active': r['is_active'],
                'created_at': r['created_at'].isoformat()
            })

        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': 'Error: ' + str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 5. UPCOMING EVENTS (DASHBOARD WIDGET ENDPOINT)
# ─────────────────────────────────────────────────────────────────────────────
@calendar_bp.route('/events/upcoming', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def upcoming_events(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify([]), 200

        query = """
            SELECT e.*, u.name as creator_name, c.section as class_section
            FROM AcademicEvents e
            LEFT JOIN Users u ON e.created_by = u.id
            LEFT JOIN Classes c ON e.target_class_id = c.id
            WHERE e.institution_id = %s AND e.is_active = TRUE AND e.end_date >= CURRENT_TIMESTAMP
        """
        params = [inst_id]

        # Role scoping
        if current_user['role'] == 'admin':
            pass
        elif current_user['role'] == 'faculty':
            query += """
                AND (e.created_by = %s OR e.target_role IN ('faculty', 'all') OR (e.target_role IS NULL AND e.target_class_id IS NULL) OR e.target_class_id IN (
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
                query += " AND e.target_class_id IS NULL AND (e.target_role IN ('student', 'all') OR e.target_role IS NULL)"
            else:
                query += """
                    AND (
                        (e.target_class_id IS NULL AND (e.target_role IN ('student', 'all') OR e.target_role IS NULL))
                        OR e.target_class_id = %s
                    )
                """
                params.append(stu_class)
            
            # Exclude drafts
            query += " AND e.status != 'draft'"

        query += " ORDER BY e.start_date ASC LIMIT 5"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        result = []
        for r in rows:
            result.append({
                'id': r['id'],
                'title': r['title'],
                'description': r['description'],
                'event_type': r['event_type'],
                'start_date': r['start_date'].isoformat(),
                'end_date': r['end_date'].isoformat(),
                'event_color': r['event_color'],
                'target_role': r['target_role'],
                'target_class_id': r['target_class_id'],
                'class_section': r['class_section'],
                'creator_name': r['creator_name'],
                'status': r['status']
            })

        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': 'Error: ' + str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 6. CALENDAR STATISTICS (DASHBOARD SUMMARIES)
# ─────────────────────────────────────────────────────────────────────────────
@calendar_bp.route('/stats', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def get_calendar_stats(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if not inst_id:
            return jsonify({}), 200

        # Query events using EXACT same scoping as listing to keep stats accurate
        query = """
            SELECT e.id, e.event_type, e.status, e.start_date, e.end_date
            FROM AcademicEvents e
            WHERE e.institution_id = %s AND e.is_active = TRUE
        """
        params = [inst_id]

        if current_user['role'] == 'admin':
            pass
        elif current_user['role'] == 'faculty':
            query += """
                AND (e.created_by = %s OR e.target_role IN ('faculty', 'all') OR (e.target_role IS NULL AND e.target_class_id IS NULL) OR e.target_class_id IN (
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
                query += " AND e.target_class_id IS NULL AND (e.target_role IN ('student', 'all') OR e.target_role IS NULL)"
            else:
                query += """
                    AND (
                        (e.target_class_id IS NULL AND (e.target_role IN ('student', 'all') OR e.target_role IS NULL))
                        OR e.target_class_id = %s
                    )
                """
                params.append(stu_class)
            query += " AND e.status != 'draft'"

        cur.execute(query, tuple(params))
        events = cur.fetchall()

        now = datetime.now()
        upcoming_count = 0
        holiday_count = 0
        exam_count = 0
        draft_count = 0
        published_count = 0
        completed_count = 0

        for ev in events:
            # End date >= now determines upcoming
            if ev['end_date'] >= now:
                upcoming_count += 1
            
            if ev['event_type'] == 'holiday':
                holiday_count += 1
            elif ev['event_type'] in ('internal_exam', 'university_exam', 'lab_exam'):
                exam_count += 1

            if ev['status'] == 'draft':
                draft_count += 1
            elif ev['status'] == 'published':
                published_count += 1
            elif ev['status'] == 'completed':
                completed_count += 1

        result = {
            'total_visible': len(events),
            'upcoming_events': upcoming_count,
            'holidays': holiday_count,
            'exams': exam_count,
            'drafts': draft_count,
            'published': published_count,
            'completed': completed_count
        }

        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()
