from flask import Blueprint, request, jsonify
from db import get_db_connection
from auth_middleware import token_required
from admin_routes import get_admin_institution

activity_log_bp = Blueprint('activity_logs', __name__, url_prefix='/api/activity-logs')

@activity_log_bp.route('', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty'])
def get_activity_logs(current_user):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT l.id, l.institution_id, l.user_id, l.action, l.entity_type, l.entity_id, 
                   l.old_data, l.new_data, l.ip_address, l.created_at,
                   u.name as user_name, u.email as user_email
            FROM ActivityLogs l
            LEFT JOIN Users u ON l.user_id = u.id
            WHERE 1=1
        """
        params = []

        # 1. Scoping by Role
        if current_user['role'] == 'admin':
            inst_id = get_admin_institution(current_user['user_id'])
            if inst_id is not None:
                query += " AND l.institution_id = %s"
                params.append(inst_id)
            
            # Admins can filter by specific user
            filter_user_id = request.args.get('user_id')
            if filter_user_id:
                query += " AND l.user_id = %s"
                params.append(int(filter_user_id))
        elif current_user['role'] == 'faculty':
            query += " AND l.user_id = %s"
            params.append(current_user['user_id'])

        # 2. General Filters
        action = request.args.get('action')
        if action:
            query += " AND l.action = %s"
            params.append(action)

        start_date = request.args.get('start_date')
        if start_date:
            query += " AND l.created_at >= %s"
            params.append(start_date + " 00:00:00")

        end_date = request.args.get('end_date')
        if end_date:
            query += " AND l.created_at <= %s"
            params.append(end_date + " 23:59:59")

        entity_type = request.args.get('entity_type')
        if entity_type:
            query += " AND l.entity_type = %s"
            params.append(entity_type)

        entity_id = request.args.get('entity_id')
        if entity_id:
            query += " AND l.entity_id = %s"
            params.append(str(entity_id))

        # 3. Pagination
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        query += " ORDER BY l.created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, tuple(params))
        logs = cur.fetchall()

        # Format datetime fields
        for log in logs:
            if log['created_at']:
                log['created_at'] = log['created_at'].isoformat()

        return jsonify(logs), 200
    except Exception as e:
        return jsonify({'message': 'Error retrieving activity logs: ' + str(e)}), 500
    finally:
        conn.close()
