const API_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:'
    ? 'http://localhost:5000/api/auth'
    : 'https://edunexus-quw3.onrender.com/api/auth';

function toggleAdminFields() {
    const roleSelect = document.getElementById('role');
    const adminFields = document.getElementById('admin-fields');
    const institutionInput = document.getElementById('institutionName');
    
    if (roleSelect && adminFields) {
        if (roleSelect.value === 'admin') {
            adminFields.style.display = 'block';
            institutionInput.required = true;
        } else {
            adminFields.style.display = 'none';
            institutionInput.required = false;
        }
    }
}

// Ensure the right fields are shown on load if there's a cached value
document.addEventListener('DOMContentLoaded', toggleAdminFields);

const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const errorDiv = document.getElementById('loginError');
        const btn = document.getElementById('loginBtn');
        
        try {
            btn.disabled = true;
            btn.textContent = 'Signing in...';
            errorDiv.style.display = 'none';
            
            const response = await fetch(`${API_URL}/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email, password })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || 'Login failed');
            }
            
            localStorage.setItem('token', data.token);
            localStorage.setItem('role', data.role);
            localStorage.setItem('institution_id', data.institution_id);
            
            redirectBasedOnRole(data.role);
            
        } catch (error) {
            errorDiv.textContent = error.message;
            errorDiv.style.display = 'block';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Sign in';
        }
    });
}

const signupForm = document.getElementById('signupForm');
if (signupForm) {
    signupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('name').value;
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const role = document.getElementById('role').value;
        const institutionName = document.getElementById('institutionName').value;
        
        const errorDiv = document.getElementById('signupError');
        const btn = document.getElementById('signupBtn');
        
        try {
            btn.disabled = true;
            btn.textContent = 'Creating account...';
            errorDiv.style.display = 'none';
            
            const payload = { name, email, password, role };
            if (role === 'admin') {
                payload.institution_name = institutionName;
            }
            
            const response = await fetch(`${API_URL}/signup`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || 'Signup failed');
            }
            
            localStorage.setItem('token', data.token);
            localStorage.setItem('role', data.role);
            
            redirectBasedOnRole(data.role);
            
        } catch (error) {
            errorDiv.textContent = error.message;
            errorDiv.style.display = 'block';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Create Account';
        }
    });
}

function redirectBasedOnRole(role) {
    if (role === 'student') {
        window.location.href = 'student_dashboard.html';
    } else if (role === 'faculty') {
        window.location.href = 'faculty_dashboard.html';
    } else if (role === 'admin') {
        window.location.href = 'admin_dashboard.html';
    } else {
        window.location.href = 'index.html';
    }
}
