import sys
import os
import io
import json

# Adjust path to import db and other modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection
from import_routes import parse_file, detect_column_mappings, match_student

def test_engine():
    print("==================================================")
    print("EduNexus Academic Data Processing Engine Tests")
    print("==================================================")
    
    # 1. Test parsing CSV
    print("1. Testing file parser...")
    csv_data = "Register_No,Student_Name,CIA1,CIA2,Attendance_Status\n22CS101,John Mathew,18,19,P\n22CS102,Emma Watson,15,16,AB"
    headers, records = parse_file(csv_data.encode('utf-8'), "test.csv")
    
    assert headers == ["Register_No", "Student_Name", "CIA1", "CIA2", "Attendance_Status"], "Header mismatch"
    assert len(records) == 2, "Record count mismatch"
    assert records[0]["Register_No"] == "22CS101", "Register number parse mismatch"
    print("   [OK] File parser working correctly.")
    
    # 2. Test AI header matching
    print("2. Testing AI column matching...")
    mapping, confidence, import_type = detect_column_mappings(headers, "combined")
    assert mapping["register_number"] == "Register_No", "AI match register_number failed"
    assert mapping["cia1"] == "CIA1", "AI match marks failed"
    assert mapping["attendance_status"] == "Attendance_Status", "AI match status failed"
    assert import_type == "combined", "AI match import type failed"
    print(f"   [OK] Column matching confidence: {confidence * 100}%")
    
    # 3. Test matching students
    print("3. Testing database integration and matching...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Let's seed a temporary student if none exist
    cur.execute("SELECT id FROM Users WHERE email = 'test_student_import@edunexus.edu'")
    s_user = cur.fetchone()
    if not s_user:
        # Create student user
        cur.execute("""
            INSERT INTO Users (name, email, password, role)
            VALUES ('Import Test Student', 'test_student_import@edunexus.edu', 'dummy', 'student')
            RETURNING id
        """)
        s_id = cur.fetchone()['id']
        cur.execute("""
            INSERT INTO Students (user_id, register_number)
            VALUES (%s, 'IMPORT_TEST_001')
        """, (s_id,))
    else:
        s_id = s_user['id']
        
    # Match student test
    row = {'register_number': 'IMPORT_TEST_001', 'student_name': 'Import Test Student'}
    matched_id, score, match_by = match_student(cur, row)
    
    assert matched_id == s_id, "Student matching user_id mismatch"
    assert score == 1.0, "Register number confidence score should be 1.0"
    print(f"   [OK] Matched student using: {match_by} (Confidence: {score * 100}%)")
    
    # Clean up test student
    cur.execute("DELETE FROM Students WHERE register_number = 'IMPORT_TEST_001'")
    cur.execute("DELETE FROM Users WHERE email = 'test_student_import@edunexus.edu'")
    
    conn.commit()
    conn.close()
    
    print("\n[SUCCESS] All core import engine unit tests passed successfully!")

if __name__ == '__main__':
    test_engine()
