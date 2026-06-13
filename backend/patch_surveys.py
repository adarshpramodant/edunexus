from db import get_db_connection

conn = get_db_connection()
cur  = conn.cursor()

patches = [
    # Add description column if missing
    "ALTER TABLE Surveys ADD COLUMN IF NOT EXISTS description TEXT;",
    # Ensure UNIQUE constraint on SurveyResponses (survey_id, student_id) already exists per schema
]

for sql in patches:
    try:
        cur.execute(sql)
        print("OK:", sql[:60])
    except Exception as e:
        print("SKIP:", e)

conn.commit()
conn.close()
print("Schema patched.")
