from flask import Flask, request, jsonify
from flask_cors import CORS
from db import get_db_connection
from admin_routes import admin_bp
from faculty_routes import faculty_bp
from student_routes import student_bp
from survey_routes import survey_bp
from notification_routes import notifications_bp
from report_routes import report_bp
from activity_log_routes import activity_log_bp
from activity_logger import log_activity
from document_routes import document_bp
from assignment_routes import assignments_bp
from calendar_routes import calendar_bp
from analytics_routes import analytics_bp
import bcrypt
import jwt
import datetime
import os
import re

app = Flask(__name__)
# Enable CORS for all routes so the frontend can easily communicate
CORS(app)

app.register_blueprint(admin_bp)
app.register_blueprint(faculty_bp)
app.register_blueprint(student_bp)
app.register_blueprint(survey_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(report_bp)
app.register_blueprint(activity_log_bp)
app.register_blueprint(document_bp)
app.register_blueprint(assignments_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(analytics_bp)

SECRET_KEY = os.environ.get("JWT_SECRET", "super-secret-default-key-please-change")

def create_token(user_id, role):
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')
    
    if not all([name, email, password, role]):
        return jsonify({'message': 'Missing required fields'}), 400
        
    if role not in ['student', 'faculty', 'admin']:
        return jsonify({'message': 'Invalid role'}), 400
        
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({'message': 'Invalid email format'}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if email exists
        cur.execute("SELECT id FROM Users WHERE email = %s", (email,))
        if cur.fetchone():
            return jsonify({'message': 'Email already registered'}), 409
            
        if role == 'admin':
            institution_name = data.get('institution_name')
            if not institution_name:
                return jsonify({'message': 'Institution name required for admin signup'}), 400
                
            # Create institution
            cur.execute("INSERT INTO Institutions (name) VALUES (%s) RETURNING id", (institution_name,))
            inst_id = cur.fetchone()['id']
            
            # Create user
            cur.execute("""
                INSERT INTO Users (name, email, password, role, institution_id)
                VALUES (%s, %s, %s, %s, %s) RETURNING id, role
            """, (name, email, hashed_password, role, inst_id))
            
            new_user = cur.fetchone()
        else:
            # Student or Faculty signup
            # institution_id is null, admin needs to add them later
            cur.execute("""
                INSERT INTO Users (name, email, password, role)
                VALUES (%s, %s, %s, %s) RETURNING id, role
            """, (name, email, hashed_password, role))
            
            new_user = cur.fetchone()
            
        conn.close()
        
        token = create_token(new_user['id'], new_user['role'])
        return jsonify({
            'message': 'Signup successful',
            'token': token,
            'role': new_user['role']
        }), 201
        
    except ValueError as val_e:
        return jsonify({'message': str(val_e)}), 500
    except Exception as e:
        return jsonify({'message': 'Database error: ' + str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not all([email, password]):
        return jsonify({'message': 'Missing email or password'}), 400
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM Users WHERE email = %s", (email,))
        user = cur.fetchone()
        conn.close()
        
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            log_activity(None, 'LOGIN_FAILED', entity_type='user', entity_id=None, new_data={'email': email})
            return jsonify({'message': 'Invalid credentials'}), 401
            
        token = create_token(user['id'], user['role'])
        
        log_activity(user['id'], 'LOGIN_SUCCESS', entity_type='user', entity_id=user['id'], institution_id=user['institution_id'])
        
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'role': user['role'],
            'institution_id': user['institution_id']
        }), 200

    except ValueError as val_e:
        return jsonify({'message': str(val_e)}), 500
    except Exception as e:
        return jsonify({'message': 'Database error: ' + str(e)}), 500

if __name__ == '__main__':
   port = int(os.environ.get("PORT", 5000))
   app.run(host='0.0.0.0', port=port)
