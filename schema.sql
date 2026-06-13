-- EduNexus Supabase/PostgreSQL Schema

CREATE TABLE Institutions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE Users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL, 
    role VARCHAR(20) NOT NULL CHECK (role IN ('student', 'faculty', 'admin')),
    institution_id INTEGER REFERENCES Institutions(id) NULL
);

CREATE TABLE Departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    institution_id INTEGER REFERENCES Institutions(id) NOT NULL
);

CREATE TABLE Semesters (
    id SERIAL PRIMARY KEY,
    number INTEGER NOT NULL,
    institution_id INTEGER REFERENCES Institutions(id) NOT NULL
);

CREATE TABLE Classes (
    id SERIAL PRIMARY KEY,
    department_id INTEGER REFERENCES Departments(id) NOT NULL,
    semester_id INTEGER REFERENCES Semesters(id) NOT NULL,
    section VARCHAR(10) NOT NULL
);

CREATE TABLE Students (
    user_id INTEGER PRIMARY KEY REFERENCES Users(id) ON DELETE CASCADE,
    register_number VARCHAR(100) UNIQUE NOT NULL,
    class_id INTEGER REFERENCES Classes(id) NULL
);

CREATE TABLE Teachers (
    user_id INTEGER PRIMARY KEY REFERENCES Users(id) ON DELETE CASCADE
);

CREATE TABLE ClassAssignments (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER REFERENCES Teachers(user_id) NOT NULL,
    class_id INTEGER REFERENCES Classes(id) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('class_teacher', 'vice_class_teacher', 'subject_teacher'))
);

CREATE TABLE Subjects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50),
    class_id INTEGER REFERENCES Classes(id)
);

CREATE TABLE SubjectAssignments (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER REFERENCES Teachers(user_id) NOT NULL,
    class_id INTEGER REFERENCES Classes(id) NOT NULL,
    subject_id INTEGER REFERENCES Subjects(id) NOT NULL
);

CREATE TABLE Attendance (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES Students(user_id) NOT NULL,
    class_id INTEGER REFERENCES Classes(id) NOT NULL,
    date DATE NOT NULL,
    hour INTEGER NOT NULL,
    subject_id INTEGER REFERENCES Subjects(id) NOT NULL,
    status VARCHAR(2) NOT NULL CHECK (status IN ('P', 'AB', 'SR', 'DL')),
    updated_by INTEGER REFERENCES Users(id) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE Marks (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES Students(user_id) NOT NULL,
    subject_id INTEGER REFERENCES Subjects(id) NOT NULL,
    mark_type VARCHAR(50) NOT NULL,
    mark_name VARCHAR(100) NOT NULL,
    marks DECIMAL(5,2) NOT NULL,
    updated_by INTEGER REFERENCES Users(id) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE AttendanceHistory (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES Users(id) ON DELETE CASCADE,
    class_id INTEGER NOT NULL,
    date DATE NOT NULL,
    hour INTEGER NOT NULL,
    subject_id INTEGER NOT NULL, 
    semester_id INTEGER REFERENCES Semesters(id),
    status VARCHAR(2) NOT NULL,
    updated_by INTEGER,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE MarksHistory (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES Users(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL,
    semester_id INTEGER REFERENCES Semesters(id),
    mark_type VARCHAR(50) NOT NULL,
    mark_name VARCHAR(100) NOT NULL,
    marks DECIMAL(5,2) NOT NULL,
    updated_by INTEGER,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Survey & Feedback System ──────────────────────────────────────────────

CREATE TABLE Surveys (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    created_by INTEGER REFERENCES Users(id) ON DELETE CASCADE NOT NULL,
    class_id INTEGER REFERENCES Classes(id) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE SurveyQuestions (
    id SERIAL PRIMARY KEY,
    survey_id INTEGER REFERENCES Surveys(id) ON DELETE CASCADE NOT NULL,
    question_text TEXT NOT NULL,
    type VARCHAR(10) NOT NULL CHECK (type IN ('mcq', 'text'))
);

CREATE TABLE QuestionOptions (
    id SERIAL PRIMARY KEY,
    question_id INTEGER REFERENCES SurveyQuestions(id) ON DELETE CASCADE NOT NULL,
    option_text VARCHAR(255) NOT NULL
);

CREATE TABLE SurveyResponses (
    id SERIAL PRIMARY KEY,
    survey_id INTEGER REFERENCES Surveys(id) ON DELETE CASCADE NOT NULL,
    student_id INTEGER REFERENCES Users(id) ON DELETE CASCADE NOT NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (survey_id, student_id)
);

CREATE TABLE SurveyAnswers (
    id SERIAL PRIMARY KEY,
    response_id INTEGER REFERENCES SurveyResponses(id) ON DELETE CASCADE NOT NULL,
    question_id INTEGER REFERENCES SurveyQuestions(id) ON DELETE CASCADE NOT NULL,
    answer_text TEXT
);

-- ── Dynamic Timetable System ─────────────────────────────────────────────

CREATE TABLE Timetable (
    id SERIAL PRIMARY KEY,
    class_id INTEGER REFERENCES Classes(id) ON DELETE CASCADE NOT NULL,
    day VARCHAR(10) NOT NULL CHECK (day IN ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')),
    hour INTEGER NOT NULL CHECK (hour BETWEEN 1 AND 8),
    subject_id INTEGER REFERENCES Subjects(id) ON DELETE SET NULL,
    UNIQUE (class_id, day, hour)
);

-- ── Attendance Unique Constraint (run ALTER if table already exists) ──────
-- ALTER TABLE Attendance ADD CONSTRAINT uq_attendance_slot_student
--     UNIQUE (student_id, class_id, date, hour, subject_id);

-- ── Attendance Edit History / Audit Log ───────────────────────────────────

CREATE TABLE AttendanceLogs (
    id SERIAL PRIMARY KEY,
    attendance_id INTEGER REFERENCES Attendance(id) ON DELETE CASCADE NOT NULL,
    previous_status VARCHAR(2),          -- NULL means initial insert
    new_status VARCHAR(2) NOT NULL,
    changed_by INTEGER REFERENCES Users(id) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Enterprise Activity Log System ───────────────────────────────────────

CREATE TABLE ActivityLogs (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER REFERENCES Institutions(id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES Users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id VARCHAR(100),
    old_data JSONB,
    new_data JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_activity_logs_institution ON ActivityLogs(institution_id);
CREATE INDEX idx_activity_logs_user ON ActivityLogs(user_id);
CREATE INDEX idx_activity_logs_action ON ActivityLogs(action);
CREATE INDEX idx_activity_logs_created_at ON ActivityLogs(created_at DESC);
CREATE INDEX idx_activity_logs_entity ON ActivityLogs(entity_type, entity_id);

-- ── Enterprise Document Management System ─────────────────────────────────

CREATE TABLE Documents (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER REFERENCES Institutions(id) ON DELETE CASCADE,
    uploaded_by INTEGER REFERENCES Users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    original_filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(500) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL,
    category VARCHAR(50) NOT NULL,
    visibility VARCHAR(20) NOT NULL CHECK (visibility IN ('public', 'role', 'class')),
    target_role VARCHAR(20) NULL CHECK (target_role IN ('student', 'faculty', 'admin')),
    target_class_id INTEGER REFERENCES Classes(id) ON DELETE SET NULL,
    version INTEGER DEFAULT 1,
    is_archived BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_documents_institution ON Documents(institution_id);
CREATE INDEX idx_documents_class ON Documents(target_class_id);
CREATE INDEX idx_documents_uploaded_by ON Documents(uploaded_by);
CREATE INDEX idx_documents_visibility ON Documents(visibility);
CREATE INDEX idx_documents_category ON Documents(category);
CREATE INDEX idx_documents_is_deleted ON Documents(is_deleted);
CREATE INDEX idx_documents_is_archived ON Documents(is_archived);
CREATE INDEX idx_documents_created_at ON Documents(created_at DESC);

-- ── Assignment Submission & Evaluation System ─────────────────────────────

CREATE TABLE Assignments (
    id SERIAL PRIMARY KEY,
    class_id INTEGER REFERENCES Classes(id) ON DELETE CASCADE,
    subject_id INTEGER REFERENCES Subjects(id) ON DELETE CASCADE,
    created_by INTEGER REFERENCES Users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    max_marks DECIMAL(5,2) NOT NULL,
    deadline TIMESTAMP NOT NULL,
    allow_resubmission BOOLEAN DEFAULT TRUE,
    status VARCHAR(20) DEFAULT 'published' CHECK (status IN ('draft', 'published', 'closed', 'archived')),
    is_active BOOLEAN DEFAULT TRUE,
    closed_at TIMESTAMP NULL,
    marks_published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE AssignmentSubmissions (
    id SERIAL PRIMARY KEY,
    assignment_id INTEGER REFERENCES Assignments(id) ON DELETE CASCADE,
    student_id INTEGER REFERENCES Users(id) ON DELETE CASCADE,
    document_id INTEGER REFERENCES Documents(id) ON DELETE SET NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'submitted' CHECK (status IN ('submitted', 'evaluated')),
    marks DECIMAL(5,2) NULL,
    feedback TEXT,
    evaluated_by INTEGER REFERENCES Users(id) ON DELETE SET NULL,
    evaluated_at TIMESTAMP NULL,
    submission_count INTEGER DEFAULT 1,
    last_resubmitted_at TIMESTAMP NULL,
    is_late BOOLEAN DEFAULT FALSE,
    CONSTRAINT uq_assignment_student UNIQUE (assignment_id, student_id)
);

CREATE INDEX idx_assignments_class ON Assignments(class_id);
CREATE INDEX idx_assignments_subject ON Assignments(subject_id);
CREATE INDEX idx_assignments_status ON Assignments(status);
CREATE INDEX idx_submissions_assignment ON AssignmentSubmissions(assignment_id);
CREATE INDEX idx_submissions_student ON AssignmentSubmissions(student_id);
CREATE INDEX idx_submissions_status ON AssignmentSubmissions(status);

-- ── Academic Calendar & Event Management System ───────────────────────────

CREATE TABLE IF NOT EXISTS AcademicEvents (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER REFERENCES Institutions(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    event_type VARCHAR(30) NOT NULL CHECK (event_type IN ('holiday', 'internal_exam', 'university_exam', 'lab_exam', 'assignment_deadline', 'survey_deadline', 'project_review', 'seminar', 'workshop', 'event', 'other')),
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    target_role VARCHAR(20) NULL CHECK (target_role IN ('student', 'faculty', 'admin', 'all')),
    target_class_id INTEGER REFERENCES Classes(id) ON DELETE CASCADE NULL,
    created_by INTEGER REFERENCES Users(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'published' CHECK (status IN ('draft', 'published', 'cancelled', 'completed')),
    document_id INTEGER REFERENCES Documents(id) ON DELETE SET NULL NULL,
    event_color VARCHAR(30) DEFAULT 'indigo',
    recurrence_pattern VARCHAR(30) DEFAULT 'none' CHECK (recurrence_pattern IN ('none', 'daily', 'weekly', 'monthly', 'yearly')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_institution ON AcademicEvents(institution_id);
CREATE INDEX idx_events_class ON AcademicEvents(target_class_id);
CREATE INDEX idx_events_type ON AcademicEvents(event_type);
CREATE INDEX idx_events_start ON AcademicEvents(start_date DESC);
CREATE INDEX idx_events_is_active ON AcademicEvents(is_active);

-- ── Student Performance Analytics System ───────────────────────────

CREATE TABLE IF NOT EXISTS AnalyticsThresholds (
    institution_id INTEGER PRIMARY KEY REFERENCES Institutions(id) ON DELETE CASCADE,
    attendance_threshold DECIMAL(5,2) DEFAULT 75.00 CHECK (attendance_threshold BETWEEN 0 AND 100),
    assignment_threshold DECIMAL(5,2) DEFAULT 60.00 CHECK (assignment_threshold BETWEEN 0 AND 100),
    marks_threshold DECIMAL(5,2) DEFAULT 50.00 CHECK (marks_threshold BETWEEN 0 AND 100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE VIEW vw_StudentOverallAttendance AS
SELECT 
    s.user_id AS student_id,
    s.class_id,
    COUNT(att.id) AS total_hours,
    SUM(CASE WHEN att.status IN ('P', 'DL') THEN 1 ELSE 0 END) AS present_hours,
    COALESCE(
        ROUND((SUM(CASE WHEN att.status IN ('P', 'DL') THEN 1 ELSE 0 END)::decimal / NULLIF(COUNT(att.id), 0)) * 100, 2),
        100.00
    ) AS attendance_percentage
FROM Students s
LEFT JOIN Attendance att ON s.user_id = att.student_id AND s.class_id = att.class_id
GROUP BY s.user_id, s.class_id;

CREATE OR REPLACE VIEW vw_StudentAssignmentSummary AS
SELECT 
    s.user_id AS student_id,
    s.class_id,
    COUNT(a.id) AS total_assignments,
    COUNT(sub.id) AS total_submissions,
    SUM(CASE WHEN sub.is_late = TRUE THEN 1 ELSE 0 END) AS late_submissions,
    SUM(CASE WHEN sub.id IS NULL AND a.deadline < CURRENT_TIMESTAMP THEN 1 ELSE 0 END) AS missing_assignments,
    COALESCE(
        ROUND((COUNT(sub.id)::decimal / NULLIF(COUNT(a.id), 0)) * 100, 2),
        100.00
    ) AS completion_percentage
FROM Students s
CROSS JOIN Assignments a
LEFT JOIN AssignmentSubmissions sub ON a.id = sub.assignment_id AND s.user_id = sub.student_id
WHERE s.class_id = a.class_id AND a.is_active = TRUE AND a.status = 'published'
GROUP BY s.user_id, s.class_id;

CREATE OR REPLACE VIEW vw_StudentMarksSummary AS
SELECT 
    s.user_id AS student_id,
    s.class_id,
    COUNT(m.id) AS total_marks_records,
    COALESCE(ROUND(AVG(m.marks), 2), 0.00) AS average_marks
FROM Students s
LEFT JOIN Marks m ON s.user_id = m.student_id
GROUP BY s.user_id, s.class_id;

CREATE OR REPLACE VIEW vw_StudentPerformanceAnalytics AS
SELECT 
    s.user_id AS student_id,
    u.name AS student_name,
    s.register_number,
    s.class_id,
    c.section AS class_section,
    dept.name AS department_name,
    sem.number AS semester_number,
    u.institution_id,
    COALESCE(att.attendance_percentage, 100.00) AS attendance_percentage,
    COALESCE(att.total_hours, 0) AS attendance_total_hours,
    COALESCE(att.present_hours, 0) AS attendance_present_hours,
    COALESCE(assign.completion_percentage, 100.00) AS assignment_completion_percentage,
    COALESCE(assign.total_assignments, 0) AS assignment_total_count,
    COALESCE(assign.total_submissions, 0) AS assignment_submitted_count,
    COALESCE(assign.missing_assignments, 0) AS assignment_missing_count,
    COALESCE(assign.late_submissions, 0) AS assignment_late_count,
    COALESCE(marks.average_marks, 0.00) AS average_marks,
    COALESCE(marks.total_marks_records, 0) AS marks_records_count
FROM Students s
JOIN Users u ON s.user_id = u.id
LEFT JOIN Classes c ON s.class_id = c.id
LEFT JOIN Departments dept ON c.department_id = dept.id
LEFT JOIN Semesters sem ON c.semester_id = sem.id
LEFT JOIN vw_StudentOverallAttendance att ON s.user_id = att.student_id
LEFT JOIN vw_StudentAssignmentSummary assign ON s.user_id = assign.student_id
LEFT JOIN vw_StudentMarksSummary marks ON s.user_id = marks.student_id;

CREATE OR REPLACE VIEW vw_SubjectRiskAnalysis AS
SELECT 
    sub.id AS subject_id,
    sub.name AS subject_name,
    sub.code AS subject_code,
    sub.class_id,
    c.section AS class_section,
    dept.name AS department_name,
    sem.number AS semester_number,
    COALESCE(ROUND(AVG(m.marks), 2), 0.00) AS average_marks,
    COALESCE(ROUND(MAX(m.marks), 2), 0.00) AS highest_marks,
    COALESCE(ROUND(MIN(m.marks), 2), 0.00) AS lowest_marks,
    COUNT(DISTINCT m.student_id) AS graded_students_count,
    COALESCE(
        ROUND((SUM(CASE WHEN att.status IN ('P', 'DL') THEN 1 ELSE 0 END)::decimal / NULLIF(COUNT(att.id), 0)) * 100, 2),
        100.00
    ) AS subject_attendance_percentage,
    COUNT(att.id) AS total_hours,
    SUM(CASE WHEN att.status = 'AB' THEN 1 ELSE 0 END) AS total_absences
FROM Subjects sub
LEFT JOIN Classes c ON sub.class_id = c.id
LEFT JOIN Departments dept ON c.department_id = dept.id
LEFT JOIN Semesters sem ON c.semester_id = sem.id
LEFT JOIN Marks m ON sub.id = m.subject_id
LEFT JOIN Attendance att ON sub.id = att.subject_id AND sub.class_id = att.class_id
GROUP BY sub.id, sub.name, sub.code, sub.class_id, c.section, dept.name, sem.number;
