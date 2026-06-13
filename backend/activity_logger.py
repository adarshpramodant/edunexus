import json
import sys
import os
from flask import has_request_context, request

# Adjust path to import db
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection

def log_activity(user_id, action, entity_type=None, entity_id=None, old_data=None, new_data=None, institution_id=None, ip_address=None, cursor=None):
    """
    Transaction-safe enterprise activity logger.
    
    :param user_id: ID of the user performing the action (actor).
    :param action: Action name (e.g. LOGIN_SUCCESS, STUDENT_TRANSFERRED).
    :param entity_type: The table or resource type (e.g. student, subject, class).
    :param entity_id: ID of the affected resource.
    :param old_data: Dictionary or list containing original data.
    :param new_data: Dictionary or list containing updated/created data.
    :param institution_id: Explicit institution ID (will auto-resolve from user if None).
    :param ip_address: Explicit client IP (will auto-resolve from headers/request context if None).
    :param cursor: Optional active transaction cursor. If provided, writes within that transaction.
    """
    # Extract IP address from request context if not provided
    if not ip_address and has_request_context():
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address and ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()

    # Resolve institution_id if not provided but user_id is
    resolved_inst_id = institution_id
    if not resolved_inst_id and user_id:
        if cursor:
            cursor.execute("SELECT institution_id FROM Users WHERE id = %s", (user_id,))
            res = cursor.fetchone()
            if res:
                resolved_inst_id = res['institution_id']
        else:
            try:
                conn = get_db_connection()
                with conn.cursor() as temp_cur:
                    temp_cur.execute("SELECT institution_id FROM Users WHERE id = %s", (user_id,))
                    res = temp_cur.fetchone()
                    if res:
                        resolved_inst_id = res['institution_id']
                conn.close()
            except Exception:
                pass

    old_data_json = json.dumps(old_data) if old_data is not None else None
    new_data_json = json.dumps(new_data) if new_data is not None else None

    # Internal insert executor
    def insert_log(cur):
        cur.execute("""
            INSERT INTO ActivityLogs (institution_id, user_id, action, entity_type, entity_id, old_data, new_data, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (resolved_inst_id, user_id, action, entity_type, str(entity_id) if entity_id is not None else None, old_data_json, new_data_json, ip_address))
        res = cur.fetchone()
        return res['id'] if res else None

    if cursor:
        try:
            return insert_log(cursor)
        except Exception as e:
            # Under cursor/transaction, let the exception propagate so transaction is rolled back
            with open("debug_error.log", "a", encoding="utf-8") as f:
                f.write(f"log_activity error (within active cursor): {str(e)}\n")
            raise e
    else:
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                log_id = insert_log(cur)
                conn.commit()
            return log_id
        except Exception as e:
            if conn:
                conn.rollback()
            with open("debug_error.log", "a", encoding="utf-8") as f:
                f.write(f"log_activity error (independent): {str(e)}\n")
            # Do NOT re-raise to ensure logging doesn't block critical path (e.g. login) if DB has issues
            return None
        finally:
            if conn:
                conn.close()
