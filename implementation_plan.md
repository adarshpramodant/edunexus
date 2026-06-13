# Implementation Plan - Student Performance Analytics System

I have designed a production-grade, highly optimized, and visually stunning **Student Performance Analytics System** for the EduNexus ERP platform. This system avoids database bloating by utilizing real-time, highly-indexed **PostgreSQL Views** and **Aggregated Queries** to deliver actionable educational insights—such as early at-risk student detection, top performer recognition, class performance reports, and subject-wise trends—instead of generic, chart-heavy business intelligence layouts.

---

## 1. User Access & Security Scoping Model

The system strictly enforces the EduNexus role hierarchy and institutional data isolation policies:
- **Administrators**: Full institutional visibility. Can query analytics across all departments, semesters, and classes, and modify institutional analytics thresholds.
- **Class / Vice Class Teachers**: Can view performance summaries, at-risk listings, and detailed metrics for classes they are assigned to.
- **Assigned Subject Teachers**: Can view subject-specific performance reports and metrics for classes they teach.
- **Students**: Heavily scoped. Students are strictly blocked from all general dashboard endpoints and can **only** query their own personal analytics payload. Attempts to view other students' analytics are blocked with `HTTP 403 Forbidden`.

---

## 2. Database Schema & Optimized Real-Time Views

We will create a lightweight persistent table for thresholds and a set of highly optimized SQL Views to make query execution instantaneous.

### A. Persistent Table: `AnalyticsThresholds`
Stores institutional threshold configurations. If an institution does not define custom thresholds, the APIs automatically fall back to standard defaults (75% attendance, 60% assignment completion, 50% marks).

```sql
CREATE TABLE IF NOT EXISTS AnalyticsThresholds (
    institution_id INTEGER PRIMARY KEY REFERENCES Institutions(id) ON DELETE CASCADE,
    attendance_threshold DECIMAL(5,2) DEFAULT 75.00 CHECK (attendance_threshold BETWEEN 0 AND 100),
    assignment_threshold DECIMAL(5,2) DEFAULT 60.00 CHECK (assignment_threshold BETWEEN 0 AND 100),
    marks_threshold DECIMAL(5,2) DEFAULT 50.00 CHECK (marks_threshold BETWEEN 0 AND 100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### B. Core Real-Time SQL Views
1. **`vw_StudentOverallAttendance`**: Aggregates total hours and present hours (status in `'P'`, `'DL'`) per student, calculating real-time attendance percentage.
2. **`vw_StudentAssignmentSummary`**: Cross-joins students with active, published assignments in their class to compute total class assignments, student submissions, late submissions, missing assignments (where the deadline has passed and no submission exists), and assignment completion percentage.
3. **`vw_StudentMarksSummary`**: Computes overall average marks for each student based on the existing `Marks` table.
4. **`vw_StudentPerformanceAnalytics`**: Consolidates profile fields (register number, class, department, semester) with the attendance, assignment, and marks summary views into a unified analytical overview.

---

## 3. Proposed Backend REST APIs (`/api/analytics`)

All endpoints will be built under the `/api/analytics` prefix in `backend/analytics_routes.py`:

| Endpoint | Method | Allowed Roles | Description |
|---|---|---|---|
| `/settings` | `GET` | `admin`, `faculty` | Retrieves the analytics thresholds for the institution (or defaults). |
| `/settings` | `POST` | `admin` | Updates custom thresholds. Audits with `ANALYTICS_SETTINGS_UPDATED` log. |
| `/summary` | `GET` | `admin`, `faculty` | Fetches dashboard summary counts (total students, at-risk count, top performers, averages). |
| `/at-risk` | `GET` | `admin`, `faculty` | Returns a paginated, filterable list of at-risk students (with specific flags). |
| `/top-performers`| `GET` | `admin`, `faculty` | Returns a paginated list of students with averages above threshold. |
| `/class/<int:class_id>`| `GET` | `admin`, `faculty` | Aggregates class averages, attendance rates, and grading distribution bands. |
| `/subject/<int:subject_id>`| `GET`| `admin`, `faculty` | Computes subject-specific metrics (average, highest, lowest, attendance trends). |
| `/student` | `GET` | `admin`, `faculty`, `student`| Fetches personal analytics (class averages comparison, standing, risk alerts). |
| `/export/pdf` | `GET` | `admin`, `faculty` | Streams a beautifully structured ReportLab PDF. Audits with `ANALYTICS_EXPORT_CREATED`. |

---

## 4. Frontend UI & Dashboard Integrations

We will create a stunning new analytics portal and integrate widgets onto existing dashboards using our standard premium glassmorphism theme:

### A. New Academic Analytics Portal (`frontend/analytics.html`)
- **Actionable Insights Panel**: Features high-end indicators showing total at-risk counts, top-performers, and aggregate metrics.
- **Interactive Listing Grids**: Paginated tables for At-Risk Students and Top Performers, filterable by class and reason tags (e.g., "Low Attendance", "Missing Assignments").
- **Dynamic Progress Rings**: Visualizes overall metrics and grade distribution bands.
- **Threshold Settings Control (Admin-Only)**: Interactive sliders to configure thresholds with instant save feedback.
- **PDF Report Action Bar**: Download button that invokes `/api/analytics/export/pdf` with active filters.

### B. Dashboard Summaries
- **Admin Overview Section**: Integrated institutional averages and overall at-risk percentages.
- **Faculty Dashboard Overview**: Embedded "Class Analytics Summary" and a compact "At-Risk Students List" with quick-alert tags.
- **Student Dashboard Section**: Custom tab "My Academic Performance" comparing personal scores against class averages.

---

## 5. Verification Plan

We will add a complete automated testing suite inside `test_suite.py` under section `12. STUDENT PERFORMANCE ANALYTICS TESTS` covering:

### Automated Tests
1. **DB Setup & Migration**: Executes programmatic runner `backend/create_analytics_tables.py` to create tables and views.
2. **Retrieve Default Thresholds**: Asserts that `GET /api/analytics/settings` returns default values.
3. **Admin Updates Settings**: Asserts that `POST /api/analytics/settings` updates configurations and writes to `AnalyticsThresholds`.
4. **At-Risk Detection Scenarios**:
   - Asserts that a student with low attendance is flagged as at-risk.
   - Asserts that a student with missing assignments is flagged as at-risk.
   - Asserts that a student with poor average marks is flagged as at-risk.
5. **Top Performers list**: Asserts that students with average marks >= thresholds are correctly categorized.
6. **Class Scoping Security**:
   - Asserts that unassigned faculty are blocked from accessing class reports (`HTTP 403`).
   - Asserts that assigned faculty can view reports only for their classes.
7. **Student Scoping Security**:
   - Asserts that students are blocked from `/api/analytics/summary`, `/at-risk`, and `/top-performers` (`HTTP 403`).
   - Asserts that student can retrieve `/api/analytics/student` for their own ID, but is blocked from requesting other IDs.
8. **PDF Export & Audits**: Asserts that exporting class reports returns an `application/pdf` stream and writes the `ANALYTICS_EXPORT_CREATED` action to the Activity Logs.

---

## Proposed Changes

### Database & Migrations

#### [NEW] [create_analytics_tables.py](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/backend/create_analytics_tables.py)
Programmatic DB migration runner to define the persistent `AnalyticsThresholds` configuration table, create database views `vw_StudentOverallAttendance`, `vw_StudentAssignmentSummary`, `vw_StudentMarksSummary`, and `vw_StudentPerformanceAnalytics`, and update reference `schema.sql`.

---

### Backend Components

#### [NEW] [analytics_routes.py](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/backend/analytics_routes.py)
Flask API blueprint containing all CRUD and aggregation methods for student performance reports, dynamic security, threshold configurations, ReportLab PDF streaming, and activity log auditing.

#### [MODIFY] [app.py](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/backend/app.py)
Import and register `analytics_bp` blueprint on prefix `/api/analytics`.

---

### Frontend Components

#### [NEW] [analytics.html](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/frontend/analytics.html)
Interactive, modern monthly class performance reporting and thresholds settings dashboard portal.

#### [NEW] [analytics.js](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/frontend/js/analytics.js)
Dynamic logic handling pagination, class filters, settings updates, progress rings, and PDF document downloads.

#### [MODIFY] [student_dashboard.html](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/frontend/student_dashboard.html) / [student.js](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/frontend/js/student.js)
Integrate dynamic private analytics widget into the student dashboard.

#### [MODIFY] [faculty_dashboard.html](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/frontend/faculty_dashboard.html) / [faculty.js](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/frontend/js/faculty.js)
Integrate Class Analytics Summary and At-Risk students alert widget into faculty home tab.

#### [MODIFY] [admin_dashboard.html](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/frontend/admin_dashboard.html) / [admin.js](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/frontend/js/admin.js)
Integrate institutional summary counters into admin main landing page.

---

### Verification Suite

#### [MODIFY] [test_suite.py](file:///c:/Users/ADARSH/Desktop/Projects/EduNexus(main)/test_suite.py)
Append Section 12 integration tests covering settings, at-risk flag checks, security barriers, PDF downloads, and activity audits.
