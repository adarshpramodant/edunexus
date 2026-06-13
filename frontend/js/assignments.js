// ─────────────────────────────────────────────────────────────────────────────
// EduNexus — Enterprise Assignment System Client JS
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = 'http://localhost:5000/api';
const token = localStorage.getItem('token');
const role = localStorage.getItem('role');

// Guard against unauthenticated access
if (!token || !role) {
    window.location.href = 'login.html';
}

let activeStatusFilter = ''; // Empty means 'All Active' (published, closed)
let currentClassList = [];
let selectedFile = null;
let currentUserId = null;

// Parse current user_id from token
try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(window.atob(base64));
    currentUserId = payload.user_id;
} catch (e) {
    console.error('Failed to parse token', e);
}

function getAuthHeaders() {
    return {
        'Authorization': `Bearer ${token}`
    };
}

// ── Render Dynamic Sidebar Navigation ──
function renderSidebar() {
    const menu = document.getElementById('sidebar-menu');
    const portalTitle = document.getElementById('portal-title');
    if (!menu) return;

    if (portalTitle) {
        portalTitle.textContent = `EduNexus ${role.charAt(0).toUpperCase() + role.slice(1)}`;
    }

    let menuHtml = '';
    if (role === 'admin') {
        menuHtml = `
            <li><a href="admin_dashboard.html#overview"><i class="fas fa-home"></i> Overview</a></li>
            <li><a href="admin_dashboard.html#departments"><i class="fas fa-building"></i> Departments & Semesters</a></li>
            <li><a href="admin_dashboard.html#classes"><i class="fas fa-chalkboard"></i> Classes</a></li>
            <li><a href="admin_dashboard.html#users"><i class="fas fa-user-plus"></i> Add Users</a></li>
            <li><a href="admin_dashboard.html#manage-users"><i class="fas fa-users-cog"></i> Manage Users</a></li>
            <li><a href="admin_dashboard.html#assign-faculty"><i class="fas fa-user-tie"></i> Assign Faculty</a></li>
            <li><a href="admin_dashboard.html#promotion"><i class="fas fa-level-up-alt"></i> Promote Semester</a></li>
            <li><a href="documents.html"><i class="fas fa-folder-open"></i> Documents</a></li>
            <li class="active"><a href="assignments.html"><i class="fas fa-tasks"></i> Assignments</a></li>
        `;
    } else if (role === 'faculty') {
        menuHtml = `
            <li><a href="faculty_dashboard.html#classes"><i class="fas fa-chalkboard-teacher"></i> My Classes</a></li>
            <li><a href="faculty_dashboard.html#attendance"><i class="fas fa-clipboard-check"></i> Attendance</a></li>
            <li><a href="faculty_dashboard.html#marks"><i class="fas fa-star"></i> Marks</a></li>
            <li><a href="survey_manage.html"><i class="fas fa-poll"></i> Surveys</a></li>
            <li><a href="documents.html"><i class="fas fa-folder-open"></i> Documents</a></li>
            <li class="active"><a href="assignments.html"><i class="fas fa-tasks"></i> Assignments</a></li>
        `;
    } else if (role === 'student') {
        menuHtml = `
            <li><a href="student_dashboard.html#courses"><i class="fas fa-book"></i> My Courses</a></li>
            <li><a href="student_dashboard.html#schedule"><i class="fas fa-calendar-alt"></i> Class Schedule</a></li>
            <li><a href="student_dashboard.html#attendance"><i class="fas fa-user-check"></i> Attendance</a></li>
            <li><a href="student_dashboard.html#marks"><i class="fas fa-chart-bar"></i> Marks &amp; Performance</a></li>
            <li><a href="survey_student.html"><i class="fas fa-poll"></i> Surveys</a></li>
            <li><a href="documents.html"><i class="fas fa-folder-open"></i> Documents</a></li>
            <li class="active"><a href="assignments.html"><i class="fas fa-tasks"></i> Assignments</a></li>
        `;
    }

    menu.innerHTML = menuHtml;

    // Show Create button and Drafts filters tab for Faculty/Admin
    if (role === 'admin' || role === 'faculty') {
        document.getElementById('faculty-actions-container').style.display = 'block';
        document.getElementById('tab-draft').style.display = 'block';
    }
}

// ── Fetch and Render Assignments ──
async function fetchAssignments() {
    const list = document.getElementById('assignments-list');
    list.innerHTML = '<p style="color:var(--text-muted); text-align:center; padding:2rem;"><i class="fas fa-circle-notch fa-spin"></i> Loading assignment listings…</p>';

    try {
        let url = `${API_BASE}/assignments`;
        if (activeStatusFilter) {
            url += `?status=${activeStatusFilter}`;
        }

        const res = await fetch(url, { headers: getAuthHeaders() });
        if (!res.ok) throw new Error('Failed to load assignments.');

        const assigns = await res.json();
        list.innerHTML = '';

        if (assigns.length === 0) {
            list.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 3rem; background: rgba(30, 41, 59, 0.2); border: 1px dashed var(--border-color); border-radius: 1rem;">
                    <i class="fas fa-tasks" style="font-size: 3rem; color: var(--text-muted); margin-bottom: 1rem; opacity: 0.4;"></i>
                    <p style="color: var(--text-muted); font-size: 0.95rem; margin: 0;">No assignments found matching the active filters.</p>
                </div>
            `;
            return;
        }

        assigns.forEach(assign => {
            const sizeLimitText = `Max Score: ${assign.max_marks}`;
            
            // Build deadline text
            const deadlineDate = assign.deadline ? new Date(assign.deadline) : null;
            const deadlineText = deadlineDate ? deadlineDate.toLocaleString(undefined, {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
            }) : 'No deadline';

            // Get status details
            let statusText = assign.status;
            let statusClass = assign.status;

            if (role === 'student' && assign.submission_status) {
                statusText = assign.submission_status === 'evaluated' ? 'graded' : 'submitted';
                statusClass = statusText;
            }

            // Student grading card details
            let gradeInfoHtml = '';
            if (role === 'student' && assign.submission_status === 'evaluated' && assign.submission_marks !== null) {
                gradeInfoHtml = `
                    <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 0.5rem; padding: 0.75rem; font-size: 0.8rem; margin-top:0.5rem;">
                        <div style="display:flex; justify-content:space-between; font-weight:700; color:#34d399;">
                            <span>Grade Score:</span>
                            <span>${assign.submission_marks} / ${assign.max_marks}</span>
                        </div>
                    </div>
                `;
            }

            // Action Buttons based on Role
            let actionHtml = '';
            if (role === 'admin' || role === 'faculty') {
                const closeBtn = assign.status === 'published' ? `
                    <button class="act-btn" onclick="handleCloseAssignment(${assign.id})" title="Close submissions"><i class="fas fa-times-circle"></i> Close</button>
                ` : '';

                const editBtn = !assign.marks_published ? `
                    <button class="act-btn" onclick="openEditModal(${JSON.stringify(assign).replace(/"/g, '&quot;')})" title="Edit Assignment"><i class="fas fa-edit"></i> Edit</button>
                ` : '';

                actionHtml = `
                    <div style="display:flex; justify-content:space-between; align-items:center; width:100%; border-top:1px solid rgba(255,255,255,0.05); padding-top:0.75rem; margin-top:0.25rem;">
                        <button class="btn" style="padding:0.4rem 0.8rem; font-size:0.78rem; margin:0;" onclick="openSubmissionsModal(${assign.id}, '${escapeHtml(assign.title)}', ${assign.max_marks})">
                            <i class="fas fa-users-cog"></i> Review Submissions
                        </button>
                        <div style="display:flex; gap:0.25rem;">
                            ${editBtn}
                            ${closeBtn}
                            <button class="act-btn danger" onclick="handleArchiveAssignment(${assign.id})" title="Archive / Delete"><i class="fas fa-trash-alt"></i></button>
                        </div>
                    </div>
                `;
            } else if (role === 'student') {
                let submitBtnText = 'Submit File';
                let canSubmit = true;

                if (assign.submission_status) {
                    submitBtnText = 'Resubmit';
                    canSubmit = assign.allow_resubmission;
                }

                if (assign.status === 'closed') {
                    canSubmit = false;
                    submitBtnText = 'Submissions Closed';
                }

                actionHtml = `
                    <div style="display:flex; justify-content:space-between; align-items:center; width:100%; border-top:1px solid rgba(255,255,255,0.05); padding-top:0.75rem; margin-top:0.25rem;">
                        <span style="font-size:0.75rem; color:var(--text-muted);">Status: <strong class="status-badge ${statusClass}">${statusText}</strong></span>
                        ${canSubmit ? `
                            <button class="btn" style="padding:0.45rem 0.95rem; font-size:0.78rem; margin:0;" onclick="openSubmitModal(${assign.id}, '${escapeHtml(assign.title)}', ${assign.max_marks}, '${deadlineText}')">
                                <i class="fas fa-cloud-upload-alt"></i> ${submitBtnText}
                            </button>
                        ` : `
                            <button class="btn" style="padding:0.45rem 0.95rem; font-size:0.78rem; margin:0; opacity:0.5; cursor:not-allowed;" disabled>
                                <i class="fas fa-ban"></i> Blocked
                            </button>
                        `}
                    </div>
                `;
            }

            list.innerHTML += `
                <div class="assign-card">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <span style="font-size:0.7rem; font-weight:700; color:var(--primary-color); text-transform:uppercase;">${escapeHtml(assign.subject_code)} | ${escapeHtml(assign.subject_name)}</span>
                        <span class="status-badge ${assign.status}">${assign.status}</span>
                    </div>
                    <h4 class="assign-title" title="${escapeHtml(assign.title)}">${escapeHtml(assign.title)}</h4>
                    <p class="assign-desc" title="${escapeHtml(assign.description || '')}">${escapeHtml(assign.description || 'No guidelines provided.')}</p>
                    
                    ${gradeInfoHtml}

                    <div class="assign-meta">
                        <span><i class="fas fa-calendar-alt" style="color:#ef4444;"></i> Due: ${deadlineText}</span>
                        <span><i class="fas fa-star" style="color:#fbbf24;"></i> ${sizeLimitText}</span>
                        <span><i class="fas fa-school"></i> Sec ${escapeHtml(assign.class_section)}</span>
                    </div>

                    ${actionHtml}
                </div>
            `;
        });

    } catch (err) {
        console.error(err);
        showToast('Error loading assignments.', 'error');
    }
}

// ── Toggle active status tabs ──
window.filterStatus = function(status, tabElement) {
    document.querySelectorAll('#status-filters .cat-tab').forEach(btn => btn.classList.remove('active'));
    tabElement.classList.add('active');

    activeStatusFilter = status;
    fetchAssignments();
};

// ── Overlay Modal Open & Close Creators ──
window.openCreateModal = async function() {
    document.getElementById('create-modal').classList.add('open');
    clearCreateForm();
    document.getElementById('modal-title-text').textContent = 'Create Assignment';
    document.getElementById('class-selectors-group').style.display = 'grid';
    await fetchAndPopulateClasses();
};

window.openEditModal = function(assign) {
    document.getElementById('create-modal').classList.add('open');
    clearCreateForm();

    document.getElementById('modal-title-text').textContent = 'Edit Assignment';
    document.getElementById('edit-assign-id').value = assign.id;
    document.getElementById('class-selectors-group').style.display = 'none'; // Lock class/subject on edit

    // Prepopulate
    document.getElementById('assign-title').value = assign.title;
    document.getElementById('assign-desc').value = assign.description || '';
    document.getElementById('assign-max-marks').value = assign.max_marks;
    
    // Parse timestamp safely into datetime-local
    if (assign.deadline) {
        const d = new Date(assign.deadline);
        const isoStr = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        document.getElementById('assign-deadline').value = isoStr;
    }

    document.getElementById('assign-status').value = assign.status === 'draft' ? 'draft' : 'published';
    document.getElementById('assign-allow-resubmit').checked = assign.allow_resubmission;
};

window.closeCreateModal = function() {
    document.getElementById('create-modal').classList.remove('open');
};

function clearCreateForm() {
    document.getElementById('assignment-form').reset();
    document.getElementById('edit-assign-id').value = '';
    document.getElementById('assign-error').style.display = 'none';
    document.getElementById('assign-error').textContent = '';
}

// ── Populate classes select ──
async function fetchAndPopulateClasses() {
    const select = document.getElementById('assign-class-select');
    select.innerHTML = '<option value="" disabled selected>Loading Classes…</option>';

    try {
        let res;
        if (role === 'admin') {
            res = await fetch(`${API_BASE}/admin/classes`, { headers: getAuthHeaders() });
        } else if (role === 'faculty') {
            res = await fetch(`${API_BASE}/faculty/my-classes`, { headers: getAuthHeaders() });
        }

        if (!res.ok) throw new Error('Failed.');

        currentClassList = await res.json();
        select.innerHTML = '<option value="" disabled selected>Select Class</option>';

        currentClassList.forEach(c => {
            const classId = c.class_id || c.id;
            const text = `${c.department} | Sem ${c.semester} | Sec ${c.section}`;
            select.innerHTML += `<option value="${classId}">${escapeHtml(text)}</option>`;
        });
    } catch (e) {
        select.innerHTML = '<option value="" disabled>Error loading classes</option>';
    }
}

// ── Populate subjects select dynamically ──
window.loadClassSubjects = async function() {
    const classId = parseInt(document.getElementById('assign-class-select').value);
    const select = document.getElementById('assign-subject-select');
    select.innerHTML = '<option value="" disabled selected>Select Subject</option>';

    if (!classId) return;

    try {
        if (role === 'faculty') {
            // Find class in our local grouped classes list
            const foundClass = currentClassList.find(c => (c.class_id || c.id) === classId);
            if (foundClass && foundClass.subjects) {
                // Fetch assigned subjects
                // We'll query faculty class details API to resolve subject IDs
                const res = await fetch(`${API_BASE}/faculty/class/${classId}`, { headers: getAuthHeaders() });
                const classDetails = await res.json();
                if (classDetails && classDetails.subjects) {
                    classDetails.subjects.forEach(s => {
                        select.innerHTML += `<option value="${s.id}">${escapeHtml(s.name)} (${escapeHtml(s.code || 'N/A')})</option>`;
                    });
                }
            }
        } else if (role === 'admin') {
            // Admins fetch subjects for the class from faculty classes details or general DB lookup
            // For simple Admin lookup, we can look at subjects assigned in ClassDetails
            const res = await fetch(`${API_BASE}/faculty/class/${classId}`, { headers: getAuthHeaders() });
            const classDetails = await res.json();
            if (classDetails && classDetails.subjects) {
                classDetails.subjects.forEach(s => {
                    select.innerHTML += `<option value="${s.id}">${escapeHtml(s.name)}</option>`;
                });
            }
        }
    } catch (e) {
        console.error('Failed to populate subjects select', e);
    }
};

// ── Save/Create Assignment Submit ──
window.handleAssignmentSubmit = async function(e) {
    e.preventDefault();

    const editId = document.getElementById('edit-assign-id').value;
    const title = document.getElementById('assign-title').value.trim();
    const description = document.getElementById('assign-desc').value.trim();
    const max_marks = document.getElementById('assign-max-marks').value;
    const deadline = document.getElementById('assign-deadline').value.replace('T', ' ') + ':00';
    const status = document.getElementById('assign-status').value;
    const allow_resubmission = document.getElementById('assign-allow-resubmit').checked;
    const errDiv = document.getElementById('assign-error');
    const btn = document.getElementById('assign-submit-btn');

    errDiv.style.display = 'none';

    let url = `${API_BASE}/assignments`;
    let method = 'POST';
    let payload = { title, description, max_marks, deadline, status, allow_resubmission };

    if (editId) {
        url += `/${editId}`;
        method = 'PUT';
    } else {
        const class_id = parseInt(document.getElementById('assign-class-select').value);
        const subject_id = parseInt(document.getElementById('assign-subject-select').value);
        if (!class_id || !subject_id) {
            errDiv.style.display = 'block';
            errDiv.textContent = 'Please select a Class and a Subject.';
            return;
        }
        payload.class_id = class_id;
        payload.subject_id = subject_id;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…';

    try {
        const res = await fetch(url, {
            method,
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (!res.ok) throw new Error(data.message || 'Saving failed.');

        showToast(data.message || 'Assignment saved successfully!', 'success');
        closeCreateModal();
        fetchAssignments();
    } catch (err) {
        errDiv.style.display = 'block';
        errDiv.textContent = err.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save';
    }
};

// ── Close Submissions (Soft close) ──
window.handleCloseAssignment = async function(assignId) {
    if (!confirm('Are you sure you want to close submissions for this assignment?')) return;

    try {
        const res = await fetch(`${API_BASE}/assignments/${assignId}/close`, {
            method: 'PUT',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Failed.');

        showToast(data.message, 'success');
        fetchAssignments();
    } catch (e) {
        showToast(e.message, 'error');
    }
};

// ── Archive Assignment (Soft Delete) ──
window.handleArchiveAssignment = async function(assignId) {
    if (!confirm('Are you sure you want to archive/delete this assignment? It will be removed from rosters.')) return;

    try {
        const res = await fetch(`${API_BASE}/assignments/${assignId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Failed.');

        showToast(data.message, 'success');
        fetchAssignments();
    } catch (e) {
        showToast(e.message, 'error');
    }
};

// ── Review Submissions Modal Open & Controls ──
let currentAssignIdReview = null;
let currentMaxMarksReview = 100;

window.openSubmissionsModal = async function(assignId, title, maxMarks) {
    currentAssignIdReview = assignId;
    currentMaxMarksReview = maxMarks;

    document.getElementById('submissions-modal').classList.add('open');
    document.getElementById('review-assign-meta').textContent = `Assignment: "${title}" | Maximum marks: ${maxMarks}`;
    document.getElementById('publish-marks-btn').style.display = 'none';

    // Clear stats
    document.getElementById('stat-total-students').textContent = '…';
    document.getElementById('stat-total-submitted').textContent = '…';
    document.getElementById('stat-pending-evaluation').textContent = '…';
    document.getElementById('stat-average-score').textContent = '…';

    await fetchAssignmentStats(assignId);
    await fetchSubmissionsRoster(assignId);
};

window.closeSubmissionsModal = function() {
    document.getElementById('submissions-modal').classList.remove('open');
    currentAssignIdReview = null;
};

// ── Fetch assignment statistics ──
async function fetchAssignmentStats(assignId) {
    try {
        const res = await fetch(`${API_BASE}/assignments/${assignId}/stats`, { headers: getAuthHeaders() });
        if (res.ok) {
            const s = await res.json();
            document.getElementById('stat-total-students').textContent = s.total_students;
            document.getElementById('stat-total-submitted').textContent = s.total_submitted;
            document.getElementById('stat-pending-evaluation').textContent = s.pending_evaluation;
            document.getElementById('stat-average-score').textContent = s.average_score !== null ? `${s.average_score.toFixed(1)}%` : 'N/A';
        }
    } catch (e) {
        console.error('Failed to load stats', e);
    }
}

// ── Fetch assignment submissions roster ──
async function fetchSubmissionsRoster(assignId) {
    const tbody = document.querySelector('#submissions-table tbody');
    tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text-muted); text-align:center;"><i class="fas fa-spinner fa-spin"></i> Loading student roster…</td></tr>';

    try {
        // Fetch if marks are already published
        const listRes = await fetch(`${API_BASE}/assignments`, { headers: getAuthHeaders() });
        const listData = await listRes.json();
        const curAssign = listData.find(a => a.id === assignId);
        const isPublished = curAssign ? curAssign.marks_published : false;

        const res = await fetch(`${API_BASE}/assignments/${assignId}/submissions`, { headers: getAuthHeaders() });
        if (!res.ok) throw new Error('Failed to load submissions.');

        const roster = await res.json();
        tbody.innerHTML = '';

        if (roster.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text-muted); text-align:center;">No students enrolled in this class roster.</td></tr>';
            return;
        }

        // Show Publish Marks button if there are evaluated marks and not yet published
        const hasEvaluated = roster.some(r => r.status === 'evaluated');
        if (hasEvaluated && !isPublished) {
            document.getElementById('publish-marks-btn').style.display = 'block';
        }

        roster.forEach(r => {
            let fileCell = '<span style="color:var(--text-muted);">—</span>';
            if (r.document_id) {
                fileCell = `
                    <button class="act-btn" onclick="handleDocumentDownload(${r.document_id}, '${escapeHtml(r.filename)}')" title="Download: ${escapeHtml(r.filename)}">
                        <i class="fas fa-file-download" style="color:var(--primary-color);"></i> ${escapeHtml(r.filename).slice(0, 15)}…
                    </button>
                `;
            }

            let dateCell = '<span style="color:var(--text-muted);">Pending</span>';
            if (r.submitted_at) {
                const subDate = new Date(r.submitted_at).toLocaleDateString();
                const lateFlag = r.is_late ? ' <span style="color:#f87171; font-weight:700; font-size:0.65rem;">(LATE)</span>' : '';
                dateCell = `<span>${subDate}${lateFlag}</span>`;
            }

            // Evaluation Inputs
            let scoreInputHtml = '';
            let feedbackInputHtml = '';
            let actionCellHtml = '';

            if (r.status === 'submitted') {
                scoreInputHtml = `<input type="number" id="grade-score-${r.submission_id}" class="form-control" style="width:70px; padding:0.4rem; font-size:0.8rem; margin:0;" min="0" max="${currentMaxMarksReview}" placeholder="Score" required>`;
                feedbackInputHtml = `<input type="text" id="grade-feedback-${r.submission_id}" class="form-control" style="width:120px; padding:0.4rem; font-size:0.8rem; margin:0;" placeholder="Feedback">`;
                actionCellHtml = `
                    <button class="btn" style="padding:0.4rem 0.8rem; font-size:0.75rem; margin:0;" onclick="submitEvaluation(${r.submission_id})">
                        Evaluate
                    </button>
                `;
            } else if (r.status === 'evaluated') {
                scoreInputHtml = `<span style="font-weight:700; color:#34d399;">${r.marks}</span>`;
                feedbackInputHtml = `<span style="font-size:0.78rem; color:var(--text-muted);">${escapeHtml(r.feedback || '—')}</span>`;
                actionCellHtml = `<span style="font-size:0.75rem; color:var(--text-muted);"><i class="fas fa-check-circle" style="color:#10b981;"></i> Graded</span>`;
            } else {
                scoreInputHtml = '<span style="color:var(--text-muted);">—</span>';
                feedbackInputHtml = '<span style="color:var(--text-muted);">—</span>';
                actionCellHtml = '<span style="font-size:0.75rem; color:var(--text-muted); font-style:italic;">No submission</span>';
            }

            tbody.innerHTML += `
                <tr>
                    <td><strong>${escapeHtml(r.register_number)}</strong></td>
                    <td>${escapeHtml(r.student_name)}</td>
                    <td>${dateCell}</td>
                    <td>${fileCell}</td>
                    <td style="text-align:center;">${scoreInputHtml}</td>
                    <td>${feedbackInputHtml}</td>
                    <td>${actionCellHtml}</td>
                </tr>
            `;
        });
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="7" style="color:var(--error); text-align:center;">Failed to load roster.</td></tr>';
    }
}

// ── Submit grading evaluation ──
window.submitEvaluation = async function(subId) {
    const marksInput = document.getElementById(`grade-score-${subId}`);
    const feedbackInput = document.getElementById(`grade-feedback-${subId}`);
    if (!marksInput) return;

    const marks = marksInput.value;
    const feedback = feedbackInput ? feedbackInput.value.trim() : '';

    if (!marks || marks === '') {
        alert('Please enter a grade score.');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/assignments/evaluate/${subId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({ marks, feedback })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Failed.');

        showToast('Evaluation saved successfully!', 'success');
        // Refresh Roster & Stats
        await fetchAssignmentStats(currentAssignIdReview);
        await fetchSubmissionsRoster(currentAssignIdReview);
    } catch (e) {
        showToast(e.message, 'error');
    }
};

// ── Download student submission file via dynamic signed link ──
window.handleDocumentDownload = async function(docId, filename) {
    try {
        const res = await fetch(`${API_BASE}/documents/${docId}/download`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Failed to download.');

        const a = document.createElement('a');
        a.href = data.download_url;
        a.download = filename;
        a.target = '_blank';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    } catch (err) {
        showToast(err.message, 'error');
    }
};

// ── Publish Marks (Manual trigger) ──
window.publishAssignmentMarks = async function() {
    if (!currentAssignIdReview) return;
    if (!confirm('Are you sure you want to publish these grades officially to student Report Cards? All students will receive grades and push notifications instantly.')) return;

    const btn = document.getElementById('publish-marks-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Publishing…';

    try {
        const res = await fetch(`${API_BASE}/assignments/${currentAssignIdReview}/publish-marks`, {
            method: 'POST',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Failed to publish.');

        showToast(data.message || 'Grades published officially!', 'success');
        btn.style.display = 'none'; // Hide since already published
        fetchAssignments();
    } catch (e) {
        showToast(e.message, 'error');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-bullhorn"></i> Publish Grades to Report Cards';
    }
};

// ── Student Submission Modal ──
window.openSubmitModal = function(assignId, title, maxMarks, deadlineText) {
    document.getElementById('submit-modal').classList.add('open');
    clearSelectedFile();
    document.getElementById('submission-form').reset();
    document.getElementById('submit-assign-id').value = assignId;
    document.getElementById('student-submit-meta').textContent = `Assignment: "${title}" | Max Score: ${maxMarks} | Due: ${deadlineText}`;
    document.getElementById('submit-error').style.display = 'none';
};

window.closeSubmitModal = function() {
    document.getElementById('submit-modal').classList.remove('open');
};

// ── Dropzone file handlers ──
window.triggerFileInput = function() {
    document.getElementById('file-input').click();
};

window.handleFileSelect = function(e) {
    const files = e.target.files;
    if (files.length > 0) {
        const file = files[0];
        
        // Enforce 50MB file size limit before upload
        const limit = 50 * 1024 * 1024;
        if (file.size > limit) {
            alert('File size exceeds the 50MB limit.');
            clearSelectedFile();
            return;
        }

        selectedFile = file;
        document.getElementById('selected-file-name').textContent = file.name;
        document.getElementById('selected-file-badge').style.display = 'flex';
        document.getElementById('dropzone-text').textContent = 'File selected!';
    }
};

window.clearSelectedFile = function() {
    selectedFile = null;
    document.getElementById('file-input').value = '';
    document.getElementById('selected-file-badge').style.display = 'none';
    document.getElementById('dropzone-text').textContent = 'Click or drag assignment file (PDF, DOCX) here';
};

// ── Student Submit Assignment Action ──
window.handleStudentSubmit = async function(e) {
    e.preventDefault();

    const assignId = document.getElementById('submit-assign-id').value;
    const errDiv = document.getElementById('submit-error');
    const btn = document.getElementById('submit-btn');

    errDiv.style.display = 'none';

    if (!selectedFile) {
        errDiv.style.display = 'block';
        errDiv.textContent = 'Please select a file to submit.';
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting…';

    try {
        // 1. Fetch Student profile to resolve class_id
        const profileRes = await fetch(`${API_BASE}/student/profile`, { headers: getAuthHeaders() });
        if (!profileRes.ok) throw new Error('Could not verify class roster enrollment.');
        const profile = await profileRes.json();
        const classId = profile.class_id;

        if (!classId) throw new Error('You are not assigned to a class roster.');

        // 2. Fetch Assignment Detail to resolve title for file upload
        const detailRes = await fetch(`${API_BASE}/assignments/${assignId}`, { headers: getAuthHeaders() });
        const detail = await detailRes.json();
        const title = `Submission - ${detail.title}`;

        // 3. Upload File to Document management portal via FormData
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('title', title);
        formData.append('description', `Student assignment file submission for assignment id: ${assignId}`);
        formData.append('category', 'assignment');
        formData.append('visibility', 'class');
        formData.append('target_class_id', classId);

        const uploadRes = await fetch(`${API_BASE}/documents`, {
            method: 'POST',
            headers: getAuthHeaders(), // Boundary auto-resolved
            body: formData
        });
        const uploadData = await uploadRes.json();
        if (!uploadRes.ok) throw new Error(uploadData.message || 'File upload failed.');

        const document_id = uploadData.document_id;

        // 4. Submit to Assignments System
        const submitRes = await fetch(`${API_BASE}/assignments/${assignId}/submit`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({ document_id })
        });
        const submitData = await submitRes.json();
        if (!submitRes.ok) throw new Error(submitData.message || 'Submission linking failed.');

        showToast('Assignment submitted successfully!', 'success');
        closeSubmitModal();
        fetchAssignments();
    } catch (err) {
        errDiv.style.display = 'block';
        errDiv.textContent = err.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Submit Assignment';
    }
};

// ── Utility Toast and escapes ──
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}"></i> ${message}`;
    container.appendChild(toast);

    setTimeout(() => toast.classList.add('visible'), 50);

    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 400);
    }, 4500);
}

function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// ── Initial Setup ──
document.addEventListener('DOMContentLoaded', () => {
    renderSidebar();
    fetchAssignments();
});
