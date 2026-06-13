"""
EduNexus — Notifications System
Routes: GET /api/notifications
        POST /api/notifications/read
        POST /api/notifications/read-all
        DELETE /api/notifications/<id>

Utility: create_notification(cur, user_id, title, message, notif_type)
         notify_class_students(cur, class_id, title, message, notif_type)
"""

from flask import Blueprint, request, jsonify
from db import get_db_connection
from auth_middleware import token_required

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')

# ─────────────────────────────────────────────────────────────────────────────
# Shared utility functions (used by other route modules)
# ─────────────────────────────────────────────────────────────────────────────

def create_notification(cur, user_id, title, message, notif_type='system'):
    """
    Insert a single notification row.
    MUST be called within an existing transaction — caller handles commit.
    notif_type: 'marks' | 'attendance' | 'survey' | 'system' | 'promotion' | 'assignment'
    """
    cur.execute("""
        INSERT INTO Notifications (user_id, title, message, type)
        VALUES (%s, %s, %s, %s)
    """, (user_id, title[:120], message[:500], notif_type))


def notify_class_students(cur, class_id, title, message, notif_type='system'):
    """
    Create one notification for every student enrolled in class_id.
    Caller handles commit.
    """
    cur.execute("""
        SELECT user_id FROM Students WHERE class_id = %s
    """, (class_id,))
    students = cur.fetchall()
    for s in students:
        create_notification(cur, s['user_id'], title, message, notif_type)
    return len(students)


def notify_class_faculty(cur, class_id, title, message, notif_type='assignment'):
    """
    Create one notification for every faculty assigned to class_id (any role).
    Caller handles commit.
    """
    cur.execute("""
        SELECT DISTINCT teacher_id AS user_id
        FROM ClassAssignments WHERE class_id = %s
        UNION
        SELECT DISTINCT sa.teacher_id AS user_id
        FROM SubjectAssignments sa
        JOIN Subjects sub ON sa.subject_id = sub.id
        WHERE sub.class_id = %s
    """, (class_id, class_id))
    faculty = cur.fetchall()
    for f in faculty:
        create_notification(cur, f['user_id'], title, message, notif_type)
    return len(faculty)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/notifications  — latest 50 for logged-in user
# ─────────────────────────────────────────────────────────────────────────────

@notifications_bp.route('', methods=['GET'])
@token_required(allowed_roles=['faculty', 'student', 'admin'])
def get_notifications(current_user):
    limit  = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            SELECT id, title, message, type, is_read, created_at
            FROM Notifications
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (current_user['user_id'], limit, offset))
        rows = cur.fetchall()

        # Unread count (all, not just current page)
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM Notifications
            WHERE user_id = %s AND is_read = FALSE
        """, (current_user['user_id'],))
        unread_count = cur.fetchone()['cnt']

        result = []
        for r in rows:
            result.append({
                'id':         r['id'],
                'title':      r['title'],
                'message':    r['message'],
                'type':       r['type'],
                'is_read':    r['is_read'],
                'created_at': r['created_at'].isoformat() if r['created_at'] else None
            })

        return jsonify({
            'notifications': result,
            'unread_count':  unread_count
        }), 200
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/notifications/read  — mark one as read
# ─────────────────────────────────────────────────────────────────────────────

@notifications_bp.route('/read', methods=['POST'])
@token_required(allowed_roles=['faculty', 'student', 'admin'])
def mark_read(current_user):
    data   = request.json or {}
    nid    = data.get('notification_id')
    if not nid:
        return jsonify({'message': 'notification_id required'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            UPDATE Notifications SET is_read = TRUE
            WHERE id = %s AND user_id = %s
        """, (nid, current_user['user_id']))
        conn.commit()
        return jsonify({'message': 'Marked as read'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/notifications/read-all  — mark all unread as read
# ─────────────────────────────────────────────────────────────────────────────

@notifications_bp.route('/read-all', methods=['POST'])
@token_required(allowed_roles=['faculty', 'student', 'admin'])
def mark_all_read(current_user):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            UPDATE Notifications SET is_read = TRUE
            WHERE user_id = %s AND is_read = FALSE
        """, (current_user['user_id'],))
        conn.commit()
        return jsonify({'message': 'All notifications marked as read'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/notifications/<id>  — delete one notification
# ─────────────────────────────────────────────────────────────────────────────

@notifications_bp.route('/<int:nid>', methods=['DELETE'])
@token_required(allowed_roles=['faculty', 'student', 'admin'])
def delete_notification(current_user, nid):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            DELETE FROM Notifications WHERE id = %s AND user_id = %s
        """, (nid, current_user['user_id']))
        conn.commit()
        return jsonify({'message': 'Notification deleted'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()
