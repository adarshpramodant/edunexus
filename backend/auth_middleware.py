from functools import wraps
from flask import request, jsonify
import jwt
import os

SECRET_KEY = os.environ.get("JWT_SECRET", "super-secret-default-key-please-change")

def token_required(allowed_roles=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = None
            if 'Authorization' in request.headers:
                # Format: "Bearer <token>"
                parts = request.headers['Authorization'].split()
                if len(parts) == 2 and parts[0] == 'Bearer':
                    token = parts[1]
            
            if not token:
                return jsonify({'message': 'Token is missing!'}), 401

            try:
                data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
                current_user = data
                
                if allowed_roles and current_user['role'] not in allowed_roles:
                    return jsonify({'message': 'Unauthorized access!'}), 403
                    
            except Exception as e:
                return jsonify({'message': 'Token is invalid!', 'error': str(e)}), 401

            return f(current_user, *args, **kwargs)
        return decorated
    return decorator
