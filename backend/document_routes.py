import os
import sys
import time
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename

# Adjust path to import other modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection
from auth_middleware import token_required
from storage_service import get_storage_service
from activity_logger import log_activity
from notification_routes import create_notification, notify_class_students, notify_class_faculty

document_bp = Blueprint('documents', __name__, url_prefix='/api/documents')

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB Upload Limit

ALLOWED_EXTENSIONS = {
    'pdf', 'docx', 'xlsx', 'pptx', 'txt', 'csv', 'rtf',
    'jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'zip', 'rar'
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user_institution(cur, user_id):
    cur.execute("SELECT institution_id FROM Users WHERE id = %s", (user_id,))
    res = cur.fetchone()
    return res['institution_id'] if res else None

# ─────────────────────────────────────────────────────────────────────────────
# 1. UPLOAD DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────
@document_bp.route('', methods=['POST'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def upload_document(current_user):
    # Enforce 50MB file size check from Content-Length header
    if request.content_length and request.content_length > MAX_UPLOAD_SIZE:
        return jsonify({'message': 'File size exceeds the 50MB limit.'}), 413

    if 'file' not in request.files:
        return jsonify({'message': 'No file part in request.'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No file selected.'}), 400

    if not allowed_file(file.filename):
        return jsonify({'message': f'File extension not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip()  # 'notes', 'assignment', 'circular', etc.
    visibility = request.form.get('visibility', 'public').strip()  # 'public', 'role', 'class'
    target_role = request.form.get('target_role')
    target_class_id = request.form.get('target_class_id')

    if not title or not category or not visibility:
        return jsonify({'message': 'title, category, and visibility are required fields.'}), 400

    if visibility == 'role' and not target_role:
        return jsonify({'message': 'target_role is required for role-scoped visibility.'}), 400

    if visibility == 'class' and not target_class_id:
        return jsonify({'message': 'target_class_id is required for class-scoped visibility.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if inst_id is None:
            return jsonify({'message': 'User is not linked to any institution.'}), 403

        # Read file contents and compute metadata
        file_data = file.read()
        file_size = len(file_data)
        if file_size > MAX_UPLOAD_SIZE:
            return jsonify({'message': 'File size exceeds the 50MB limit.'}), 413

        orig_filename = file.filename
        safe_name = secure_filename(orig_filename)
        mime_type = file.content_type or 'application/octet-stream'

        # Structure path to avoid collision: institution_<id>/user_<id>/<timestamp>_<filename>
        timestamp = int(time.time())
        storage_path = f"institution_{inst_id}/user_{current_user['user_id']}/{timestamp}_{safe_name}"

        # Upload file using active Storage Service (handles dynamic testing mocks)
        storage_service = get_storage_service()
        uploaded_path = storage_service.upload_file('documents', storage_path, file_data, mime_type)

        # Class ID parsing
        class_val = int(target_class_id) if target_class_id and visibility == 'class' else None

        # Insert to database
        cur.execute("""
            INSERT INTO Documents (institution_id, uploaded_by, title, description, original_filename, 
                                   storage_path, mime_type, file_size, category, visibility, 
                                   target_role, target_class_id, version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            RETURNING id
        """, (inst_id, current_user['user_id'], title, description or None, orig_filename,
              uploaded_path, mime_type, file_size, category, visibility,
              target_role if visibility == 'role' else None, class_val))
        
        doc_id = cur.fetchone()['id']

        # Notify targeted users
        if visibility == 'class' and class_val:
            # Notify enrolled students
            notify_class_students(cur, class_val, 'New Class Document Uploaded', f'New {category} uploaded: "{title}"', 'assignment')
        elif visibility == 'public':
            # Notify everyone in the institution (except the uploader)
            cur.execute("SELECT id FROM Users WHERE institution_id = %s", (inst_id,))
            all_users = cur.fetchall()
            for u in all_users:
                if u['id'] != current_user['user_id']:
                    create_notification(cur, u['id'], 'New Notice/Circular Published', f'A new circular/notice was published: "{title}"', 'system')

        # Log Activity Audit Trail
        log_activity(current_user['user_id'], 'DOCUMENT_UPLOADED', entity_type='document', entity_id=doc_id, 
                     new_data={'title': title, 'category': category, 'visibility': visibility}, cursor=cur)

        conn.commit()
        return jsonify({
            'message': 'Document uploaded successfully.',
            'document_id': doc_id,
            'storage_path': uploaded_path
        }), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'message': 'Upload failed: ' + str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 2. LIST DOCUMENTS (WITH ROLE-BASED VISIBILITY SCOPING & FILTERING)
# ─────────────────────────────────────────────────────────────────────────────
@document_bp.route('', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def list_documents(current_user):
    category = request.args.get('category')
    search = request.args.get('search')
    is_archived = request.args.get('is_archived', 'false').lower() == 'true'
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        inst_id = get_user_institution(cur, current_user['user_id'])
        if inst_id is None:
            return jsonify([]), 200

        # Base SELECT query mapping
        query = """
            SELECT d.id, d.uploaded_by, d.title, d.description, d.original_filename, 
                   d.storage_path, d.mime_type, d.file_size, d.category, d.visibility, 
                   d.target_role, d.target_class_id, d.version, d.is_archived, d.created_at,
                   u.name as uploader_name
            FROM Documents d
            JOIN Users u ON d.uploaded_by = u.id
            WHERE d.institution_id = %s AND d.is_deleted = FALSE
        """
        params = [inst_id]

        # Role-based visibility filters
        if current_user['role'] == 'admin':
            # Admins see all documents (active or archived)
            if not is_archived:
                query += " AND d.is_archived = FALSE"
            else:
                query += " AND d.is_archived = TRUE"
        
        elif current_user['role'] == 'faculty':
            # Faculty see:
            # - Owned uploads
            # - Public documents
            # - Role-scoped (targeting 'faculty')
            # - Class-scoped where they have a class or subject assignment
            cur.execute("""
                SELECT DISTINCT class_id FROM ClassAssignments WHERE teacher_id = %s
                UNION
                SELECT DISTINCT sa.class_id FROM SubjectAssignments sa WHERE sa.teacher_id = %s
            """, (current_user['user_id'], current_user['user_id']))
            assigned_classes = [r['class_id'] for r in cur.fetchall()]

            class_clause = ""
            clause_params = [current_user['user_id']]
            if assigned_classes:
                class_clause = "OR (d.visibility = 'class' AND d.target_class_id IN %s)"
                clause_params.append(tuple(assigned_classes))

            query += f"""
                AND (
                    d.uploaded_by = %s
                    OR d.visibility = 'public'
                    OR (d.visibility = 'role' AND d.target_role = 'faculty')
                    {class_clause}
                )
            """
            params.extend(clause_params)
            query += " AND d.is_archived = %s"
            params.append(is_archived)

        elif current_user['role'] == 'student':
            # Students see:
            # - Owned uploads (e.g. assignment submissions)
            # - Public documents (e.g. notices)
            # - Role-scoped (targeting 'student')
            # - Class-scoped matching their class_id
            cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
            student_class_res = cur.fetchone()
            student_class_id = student_class_res['class_id'] if student_class_res else None

            class_clause = ""
            if student_class_id is not None:
                class_clause = f"OR (d.visibility = 'class' AND d.target_class_id = {student_class_id})"

            query += f"""
                AND (
                    d.uploaded_by = %s
                    OR d.visibility = 'public'
                    OR (d.visibility = 'role' AND d.target_role = 'student')
                    {class_clause}
                )
            """
            params.append(current_user['user_id'])
            # Students never see archived files
            query += " AND d.is_archived = FALSE"

        # Apply common filters
        if category:
            query += " AND d.category = %s"
            params.append(category)

        if search:
            query += " AND (d.title ILIKE %s OR d.description ILIKE %s)"
            params.append(f"%{search}%")
            params.append(f"%{search}%")

        # Sorting and Pagination
        query += " ORDER BY d.created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        result = []
        for r in rows:
            result.append({
                'id': r['id'],
                'uploaded_by': r['uploaded_by'],
                'uploader_name': r['uploader_name'],
                'title': r['title'],
                'description': r['description'],
                'original_filename': r['original_filename'],
                'storage_path': r['storage_path'],
                'mime_type': r['mime_type'],
                'file_size': r['file_size'],
                'category': r['category'],
                'visibility': r['visibility'],
                'target_role': r['target_role'],
                'target_class_id': r['target_class_id'],
                'version': r['version'],
                'is_archived': r['is_archived'],
                'created_at': r['created_at'].isoformat() if r['created_at'] else None
            })

        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': 'Error: ' + str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 3. GET DYNAMIC SECURE DOWNLOAD URL (WITH DOWNLOAD ACCESS CHECKING)
# ─────────────────────────────────────────────────────────────────────────────
@document_bp.route('/<int:doc_id>/download', methods=['GET'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def get_download_url(current_user, doc_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM Documents WHERE id = %s AND is_deleted = FALSE", (doc_id,))
        doc = cur.fetchone()
        if not doc:
            return jsonify({'message': 'Document not found or soft-deleted.'}), 404

        # Access check
        allowed = False
        if current_user['role'] == 'admin':
            allowed = (doc['institution_id'] == get_user_institution(cur, current_user['user_id']))
        else:
            if doc['uploaded_by'] == current_user['user_id']:
                allowed = True
            elif doc['visibility'] == 'public':
                allowed = (doc['institution_id'] == get_user_institution(cur, current_user['user_id']))
            elif doc['visibility'] == 'role':
                allowed = (doc['target_role'] == current_user['role'])
            elif doc['visibility'] == 'class' and doc['target_class_id']:
                if current_user['role'] == 'student':
                    cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
                    res = cur.fetchone()
                    allowed = (res and res['class_id'] == doc['target_class_id'])
                elif current_user['role'] == 'faculty':
                    cur.execute("""
                        SELECT 1 FROM ClassAssignments WHERE teacher_id = %s AND class_id = %s
                        UNION
                        SELECT 1 FROM SubjectAssignments WHERE teacher_id = %s AND class_id = %s
                    """, (current_user['user_id'], doc['target_class_id'], current_user['user_id'], doc['target_class_id']))
                    allowed = bool(cur.fetchone())

        if not allowed:
            return jsonify({'message': 'Unauthorized to view or download this document.'}), 403

        # Dynamically generate secure signed URL (expiring in 60s)
        storage_service = get_storage_service()
        signed_url = storage_service.get_signed_url('documents', doc['storage_path'], expires_in=60)

        # Log download activity
        log_activity(current_user['user_id'], 'DOCUMENT_DOWNLOADED', entity_type='document', entity_id=doc_id,
                     new_data={'title': doc['title']}, cursor=cur)
        
        conn.commit()
        return jsonify({'download_url': signed_url}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': 'Error generating download: ' + str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 4. TOGGLE ARCHIVE DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────
@document_bp.route('/<int:doc_id>/archive', methods=['PUT'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def toggle_archive(current_user, doc_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM Documents WHERE id = %s AND is_deleted = FALSE", (doc_id,))
        doc = cur.fetchone()
        if not doc:
            return jsonify({'message': 'Document not found.'}), 404

        # Verify role permission: must be Admin or the uploader
        if current_user['role'] != 'admin' and doc['uploaded_by'] != current_user['user_id']:
            return jsonify({'message': 'Unauthorized. Only uploader or Admin can archive.'}), 403

        new_archive_state = not doc['is_archived']
        cur.execute("UPDATE Documents SET is_archived = %s WHERE id = %s", (new_archive_state, doc_id))

        action_name = 'DOCUMENT_ARCHIVED' if new_archive_state else 'DOCUMENT_UNARCHIVED'
        log_activity(current_user['user_id'], action_name, entity_type='document', entity_id=doc_id, cursor=cur)

        conn.commit()
        return jsonify({'message': f'Document successfully {"archived" if new_archive_state else "unarchived"}.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 5. SOFT-DELETE DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────
@document_bp.route('/<int:doc_id>', methods=['DELETE'])
@token_required(allowed_roles=['admin', 'faculty', 'student'])
def soft_delete_document(current_user, doc_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM Documents WHERE id = %s AND is_deleted = FALSE", (doc_id,))
        doc = cur.fetchone()
        if not doc:
            return jsonify({'message': 'Document not found.'}), 404

        # Verify role permission: must be Admin or the uploader
        if current_user['role'] != 'admin' and doc['uploaded_by'] != current_user['user_id']:
            return jsonify({'message': 'Unauthorized. Only uploader or Admin can delete.'}), 403

        # Update soft delete columns
        cur.execute("""
            UPDATE Documents 
            SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP 
            WHERE id = %s
        """, (doc_id,))

        log_activity(current_user['user_id'], 'DOCUMENT_DELETED', entity_type='document', entity_id=doc_id, cursor=cur)

        conn.commit()
        return jsonify({'message': 'Document successfully soft-deleted.'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 6. LOCAL MOCK STORAGE STREAMING (UTILITIES ONLY FOR LOCAL TEST RUNS)
# ─────────────────────────────────────────────────────────────────────────────
@document_bp.route('/mock-download/<bucket>/<path:filepath>', methods=['GET'])
def serve_mock_download(bucket, filepath):
    mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock_storage', bucket)
    full_path = os.path.join(mock_dir, filepath.replace('/', os.sep))
    if os.path.exists(full_path):
        return send_file(full_path, as_attachment=True)
    return jsonify({'message': 'Mock file not found'}), 404
