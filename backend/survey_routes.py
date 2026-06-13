from flask import Blueprint, request, jsonify
from db import get_db_connection
from auth_middleware import token_required
from activity_logger import log_activity

survey_bp = Blueprint('survey', __name__)

# ─── Role helpers ──────────────────────────────────────────────────────────────

ROLE_PRIORITY = {'class_teacher': 3, 'vice_class_teacher': 2, 'subject_teacher': 1}

def _is_class_lead(cur, class_id, user_id):
    """True if faculty is class_teacher or vice_class_teacher for this class."""
    cur.execute(
        "SELECT 1 FROM ClassAssignments "
        "WHERE class_id = %s AND teacher_id = %s "
        "AND role IN ('class_teacher', 'vice_class_teacher')",
        (class_id, user_id)
    )
    return bool(cur.fetchone())

def _faculty_assigned(cur, class_id, user_id):
    """True if faculty has ANY assignment (class or subject) for this class."""
    cur.execute("""
        SELECT 1 FROM ClassAssignments WHERE class_id = %s AND teacher_id = %s
        UNION
        SELECT 1 FROM SubjectAssignments WHERE class_id = %s AND teacher_id = %s
    """, (class_id, user_id, class_id, user_id))
    return bool(cur.fetchone())

# ═══════════════════════════════════════════════════════════════════════════════
# FACULTY ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. Create Survey (atomic: title + description + questions + options) ───────
@survey_bp.route('/api/faculty/surveys', methods=['POST'])
@token_required(allowed_roles=['faculty'])
def create_survey(current_user):
    data        = request.json or {}
    title       = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    class_id    = data.get('class_id')
    questions   = data.get('questions', [])   # list of question dicts

    # ── Validation ──
    if not title:
        return jsonify({'message': 'Survey title is required'}), 400
    if not class_id:
        return jsonify({'message': 'class_id is required'}), 400
    if not questions:
        return jsonify({'message': 'At least one question is required'}), 400

    for i, q in enumerate(questions, 1):
        if not (q.get('question_text') or '').strip():
            return jsonify({'message': f'Question {i}: text is required'}), 400
        qtype = (q.get('question_type') or q.get('type') or '').lower()
        if qtype not in ('mcq', 'text'):
            return jsonify({'message': f'Question {i}: type must be mcq or text'}), 400
        if qtype == 'mcq':
            opts = [o for o in q.get('options', []) if (o or '').strip()]
            if len(opts) < 2:
                return jsonify({'message': f'Question {i}: MCQ needs at least 2 options'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        # Auth: must be class_teacher or vice_class_teacher
        if not _is_class_lead(cur, class_id, current_user['user_id']):
            return jsonify({'message': 'Unauthorized: Only Class/Vice-Class Teachers can create surveys'}), 403

        # Insert survey
        cur.execute("""
            INSERT INTO Surveys (title, description, created_by, class_id)
            VALUES (%s, %s, %s, %s) RETURNING id, title, created_at
        """, (title, description or None, current_user['user_id'], class_id))
        survey = cur.fetchone()
        survey_id = survey['id']

        # Insert questions + options
        for q in questions:
            qtype = (q.get('question_type') or q.get('type') or '').lower()
            cur.execute("""
                INSERT INTO SurveyQuestions (survey_id, question_text, type)
                VALUES (%s, %s, %s) RETURNING id
            """, (survey_id, q['question_text'].strip(), qtype))
            q_id = cur.fetchone()['id']

            if qtype == 'mcq':
                for opt_text in q.get('options', []):
                    opt_text = (opt_text or '').strip()
                    if opt_text:
                        cur.execute("""
                            INSERT INTO QuestionOptions (question_id, option_text)
                            VALUES (%s, %s)
                        """, (q_id, opt_text))

        log_activity(current_user['user_id'], 'SURVEY_CREATED', entity_type='survey', entity_id=survey_id, new_data={'title': title, 'class_id': class_id}, cursor=cur)
        conn.commit()
        return jsonify({
            'message': 'Survey created successfully',
            'survey_id': survey_id,
            'title': survey['title']
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


# ── 2. Get Surveys created by this faculty (all classes) ──────────────────────
@survey_bp.route('/api/faculty/surveys', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_faculty_surveys(current_user):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            SELECT s.id, s.title, s.description, s.class_id,
                   CONCAT(d.name, ' | Sem ', sem.number, ' | Sec ', c.section) AS class_name,
                   s.created_at,
                   COUNT(DISTINCT sq.id)  AS question_count,
                   COUNT(DISTINCT sr.id)  AS response_count
            FROM Surveys s
            JOIN Classes c     ON s.class_id = c.id
            JOIN Departments d ON c.department_id = d.id
            JOIN Semesters sem ON c.semester_id = sem.id
            LEFT JOIN SurveyQuestions sq ON s.id = sq.survey_id
            LEFT JOIN SurveyResponses sr ON s.id = sr.survey_id
            WHERE s.created_by = %s
            GROUP BY s.id, s.title, s.description, s.class_id,
                     d.name, sem.number, c.section, s.created_at
            ORDER BY s.created_at DESC
        """, (current_user['user_id'],))
        surveys = cur.fetchall()
        for row in surveys:
            if row.get('created_at'):
                row['created_at'] = row['created_at'].strftime('%Y-%m-%d %H:%M')
        return jsonify(surveys), 200
    finally:
        conn.close()


# ── 3. Get Surveys for a specific class (faculty view) ────────────────────────
@survey_bp.route('/api/faculty/surveys/<int:class_id>', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_class_surveys(current_user, class_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        if not _faculty_assigned(cur, class_id, current_user['user_id']):
            return jsonify({'message': 'Unauthorized'}), 403

        cur.execute("""
            SELECT s.id, s.title, s.description, s.created_at,
                   u.name AS created_by_name,
                   COUNT(DISTINCT sq.id)  AS question_count,
                   COUNT(DISTINCT sr.id)  AS response_count
            FROM Surveys s
            JOIN Users u ON s.created_by = u.id
            LEFT JOIN SurveyQuestions sq ON s.id = sq.survey_id
            LEFT JOIN SurveyResponses  sr ON s.id = sr.survey_id
            WHERE s.class_id = %s
            GROUP BY s.id, s.title, s.description, s.created_at, u.name
            ORDER BY s.created_at DESC
        """, (class_id,))
        surveys = cur.fetchall()
        for row in surveys:
            if row.get('created_at'):
                row['created_at'] = row['created_at'].strftime('%Y-%m-%d %H:%M')
        return jsonify(surveys), 200
    finally:
        conn.close()


# ── 4. Get single survey with questions (faculty — for editing / viewing) ─────
@survey_bp.route('/api/faculty/survey/<int:survey_id>', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_survey_detail(current_user, survey_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id, title, description, class_id, created_at FROM Surveys WHERE id = %s AND created_by = %s",
            (survey_id, current_user['user_id'])
        )
        survey = cur.fetchone()
        if not survey:
            return jsonify({'message': 'Survey not found or unauthorized'}), 404
        if survey.get('created_at'):
            survey['created_at'] = survey['created_at'].strftime('%Y-%m-%d %H:%M')

        cur.execute(
            "SELECT id, question_text, type FROM SurveyQuestions WHERE survey_id = %s ORDER BY id",
            (survey_id,)
        )
        questions = cur.fetchall()
        for q in questions:
            if q['type'] == 'mcq':
                cur.execute(
                    "SELECT id, option_text FROM QuestionOptions WHERE question_id = %s ORDER BY id",
                    (q['id'],)
                )
                q['options'] = cur.fetchall()
            else:
                q['options'] = []

        return jsonify({'survey': survey, 'questions': questions}), 200
    finally:
        conn.close()


# ── 5. Get Survey Results (faculty) ──────────────────────────────────────────
@survey_bp.route('/api/faculty/survey/<int:survey_id>/results', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_survey_results(current_user, survey_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id, title FROM Surveys WHERE id = %s AND created_by = %s",
            (survey_id, current_user['user_id'])
        )
        survey = cur.fetchone()
        if not survey:
            return jsonify({'message': 'Survey not found or unauthorized'}), 404

        cur.execute(
            "SELECT sq.id, sq.question_text, sq.type FROM SurveyQuestions sq "
            "WHERE sq.survey_id = %s ORDER BY sq.id",
            (survey_id,)
        )
        questions = cur.fetchall()

        cur.execute(
            "SELECT COUNT(*) AS total FROM SurveyResponses WHERE survey_id = %s",
            (survey_id,)
        )
        total = cur.fetchone()['total']

        for q in questions:
            if q['type'] == 'mcq':
                # Count per option text
                cur.execute("""
                    SELECT sa.answer_text, COUNT(*) AS count
                    FROM SurveyAnswers sa
                    JOIN SurveyResponses sr ON sa.response_id = sr.id
                    WHERE sa.question_id = %s AND sr.survey_id = %s
                    GROUP BY sa.answer_text ORDER BY count DESC
                """, (q['id'], survey_id))
                q['answer_summary'] = cur.fetchall()
                q['raw_answers'] = []
            else:
                q['answer_summary'] = []
                cur.execute("""
                    SELECT u.name AS student_name, sa.answer_text
                    FROM SurveyAnswers sa
                    JOIN SurveyResponses sr ON sa.response_id = sr.id
                    JOIN Users u ON sr.student_id = u.id
                    WHERE sa.question_id = %s AND sr.survey_id = %s
                    ORDER BY sr.submitted_at
                """, (q['id'], survey_id))
                q['raw_answers'] = cur.fetchall()

        return jsonify({'survey': survey, 'questions': questions, 'total_responses': total}), 200
    finally:
        conn.close()


# ── 6. Delete Survey (faculty — owner only) ───────────────────────────────────
@survey_bp.route('/api/faculty/survey/<int:survey_id>', methods=['DELETE'])
@token_required(allowed_roles=['faculty'])
def delete_survey(current_user, survey_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM Surveys WHERE id = %s AND created_by = %s",
            (survey_id, current_user['user_id'])
        )
        if not cur.fetchone():
            return jsonify({'message': 'Survey not found or unauthorized'}), 404

        cur.execute("DELETE FROM Surveys WHERE id = %s", (survey_id,))
        conn.commit()
        return jsonify({'message': 'Survey deleted'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


# ── Legacy add-question / add-option (kept for backward compat) ───────────────
@survey_bp.route('/api/faculty/add-question', methods=['POST'])
@token_required(allowed_roles=['faculty'])
def add_question(current_user):
    data = request.json or {}
    survey_id     = data.get('survey_id')
    question_text = (data.get('question_text') or '').strip()
    q_type        = (data.get('type') or '').lower()

    if not all([survey_id, question_text, q_type]):
        return jsonify({'message': 'Missing fields'}), 400
    if q_type not in ('mcq', 'text'):
        return jsonify({'message': 'type must be mcq or text'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM Surveys WHERE id = %s AND created_by = %s",
            (survey_id, current_user['user_id'])
        )
        if not cur.fetchone():
            return jsonify({'message': 'Unauthorized or survey not found'}), 403

        cur.execute("""
            INSERT INTO SurveyQuestions (survey_id, question_text, type)
            VALUES (%s, %s, %s) RETURNING id, survey_id, question_text, type
        """, (survey_id, question_text, q_type))
        question = cur.fetchone()
        conn.commit()
        return jsonify(question), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


@survey_bp.route('/api/faculty/add-option', methods=['POST'])
@token_required(allowed_roles=['faculty'])
def add_option(current_user):
    data        = request.json or {}
    question_id = data.get('question_id')
    option_text = (data.get('option_text') or '').strip()

    if not all([question_id, option_text]):
        return jsonify({'message': 'Missing fields'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            SELECT sq.id FROM SurveyQuestions sq
            JOIN Surveys s ON sq.survey_id = s.id
            WHERE sq.id = %s AND s.created_by = %s
        """, (question_id, current_user['user_id']))
        if not cur.fetchone():
            return jsonify({'message': 'Unauthorized or question not found'}), 403

        cur.execute("""
            INSERT INTO QuestionOptions (question_id, option_text)
            VALUES (%s, %s) RETURNING id, question_id, option_text
        """, (question_id, option_text))
        option = cur.fetchone()
        conn.commit()
        return jsonify(option), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


# Legacy alias
@survey_bp.route('/api/faculty/survey/<int:survey_id>/questions', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_survey_questions(current_user, survey_id):
    return get_survey_detail.__wrapped__(current_user, survey_id)


# Legacy alias kept
@survey_bp.route('/api/faculty/survey-results/<int:survey_id>', methods=['GET'])
@token_required(allowed_roles=['faculty'])
def get_survey_results_legacy(current_user, survey_id):
    return get_survey_results.__wrapped__(current_user, survey_id)


# ═══════════════════════════════════════════════════════════════════════════════
# STUDENT ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. Get surveys for student's class (with submitted flag) ──────────────────
@survey_bp.route('/api/student/surveys', methods=['GET'])
@token_required(allowed_roles=['student'])
def get_student_surveys(current_user):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
        res = cur.fetchone()
        if not res or not res['class_id']:
            return jsonify([]), 200

        class_id = res['class_id']
        cur.execute("""
            SELECT s.id, s.title, s.description, s.created_at,
                   u.name AS created_by_name,
                   COUNT(DISTINCT sq.id) AS question_count,
                   CASE WHEN sr.id IS NOT NULL THEN TRUE ELSE FALSE END AS submitted
            FROM Surveys s
            JOIN Users u ON s.created_by = u.id
            LEFT JOIN SurveyQuestions sq ON s.id = sq.survey_id
            LEFT JOIN SurveyResponses sr ON s.id = sr.survey_id AND sr.student_id = %s
            WHERE s.class_id = %s
            GROUP BY s.id, s.title, s.description, s.created_at, u.name, sr.id
            ORDER BY s.created_at DESC
        """, (current_user['user_id'], class_id))
        surveys = cur.fetchall()
        for row in surveys:
            if row.get('created_at'):
                row['created_at'] = row['created_at'].strftime('%Y-%m-%d')
        return jsonify(surveys), 200
    finally:
        conn.close()


# ── 2. Get single survey for answering ───────────────────────────────────────
@survey_bp.route('/api/student/survey/<int:survey_id>', methods=['GET'])
@token_required(allowed_roles=['student'])
def get_survey_for_student(current_user, survey_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
        res = cur.fetchone()
        if not res:
            return jsonify({'message': 'Student not found'}), 404

        cur.execute(
            "SELECT id, title, description, class_id FROM Surveys WHERE id = %s AND class_id = %s",
            (survey_id, res['class_id'])
        )
        survey = cur.fetchone()
        if not survey:
            return jsonify({'message': 'Survey not found or not assigned to your class'}), 404

        # Check already submitted
        cur.execute(
            "SELECT id FROM SurveyResponses WHERE survey_id = %s AND student_id = %s",
            (survey_id, current_user['user_id'])
        )
        already_submitted = bool(cur.fetchone())

        cur.execute(
            "SELECT id, question_text, type FROM SurveyQuestions WHERE survey_id = %s ORDER BY id",
            (survey_id,)
        )
        questions = cur.fetchall()
        for q in questions:
            if q['type'] == 'mcq':
                cur.execute(
                    "SELECT id, option_text FROM QuestionOptions WHERE question_id = %s ORDER BY id",
                    (q['id'],)
                )
                q['options'] = cur.fetchall()
            else:
                q['options'] = []

        return jsonify({'survey': survey, 'questions': questions, 'already_submitted': already_submitted}), 200
    finally:
        conn.close()


# ── 3. Submit Survey ──────────────────────────────────────────────────────────
@survey_bp.route('/api/student/surveys/<int:survey_id>/submit', methods=['POST'])
@token_required(allowed_roles=['student'])
def submit_survey(current_user, survey_id):
    data    = request.json or {}
    answers = data.get('answers', [])

    if not answers:
        return jsonify({'message': 'answers array is required'}), 400

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        # Duplicate prevention
        cur.execute(
            "SELECT id FROM SurveyResponses WHERE survey_id = %s AND student_id = %s",
            (survey_id, current_user['user_id'])
        )
        if cur.fetchone():
            return jsonify({'message': 'You have already submitted this survey'}), 409

        # Ensure student belongs to the class
        cur.execute("SELECT class_id FROM Students WHERE user_id = %s", (current_user['user_id'],))
        student = cur.fetchone()
        cur.execute("SELECT class_id FROM Surveys WHERE id = %s", (survey_id,))
        survey  = cur.fetchone()
        if not student or not survey:
            return jsonify({'message': 'Survey or student not found'}), 404
        if student['class_id'] != survey['class_id']:
            return jsonify({'message': 'Unauthorized: survey not assigned to your class'}), 403

        # Validate all questions answered
        cur.execute(
            "SELECT COUNT(*) AS total FROM SurveyQuestions WHERE survey_id = %s",
            (survey_id,)
        )
        total_qs = cur.fetchone()['total']
        if len(answers) < total_qs:
            return jsonify({'message': f'Please answer all {total_qs} questions'}), 400

        # Create response record
        cur.execute("""
            INSERT INTO SurveyResponses (survey_id, student_id)
            VALUES (%s, %s) RETURNING id
        """, (survey_id, current_user['user_id']))
        response_id = cur.fetchone()['id']

        # Insert answers — support both text answers and MCQ (store option text)
        for ans in answers:
            q_id        = ans.get('question_id')
            answer_text = ans.get('answer_text') or ans.get('answer')
            option_id   = ans.get('selected_option_id')

            # For MCQ: resolve option text from option_id if text not provided
            if option_id and not answer_text:
                cur.execute(
                    "SELECT option_text FROM QuestionOptions WHERE id = %s",
                    (option_id,)
                )
                opt = cur.fetchone()
                answer_text = opt['option_text'] if opt else ''

            if q_id:
                cur.execute("""
                    INSERT INTO SurveyAnswers (response_id, question_id, answer_text)
                    VALUES (%s, %s, %s)
                """, (response_id, q_id, answer_text or ''))

        log_activity(current_user['user_id'], 'SURVEY_SUBMITTED', entity_type='survey', entity_id=survey_id, cursor=cur)
        conn.commit()
        return jsonify({'message': 'Survey submitted successfully'}), 201

    except Exception as e:
        conn.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        conn.close()


# Legacy route kept
@survey_bp.route('/api/student/submit-survey', methods=['POST'])
@token_required(allowed_roles=['student'])
def submit_survey_legacy(current_user):
    data      = request.json or {}
    survey_id = data.get('survey_id')
    if not survey_id:
        return jsonify({'message': 'survey_id is required'}), 400
    # Delegate to the canonical handler
    return submit_survey.__wrapped__(current_user, survey_id)
