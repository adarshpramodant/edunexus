// ─────────────────────────────────────────────────────────────────────────────
// EduNexus — Faculty Class Workspace JS  (Attendance v2 + Marks v2)
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:'
    ? 'http://localhost:5000/api'
    : 'https://edunexus-quw3.onrender.com/api';
const API_URL = `${API_BASE}/faculty`;
const token    = localStorage.getItem('token');
const userRole = localStorage.getItem('role');

if (!token || userRole !== 'faculty') {
    window.location.href = 'login.html';
}

function getAuthHeaders() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

const urlParams = new URLSearchParams(window.location.search);
const classId   = urlParams.get('class_id');
if (!classId) window.location.href = 'faculty_dashboard.html';

// ── Global cache ──────────────────────────────────────────────────────────────
let currentClassInfo = null;
let currentStudents  = [];
let currentSubjects  = [];
let allFaculty       = [];
let attCurrentConflict = false;

// ── Generic helpers ───────────────────────────────────────────────────────────
function switchTab(tabId, btn) {
    document.querySelectorAll('.section-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    btn.classList.add('active');
}

function showMessage(elementId, message, isError = false) {
    const el = document.getElementById(elementId);
    el.textContent = message;
    el.className = `message-container ${isError ? 'message-error' : 'message-success'}`;
    el.style.display = 'block';
    setTimeout(() => { el.style.display = 'none'; el.className = 'message-container'; }, 5000);
}

// ── Toast ─────────────────────────────────────────────────────────────────────
let _toastTimer = null;
function showToast(msg, type = 'success') {
    const toast  = document.getElementById('ws-toast');
    const msgEl  = document.getElementById('ws-toast-msg');
    const iconEl = document.getElementById('ws-toast-icon');
    const icons  = { success: 'fa-check-circle', error: 'fa-exclamation-circle', warning: 'fa-exclamation-triangle' };
    toast.className  = `show ${type}`;
    msgEl.textContent = msg;
    iconEl.className  = `fas ${icons[type] || 'fa-info-circle'}`;
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => { toast.className = type; }, 3800);
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function initWorkspace() {
    try {
        const res1 = await fetch(`${API_URL}/class/${classId}`, { headers: getAuthHeaders() });
        if (!res1.ok) throw new Error('Could not load class.');
        currentClassInfo = await res1.json();

        const roles       = currentClassInfo.roles || [];
        const primaryRole = currentClassInfo.primary_role || currentClassInfo.class_role || '';
        currentClassInfo.resolvedRoles       = roles;
        currentClassInfo.resolvedPrimaryRole = primaryRole;

        const isLead = roles.includes('class_teacher') || roles.includes('vice_class_teacher');

        document.getElementById('class-subtitle').innerText =
            `${currentClassInfo.department} | Semester ${currentClassInfo.semester} | Section ${currentClassInfo.section}`;

        const roleLabel = primaryRole
            ? primaryRole.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) + ' (Primary)'
            : 'Assigned Faculty';
        const secondaryRoles = roles.filter(r => r !== primaryRole)
            .map(r => r.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()));
        document.getElementById('role-badge').innerText = secondaryRoles.length
            ? `Role: ${roleLabel} + ${secondaryRoles.join(', ')}` : `Role: ${roleLabel}`;

        if (isLead) {
            document.getElementById('tab-subjects-btn').style.display = 'inline-block';
            fetchAllFaculty();
        }

        await fetchStudents();
        await fetchSubjects();
    } catch (err) {
        console.error(err);
        alert('Failed to initialize workspace.');
    }
}

async function fetchStudents() {
    const res = await fetch(`${API_URL}/class/${classId}/students`, { headers: getAuthHeaders() });
    currentStudents = await res.json();
    const tbody = document.querySelector('#students-table tbody');
    tbody.innerHTML = '';
    currentStudents.forEach(stu => {
        tbody.innerHTML += `<tr><td>${stu.register_number}</td><td>${stu.name}</td><td>${stu.email}</td></tr>`;
    });
}

async function fetchSubjects() {
    const res = await fetch(`${API_URL}/class/${classId}/subjects`, { headers: getAuthHeaders() });
    currentSubjects = await res.json();

    // Attendance subject dropdown
    const attOpts = '<option value="" disabled selected>Subject</option>' +
        currentSubjects.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
    document.getElementById('att-subject').innerHTML = attOpts;

    // Marks entry dropdown
    const marksOpts = '<option value="" disabled selected>Subject</option>' +
        currentSubjects.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
    document.getElementById('marks-subject').innerHTML = marksOpts;

    // Summary dropdown
    const summaryOpts = '<option value="" disabled selected>Subject</option>' +
        currentSubjects.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
    document.getElementById('summary-subject').innerHTML = summaryOpts;

    const roles  = currentClassInfo.resolvedRoles || [];
    const isLead = roles.includes('class_teacher') || roles.includes('vice_class_teacher');

    if (isLead) {
        const tbody = document.querySelector('#workspace-subjects-table tbody');
        tbody.innerHTML = '';
        let facultyOpts = '<option value="">Unassigned</option>';
        allFaculty.forEach(f => { facultyOpts += `<option value="${f.id}">${f.name}</option>`; });

        currentSubjects.forEach(s => {
            let sel = `<select class="form-control form-select assign-teacher-sel" data-subject-id="${s.id}" style="padding:0.5rem;">${facultyOpts}</select>`;
            sel = sel.replace(`value="${s.teacher_id}"`, `value="${s.teacher_id}" selected`);
            let actionBtn = `<button class="btn" onclick="saveAssignment(${s.id})" style="padding:0.4rem 0.8rem;height:auto;">Assign</button>`;
            if (s.assignment_id) {
                actionBtn += ` <button class="btn btn-warning" onclick="removeAssignment(${s.assignment_id})" style="padding:0.4rem 0.8rem;height:auto;background:var(--error);"><i class="fas fa-trash"></i></button>`;
            }
            tbody.innerHTML += `<tr><td>${s.name}</td><td>${s.code || ''}</td><td>${sel}</td><td style="display:flex;gap:0.5rem;">${actionBtn}</td></tr>`;
        });
    }
}

async function fetchAllFaculty() {
    const res  = await fetch(`${API_URL}/all-faculty`, { headers: getAuthHeaders() });
    allFaculty = await res.json();
}

// ─────────────────────────────────────────────────────────────────────────────
// ATTENDANCE v2
// ─────────────────────────────────────────────────────────────────────────────

function buildAttRow(stu, idx, currentStatus) {
    const statuses = [
        { code: 'P', title: 'Present' }, { code: 'AB', title: 'Absent' },
        { code: 'SR', title: 'Sick Room' }, { code: 'DL', title: 'Duty Leave' }
    ];
    const btns = statuses.map(s => {
        const active = currentStatus === s.code ? `active-${s.code}` : '';
        return `<button type="button" class="status-btn ${active}" data-code="${s.code}" title="${s.title}" onclick="setStudentStatus(this,'${s.code}')">${s.code}</button>`;
    }).join('');
    return `<tr data-student-id="${stu.id}">
        <td style="color:var(--text-muted);font-size:0.78rem;">${idx}</td>
        <td class="reg-col">${stu.register_number}</td>
        <td class="name-col">${stu.name}</td>
        <td><div class="status-btn-group">${btns}</div></td>
    </tr>`;
}

function setStudentStatus(btn, code) {
    const group = btn.closest('.status-btn-group');
    group.querySelectorAll('.status-btn').forEach(b => { b.className = 'status-btn'; });
    btn.classList.add(`active-${code}`);
    updateSummaryPills();
}

function markAll(code) {
    document.querySelectorAll('#att-tbody .status-btn-group').forEach(group => {
        group.querySelectorAll('.status-btn').forEach(b => { b.className = 'status-btn'; });
        const target = group.querySelector(`[data-code="${code}"]`);
        if (target) target.classList.add(`active-${code}`);
    });
    updateSummaryPills();
}

function updateSummaryPills() {
    const counts = { P: 0, AB: 0, SR: 0, DL: 0 };
    document.querySelectorAll('#att-tbody tr').forEach(row => {
        const active = row.querySelector('.status-btn[class*="active-"]');
        if (active && counts[active.dataset.code] !== undefined) counts[active.dataset.code]++;
    });
    ['P', 'AB', 'SR', 'DL'].forEach(c => {
        const el = document.getElementById(`cnt-${c}`);
        if (el) el.textContent = counts[c];
    });
}

async function fetchAttendanceSheet() {
    const date = document.getElementById('att-date').value;
    const hour = document.getElementById('att-hour').value;
    const subjectId = document.getElementById('att-subject').value;
    if (!date || !hour || !subjectId) { showToast('Please select date, hour and subject.', 'warning'); return; }

    try {
        const res  = await fetch(`${API_URL}/attendance?class_id=${classId}&date=${date}&hour=${hour}&subject_id=${subjectId}`, { headers: getAuthHeaders() });
        const data = await res.json();
        const existingAtt  = data.attendance   || {};
        const sessionMeta  = data.session_meta || null;
        const conflict     = data.conflict      || null;
        attCurrentConflict = !!conflict;

        const banner = document.getElementById('att-conflict-banner');
        if (conflict) {
            document.getElementById('att-conflict-msg').textContent = `⚠ Attendance for "${conflict.subject_name}" already exists in this slot. Saving will overwrite it.`;
            banner.classList.add('show');
        } else {
            banner.classList.remove('show');
        }

        const metaBar = document.getElementById('att-meta-bar');
        if (sessionMeta && sessionMeta.updated_by) {
            document.getElementById('meta-updated-by').textContent = sessionMeta.updated_by;
            document.getElementById('meta-updated-at').textContent = sessionMeta.updated_at ? new Date(sessionMeta.updated_at).toLocaleString() : '—';
            metaBar.style.display = 'flex';
        } else {
            metaBar.style.display = 'none';
        }

        const tbody = document.getElementById('att-tbody');
        tbody.innerHTML = '';
        currentStudents.forEach((stu, i) => {
            tbody.innerHTML += buildAttRow(stu, i + 1, existingAtt[stu.id] || '');
        });
        updateSummaryPills();
        document.getElementById('att-sheet-section').style.display = 'block';
        showToast(Object.keys(existingAtt).length === 0 ? 'New session loaded. Mark attendance below.' : 'Existing data loaded. Edit and save.', 'success');
    } catch (err) {
        console.error(err);
        showToast('Failed to load attendance. Check server.', 'error');
    }
}

async function saveAttendanceV2(forceOverwrite = false) {
    const date = document.getElementById('att-date').value;
    const hour = document.getElementById('att-hour').value;
    const subjectId = document.getElementById('att-subject').value;
    if (!date || !hour || !subjectId) { showToast('Session parameters missing.', 'error'); return; }

    const attendanceArr = [];
    let missingCount = 0;
    document.querySelectorAll('#att-tbody tr').forEach(row => {
        const stuId  = row.getAttribute('data-student-id');
        const active = row.querySelector('.status-btn[class*="active-"]');
        if (!active) missingCount++;
        else attendanceArr.push({ student_id: parseInt(stuId), status: active.dataset.code });
    });
    if (missingCount > 0) { showToast(`${missingCount} student(s) have no status. Mark all students.`, 'error'); return; }
    if (attendanceArr.length === 0) { showToast('No students in the list.', 'error'); return; }

    const saveBtn = document.getElementById('btn-save-att');
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…';

    try {
        const res  = await fetch(`${API_URL}/attendance`, {
            method: 'POST', headers: getAuthHeaders(),
            body: JSON.stringify({ class_id: parseInt(classId), date, hour: parseInt(hour), subject_id: parseInt(subjectId), attendance: attendanceArr, force_overwrite: forceOverwrite || attCurrentConflict })
        });
        const data = await res.json();
        if (res.status === 409) {
            document.getElementById('att-conflict-msg').textContent = `⚠ ${data.message}`;
            document.getElementById('att-conflict-banner').classList.add('show');
            showToast('Conflict detected. See banner above.', 'warning');
        } else if (res.ok) {
            document.getElementById('att-conflict-banner').classList.remove('show');
            attCurrentConflict = false;
            showToast(data.message, 'success');
            const ind = document.getElementById('att-save-indicator');
            ind.textContent = '✓ Saved at ' + new Date().toLocaleTimeString();
            ind.style.opacity = '1';
            setTimeout(() => { ind.style.opacity = '0'; }, 4000);
            fetchAttendanceSheet();
        } else {
            showToast(data.message || 'Error saving attendance.', 'error');
        }
    } catch (err) {
        showToast('Network error. Could not save.', 'error');
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="fas fa-save"></i> Save Attendance';
    }
}

async function openHistoryModal() {
    const modal   = document.getElementById('att-history-modal');
    const loading = document.getElementById('hist-loading');
    const table   = document.getElementById('hist-table');
    const empty   = document.getElementById('hist-empty');
    const tbody   = document.getElementById('hist-tbody');
    modal.classList.add('open');
    loading.style.display = 'block';
    table.style.display   = 'none';
    empty.style.display   = 'none';
    tbody.innerHTML       = '';

    const date = document.getElementById('att-date').value;
    const hour = document.getElementById('att-hour').value;
    const subjectId = document.getElementById('att-subject').value;
    try {
        const res  = await fetch(`${API_URL}/attendance/history?class_id=${classId}&date=${date}&hour=${hour}&subject_id=${subjectId}`, { headers: getAuthHeaders() });
        const logs = await res.json();
        loading.style.display = 'none';
        if (!Array.isArray(logs) || logs.length === 0) { empty.style.display = 'block'; return; }
        const chip = code => code ? `<span class="schip schip-${code}">${code}</span>` : `<span class="schip schip-null">New</span>`;
        logs.forEach(log => {
            const dt = log.changed_at ? new Date(log.changed_at).toLocaleString() : '—';
            tbody.innerHTML += `<tr><td>${log.student}</td><td style="font-family:monospace;font-size:0.75rem;color:var(--text-muted);">${log.register_number}</td><td>${chip(log.previous_status)}</td><td>${chip(log.new_status)}</td><td>${log.changed_by}</td><td style="color:var(--text-muted);font-size:0.78rem;">${dt}</td></tr>`;
        });
        table.style.display = 'table';
    } catch (err) {
        loading.textContent = 'Failed to load history.';
    }
}

function closeHistoryModal() {
    document.getElementById('att-history-modal').classList.remove('open');
}
document.addEventListener('click', e => {
    const modal = document.getElementById('att-history-modal');
    if (e.target === modal) closeHistoryModal();
});

// ─────────────────────────────────────────────────────────────────────────────
// MARKS v2
// ─────────────────────────────────────────────────────────────────────────────

function switchMarksTab(tab, btn) {
    document.querySelectorAll('.marks-tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('mtab-entry').style.display   = tab === 'entry'   ? 'block' : 'none';
    document.getElementById('mtab-summary').style.display = tab === 'summary' ? 'block' : 'none';
}

// When subject changes in entry mode, reset the sheet
function onMarksSubjectChange() {
    document.getElementById('marks-sheet-section').style.display = 'none';
    document.getElementById('marks-meta-bar').style.display     = 'none';
}

/** Highlight mark input based on percentage vs max */
function highlightMarkInput(input, max) {
    const val = parseFloat(input.value);
    input.classList.remove('mark-high', 'mark-low');
    if (isNaN(val) || input.value === '') return;
    const pct = (val / max) * 100;
    if (pct >= 75) input.classList.add('mark-high');
    else if (pct < 50) input.classList.add('mark-low');
}

/** Grade class name helper */
function gradeClass(g) {
    const map = { 'A+': 'Ap', 'A': 'A', 'B+': 'Bp', 'B': 'B', 'C': 'C', 'D': 'D' };
    return `grade-badge grade-${map[g] || 'D'}`;
}

/** Load student list with existing marks pre-filled */
async function fetchMarksSheet() {
    const subjectId = document.getElementById('marks-subject').value;
    const markType  = document.getElementById('marks-type').value;
    const markName  = document.getElementById('marks-name').value.trim();
    const maxMarks  = parseFloat(document.getElementById('marks-max').value) || 100;

    if (!subjectId)  { showToast('Please select a subject.', 'warning'); return; }
    if (!markType)   { showToast('Please select a mark type.', 'warning'); return; }
    if (!markName)   { showToast('Please enter a mark name (e.g. Internal 1).', 'warning'); return; }
    if (!currentStudents.length) { showToast('No students loaded yet.', 'warning'); return; }

    // Update UI labels
    document.getElementById('marks-max-label').textContent = `/ ${maxMarks}`;
    document.getElementById('marks-range-note').textContent = `Range: 0 – ${maxMarks}`;

    // Fetch existing marks
    let existingMap = {};
    try {
        const res  = await fetch(`${API_URL}/marks?subject_id=${subjectId}&mark_type=${encodeURIComponent(markType)}&mark_name=${encodeURIComponent(markName)}`, { headers: getAuthHeaders() });
        if (res.ok) existingMap = await res.json();
    } catch (e) { console.warn('Could not fetch existing marks:', e); }

    const hasExisting = Object.keys(existingMap).length > 0;
    const metaBar = document.getElementById('marks-meta-bar');
    const cntEl   = document.getElementById('marks-meta-count');
    if (hasExisting) {
        metaBar.style.display = 'flex';
        cntEl.textContent     = `${Object.keys(existingMap).length} existing record(s) will be updated.`;
    } else {
        metaBar.style.display = 'none';
    }

    // Build rows
    const tbody = document.getElementById('marks-tbody');
    tbody.innerHTML = '';
    currentStudents.forEach((stu, i) => {
        const existing = existingMap[stu.id];
        const prevVal  = existing ? existing.marks : null;
        const prevHtml = prevVal !== null
            ? `<span style="color:var(--text-muted); font-size:0.8rem;">${prevVal}</span>`
            : `<span style="color:var(--border-color); font-size:0.78rem;">—</span>`;

        // If existing, pre-fill input
        const inputVal = prevVal !== null ? prevVal : '';

        tbody.innerHTML += `<tr data-student-id="${stu.id}">
            <td style="color:var(--text-muted);font-size:0.78rem;">${i + 1}</td>
            <td class="reg-col">${stu.register_number}</td>
            <td class="name-col">${stu.name}</td>
            <td>
                <input type="number" step="0.01" min="0" max="${maxMarks}"
                    class="mark-input"
                    value="${inputVal}"
                    placeholder="—"
                    oninput="highlightMarkInput(this, ${maxMarks})">
            </td>
            <td class="prev-col">${prevHtml}</td>
        </tr>`;
    });

    // Apply highlight to pre-filled inputs
    document.querySelectorAll('#marks-tbody .mark-input').forEach(inp => {
        if (inp.value !== '') highlightMarkInput(inp, maxMarks);
    });

    document.getElementById('marks-sheet-section').style.display = 'block';
    showToast(hasExisting ? 'Existing marks loaded. Edit to update.' : 'New mark sheet ready. Enter values and save.', 'success');
}

/** Fill all empty inputs with the given value */
function fillAll() {
    const fillVal  = document.getElementById('fill-value').value;
    const maxMarks = parseFloat(document.getElementById('marks-max').value) || 100;
    if (fillVal === '' || isNaN(parseFloat(fillVal))) { showToast('Enter a fill value first.', 'warning'); return; }
    const fv = parseFloat(fillVal);
    if (fv < 0 || fv > maxMarks) { showToast(`Value must be between 0 and ${maxMarks}.`, 'error'); return; }

    document.querySelectorAll('#marks-tbody .mark-input').forEach(inp => {
        if (inp.value === '') {
            inp.value = fv;
            highlightMarkInput(inp, maxMarks);
        }
    });
}

/** Save the marks sheet */
async function saveMarksV2() {
    const subjectId = document.getElementById('marks-subject').value;
    const markType  = document.getElementById('marks-type').value;
    const markName  = document.getElementById('marks-name').value.trim();
    const maxMarks  = parseFloat(document.getElementById('marks-max').value) || 100;

    if (!subjectId || !markType || !markName) {
        showToast('Subject, type and name are required.', 'error'); return;
    }

    const marksArr = [];
    let hasValue   = false;
    let invalid    = false;

    document.querySelectorAll('#marks-tbody tr').forEach(row => {
        const stuId = row.getAttribute('data-student-id');
        const inp   = row.querySelector('.mark-input');
        const raw   = inp.value.trim();

        if (raw === '' || raw === null) {
            marksArr.push({ student_id: parseInt(stuId), marks: '' }); // blank = skip
            return;
        }
        const val = parseFloat(raw);
        if (isNaN(val)) { invalid = true; return; }
        if (val < 0 || val > maxMarks) { invalid = true; return; }
        marksArr.push({ student_id: parseInt(stuId), marks: val });
        hasValue = true;
    });

    if (invalid) { showToast(`Invalid values found. Marks must be numeric and between 0–${maxMarks}.`, 'error'); return; }
    if (!hasValue) { showToast('No marks entered. Please fill at least one student.', 'error'); return; }

    const saveBtn = document.getElementById('btn-save-marks');
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…';

    try {
        const res  = await fetch(`${API_URL}/marks`, {
            method: 'POST', headers: getAuthHeaders(),
            body: JSON.stringify({ subject_id: parseInt(subjectId), mark_type: markType, mark_name: markName, max_marks: maxMarks, marks: marksArr })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
            const ind = document.getElementById('marks-save-indicator');
            ind.textContent = `✓ Saved at ${new Date().toLocaleTimeString()}`;
            ind.style.opacity = '1';
            setTimeout(() => { ind.style.opacity = '0'; }, 4000);
            // Refresh to show updated prev. values
            fetchMarksSheet();
        } else {
            showToast(data.message || 'Error saving marks.', 'error');
        }
    } catch (err) {
        showToast('Network error. Could not save marks.', 'error');
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="fas fa-save"></i> Save Marks';
    }
}

/** Load class summary for a subject (all components × all students) */
async function loadMarksSummary() {
    const subjectId = document.getElementById('summary-subject').value;
    if (!subjectId) { showToast('Please select a subject.', 'warning'); return; }

    const summarySection = document.getElementById('summary-section');
    const emptyEl        = document.getElementById('summary-empty');
    summarySection.style.display = 'none';
    emptyEl.style.display        = 'none';

    try {
        const res  = await fetch(`${API_URL}/marks/summary?subject_id=${subjectId}&class_id=${classId}`, { headers: getAuthHeaders() });
        const data = await res.json();

        if (!data.components || data.components.length === 0) {
            emptyEl.style.display = 'block';
            return;
        }

        const components = data.components; // [{mark_type, mark_name}]
        const students   = data.students;   // [{...}]

        // Build dynamic header: Reg | Name | [comp1] [comp2] … | Total | Avg | Grade
        const thead = document.getElementById('summary-head');
        const tbody = document.getElementById('summary-tbody');

        let headerHtml = `<tr>
            <th>Reg. No</th>
            <th>Name</th>`;
        components.forEach(c => {
            headerHtml += `<th title="${c.mark_type}">${c.mark_type}<br><small style="font-weight:400;text-transform:none;">${c.mark_name}</small></th>`;
        });
        headerHtml += `<th>Total</th><th>Average</th><th>Grade</th></tr>`;
        thead.innerHTML = headerHtml;

        tbody.innerHTML = '';
        students.forEach(s => {
            let row = `<tr>
                <td style="font-family:monospace; font-size:0.78rem; color:var(--text-muted);">${s.register_number}</td>
                <td style="font-weight:600;">${s.student_name}</td>`;
            components.forEach(c => {
                const key = `${c.mark_type}::${c.mark_name}`;
                const val = s.marks[key];
                if (val !== undefined) {
                    const colorClass = val >= 75 ? 'style="color:#10b981;font-weight:700;"' : val < 50 ? 'style="color:#ef4444;font-weight:700;"' : '';
                    row += `<td ${colorClass}>${val}</td>`;
                } else {
                    row += `<td style="color:var(--border-color);">—</td>`;
                }
            });
            row += `<td style="font-weight:700;">${s.total.toFixed(1)}</td>`;
            row += `<td>${s.average}</td>`;
            row += `<td><span class="${gradeClass(s.grade)}">${s.grade}</span></td>`;
            row += '</tr>';
            tbody.innerHTML += row;
        });

        summarySection.style.display = 'block';
    } catch (err) {
        console.error(err);
        showToast('Failed to load summary.', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SUBJECTS & ASSIGNMENT
// ─────────────────────────────────────────────────────────────────────────────

document.getElementById('create-subject-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('new-sub-name').value;
    const code = document.getElementById('new-sub-code').value;
    try {
        const res  = await fetch(`${API_URL}/subjects`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ class_id: parseInt(classId), name, code }) });
        const data = await res.json();
        if (res.ok) {
            showMessage('subject-create-msg', data.message);
            document.getElementById('new-sub-name').value = '';
            document.getElementById('new-sub-code').value = '';
            fetchSubjects();
        } else showMessage('subject-create-msg', data.message, true);
    } catch (err) { showMessage('subject-create-msg', 'Server error', true); }
});

async function saveAssignment(subjectId) {
    const sel = document.querySelector(`.assign-teacher-sel[data-subject-id="${subjectId}"]`);
    const tid = sel.value;
    if (!tid) return alert('Select a teacher first');
    try {
        const res = await fetch(`${API_URL}/assign-subject`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ subject_id: subjectId, teacher_id: parseInt(tid), class_id: parseInt(classId) }) });
        const data = await res.json();
        if (res.ok) fetchSubjects();
        else alert(data.message);
    } catch (err) { console.error(err); }
}

async function removeAssignment(assignmentId) {
    if (!confirm('Remove this teacher from the subject?')) return;
    try {
        const res = await fetch(`${API_URL}/assign-subject/${assignmentId}`, { method: 'DELETE', headers: getAuthHeaders() });
        if (res.ok) fetchSubjects();
        else { const d = await res.json(); alert(d.message); }
    } catch (err) { console.error(err); }
}

// ─────────────────────────────────────────────────────────────────────────────
// TIMETABLE SYSTEM
// ─────────────────────────────────────────────────────────────────────────────

const DAYS  = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const HOURS = [1, 2, 3, 4, 5, 6, 7, 8];

async function loadTimetable() {
    const container = document.getElementById('tt-grid-container');
    const roles     = currentClassInfo.resolvedRoles || [];
    const isLead    = roles.includes('class_teacher') || roles.includes('vice_class_teacher');
    const todayName = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][new Date().getDay()];

    document.getElementById('tt-role-note').textContent = isLead
        ? 'You have edit access. Changes auto-save on selection.'
        : 'Read-only view. Only Class/Vice-Class Teachers can edit.';

    try {
        const res  = await fetch(`${API_URL}/timetable/${classId}`, { headers: getAuthHeaders() });
        const data = await res.json();

        const subjectOptions = '<option value="">— Empty —</option>' +
            currentSubjects.map(s => `<option value="${s.id}">${s.name} (${s.code || '—'})</option>`).join('');

        let html = '<table><thead><tr><th>Day \\ Hour</th>';
        HOURS.forEach(h => { html += `<th>Hour ${h}</th>`; });
        html += '</tr></thead><tbody>';

        DAYS.forEach(day => {
            const isToday = day === todayName;
            html += `<tr><td class="day-label${isToday ? ' today-col' : ''}">${day}${isToday ? ' <span style="color:var(--primary-color);font-size:0.7rem;">▶ Today</span>' : ''}</td>`;
            HOURS.forEach(hour => {
                const slot    = data[day]?.[hour];
                const cellCls = isToday ? 'today-col' : '';
                if (isLead) {
                    let opts = subjectOptions.replace(`value="${slot?.subject_id}"`, `value="${slot?.subject_id}" selected`);
                    html += `<td class="${cellCls}">
                        <select class="tt-select" data-day="${day}" data-hour="${hour}" onchange="saveTimetableSlot(this)">${opts}</select>
                        ${slot ? `<div style="font-size:0.68rem;color:var(--text-muted);margin-top:2px;">${slot.teacher_name || ''}</div>` : ''}
                    </td>`;
                } else {
                    if (slot) html += `<td class="${cellCls}"><div class="tt-readonly-cell"><strong>${slot.subject_name || '—'}</strong><small>${slot.teacher_name || ''}</small></div></td>`;
                    else      html += `<td class="${cellCls}"><span style="color:var(--border-color);">—</span></td>`;
                }
            });
            html += '</tr>';
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<p style="color:var(--error);margin-top:1rem;">Failed to load timetable.</p>`;
    }
}

async function saveTimetableSlot(selectEl) {
    const day        = selectEl.dataset.day;
    const hour       = parseInt(selectEl.dataset.hour);
    const subject_id = selectEl.value ? parseInt(selectEl.value) : null;
    const statusEl   = document.getElementById('tt-save-status');
    try {
        if (subject_id) {
            await fetch(`${API_URL}/timetable`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ class_id: parseInt(classId), day, hour, subject_id }) });
        } else {
            await fetch(`${API_URL}/timetable`, { method: 'DELETE', headers: getAuthHeaders(), body: JSON.stringify({ class_id: parseInt(classId), day, hour }) });
        }
        statusEl.textContent = '✓ Saved';
        statusEl.style.opacity = '1';
        setTimeout(() => { statusEl.style.opacity = '0'; }, 2000);
        await loadTimetable();
    } catch (e) { console.error('Timetable save error:', e); }
}

// ─────────────────────────────────────────────────────────────────────────────
// EXCEL/CSV IMPORT & EXPORT TEMPLATES (SheetJS)
// ─────────────────────────────────────────────────────────────────────────────

/** Marks Template Downloader */
window.downloadMarksTemplate = function() {
    if (!currentStudents.length) {
        showToast("Please load the student list first.", "warning");
        return;
    }
    const markType = document.getElementById('marks-type').value || 'Marks';
    const markName = document.getElementById('marks-name').value.trim() || 'Component';
    const maxMarks = parseFloat(document.getElementById('marks-max').value) || 100;
    
    const rows = [
        ["Register Number", "Student Name", `${markType} - ${markName} (Max: ${maxMarks})`]
    ];
    
    currentStudents.forEach(stu => {
        // Retrieve current score from UI if already filled
        let currentVal = "";
        const tr = document.querySelector(`#marks-tbody tr[data-student-id="${stu.id}"]`);
        if (tr) {
            const input = tr.querySelector('.mark-input');
            if (input && input.value !== '') currentVal = parseFloat(input.value);
        }
        rows.push([stu.register_number, stu.name, currentVal]);
    });
    
    try {
        const worksheet = XLSX.utils.aoa_to_sheet(rows);
        const workbook = XLSX.utils.book_new();
        XLSX.book_append_sheet(workbook, worksheet, "Marks Sheet");
        
        const safeName = markName.replace(/[^a-z0-9]/gi, '_').toLowerCase();
        const fileName = `Marks_Template_${markType}_${safeName}.xlsx`;
        XLSX.writeFile(workbook, fileName);
        showToast("Marks template downloaded.", "success");
    } catch (e) {
        console.error(e);
        showToast("Failed to generate marks template.", "error");
    }
};

/** Marks Excel/CSV Uploader & Auto-Fill */
window.importMarksFromFile = function(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    if (!currentStudents.length) {
        showToast("Please load the student sheet first.", "warning");
        event.target.value = "";
        return;
    }
    
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const data = new Uint8Array(e.target.result);
            const workbook = XLSX.read(data, { type: 'array' });
            const sheetName = workbook.SheetNames[0];
            const worksheet = workbook.Sheets[sheetName];
            const jsonData = XLSX.utils.sheet_to_json(worksheet, { defval: "" });
            
            if (!jsonData.length) {
                showToast("The uploaded file is empty.", "error");
                return;
            }
            
            // Detect headers / columns
            let regKey = null;
            let markKey = null;
            
            const sampleRow = jsonData[0];
            const keys = Object.keys(sampleRow);
            
            for (const k of keys) {
                const kl = k.toLowerCase().replace(/[^a-z0-9]/g, '');
                if (kl.includes('reg') || kl.includes('roll') || kl.includes('id') || kl.includes('adm')) {
                    regKey = k;
                }
                if (kl.includes('mark') || kl.includes('score') || kl.includes('grade') || kl.includes('val')) {
                    markKey = k;
                }
            }
            
            // Fallbacks
            if (!regKey && keys.length > 0) regKey = keys[0];
            if (!markKey) {
                if (keys.length > 2) markKey = keys[2];
                else if (keys.length > 1) markKey = keys[1];
            }
            
            if (!regKey || !markKey) {
                showToast("Could not determine student register or marks columns in spreadsheet.", "error");
                return;
            }
            
            let matchedCount = 0;
            const maxMarks = parseFloat(document.getElementById('marks-max').value) || 100;
            const rows = document.querySelectorAll('#marks-tbody tr');
            
            rows.forEach(tr => {
                const regNo = tr.querySelector('.reg-col').textContent.trim();
                const input = tr.querySelector('.mark-input');
                
                // Match register number
                const matchedRow = jsonData.find(row => {
                    const rowReg = String(row[regKey] || '').trim();
                    return rowReg.toLowerCase() === regNo.toLowerCase();
                });
                
                if (matchedRow) {
                    const val = parseFloat(matchedRow[markKey]);
                    if (!isNaN(val)) {
                        input.value = val;
                        highlightMarkInput(input, maxMarks);
                        matchedCount++;
                    }
                }
            });
            
            showToast(`Auto-filled marks for ${matchedCount} out of ${rows.length} students.`, "success");
        } catch (err) {
            console.error(err);
            showToast("Failed to parse file. Verify file format.", "error");
        } finally {
            event.target.value = "";
        }
    };
    reader.readAsArrayBuffer(file);
};

/** Attendance Template Downloader */
window.downloadAttendanceTemplate = function() {
    if (!currentStudents.length) {
        showToast("Please load the student list first.", "warning");
        return;
    }
    const date = document.getElementById('att-date').value || new Date().toISOString().split('T')[0];
    const hour = document.getElementById('att-hour').value || '1';
    
    const rows = [
        ["Register Number", "Student Name", "Attendance Status (P / AB / SR / DL)"]
    ];
    
    currentStudents.forEach(stu => {
        let currentStatus = "P"; // default to Present
        const tr = document.querySelector(`#att-tbody tr[data-student-id="${stu.id}"]`);
        if (tr) {
            const active = tr.querySelector('.status-btn[class*="active-"]');
            if (active) currentStatus = active.dataset.code;
        }
        rows.push([stu.register_number, stu.name, currentStatus]);
    });
    
    try {
        const worksheet = XLSX.utils.aoa_to_sheet(rows);
        const workbook = XLSX.utils.book_new();
        XLSX.book_append_sheet(workbook, worksheet, "Attendance Sheet");
        
        const fileName = `Attendance_Template_${date}_hour_${hour}.xlsx`;
        XLSX.writeFile(workbook, fileName);
        showToast("Attendance template downloaded.", "success");
    } catch (e) {
        console.error(e);
        showToast("Failed to generate attendance template.", "error");
    }
};

/** Attendance Excel/CSV Uploader & Auto-Fill */
window.importAttendanceFromFile = function(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    if (!currentStudents.length) {
        showToast("Please load the student sheet first.", "warning");
        event.target.value = "";
        return;
    }
    
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const data = new Uint8Array(e.target.result);
            const workbook = XLSX.read(data, { type: 'array' });
            const sheetName = workbook.SheetNames[0];
            const worksheet = workbook.Sheets[sheetName];
            const jsonData = XLSX.utils.sheet_to_json(worksheet, { defval: "" });
            
            if (!jsonData.length) {
                showToast("The uploaded file is empty.", "error");
                return;
            }
            
            let regKey = null;
            let statusKey = null;
            
            const sampleRow = jsonData[0];
            const keys = Object.keys(sampleRow);
            
            for (const k of keys) {
                const kl = k.toLowerCase().replace(/[^a-z0-9]/g, '');
                if (kl.includes('reg') || kl.includes('roll') || kl.includes('id') || kl.includes('adm')) {
                    regKey = k;
                }
                if (kl.includes('status') || kl.includes('attend') || kl.includes('present') || kl.includes('state')) {
                    statusKey = k;
                }
            }
            
            // Fallbacks
            if (!regKey && keys.length > 0) regKey = keys[0];
            if (!statusKey) {
                if (keys.length > 2) statusKey = keys[2];
                else if (keys.length > 1) statusKey = keys[1];
            }
            
            if (!regKey || !statusKey) {
                showToast("Could not determine student register or attendance status columns in spreadsheet.", "error");
                return;
            }
            
            let matchedCount = 0;
            const rows = document.querySelectorAll('#att-tbody tr');
            
            rows.forEach(tr => {
                const regNo = tr.querySelector('.reg-col').textContent.trim();
                
                // Match register number
                const matchedRow = jsonData.find(row => {
                    const rowReg = String(row[regKey] || '').trim();
                    return rowReg.toLowerCase() === regNo.toLowerCase();
                });
                
                if (matchedRow) {
                    const rawVal = String(matchedRow[statusKey]).trim().toUpperCase();
                    let mappedStatus = '';
                    
                    if (['P', 'PRESENT', '1', 'Y', 'YES'].includes(rawVal)) {
                        mappedStatus = 'P';
                    } else if (['AB', 'ABSENT', 'A', '0', 'N', 'NO'].includes(rawVal)) {
                        mappedStatus = 'AB';
                    } else if (rawVal === 'SR') {
                        mappedStatus = 'SR';
                    } else if (rawVal === 'DL') {
                        mappedStatus = 'DL';
                    }
                    
                    if (mappedStatus) {
                        const btn = tr.querySelector(`.status-btn[data-code="${mappedStatus}"]`);
                        if (btn) {
                            setStudentStatus(btn, mappedStatus);
                            matchedCount++;
                        }
                    }
                }
            });
            
            showToast(`Auto-filled attendance for ${matchedCount} out of ${rows.length} students.`, "success");
        } catch (err) {
            console.error(err);
            showToast("Failed to parse file. Verify file format.", "error");
        } finally {
            event.target.value = "";
        }
    };
    reader.readAsArrayBuffer(file);
};

// ─────────────────────────────────────────────────────────────────────────────
// Initialization
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    await initWorkspace();
    await loadTimetable();
    document.getElementById('att-date').value = new Date().toISOString().split('T')[0];
});
