from db import get_db_connection

conn = get_db_connection()
cur = conn.cursor()
try:
    cur.execute("ALTER TABLE Subjects ADD COLUMN class_id INTEGER REFERENCES Classes(id);")
    print("Added class_id to Subjects")
except Exception as e:
    print("class_id err:", e)
    
conn.commit()
conn.close()
