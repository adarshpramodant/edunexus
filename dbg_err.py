import requests
import json

BASE = "http://localhost:5000/api"

# Login as admin to get token
r_admin = requests.post(f"{BASE}/auth/login", json={"email": "admin_1713414000@test.com", "password": "Admin@123"})
# wait we don't know the exact email because of timestamp
