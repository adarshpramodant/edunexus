// ─────────────────────────────────────────────────────────────────────────────
// EduNexus — Student Performance Analytics JS
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = 'http://localhost:5000/api';
const token = localStorage.getItem('token');
const role = localStorage.getItem('role');

if (!token || !role) {
    window.location.href = 'login.html';
}

// Global Roster State
let activeTab = 'at-risk'; // 'at-risk' or 'top-performers'
let currentLimit = 15;
let currentOffset = 0;
let totalRecords = 0;
let searchQuery = '';
let rosterData = [];

// Dynamic Menu Loader
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
            <li><a href="assignments.html"><i class="fas fa-tasks"></i> Assignments</a></li>
            <li><a href="calendar.html"><i class="fas fa-calendar-alt"></i> Calendar</a></li>
            <li class="active"><a href="analytics.html"><i class="fas fa-chart-bar"></i> Analytics</a></li>
        `;
    } else if (role === 'faculty') {
        menuHtml = `
            <li><a href="faculty_dashboard.html#classes"><i class="fas fa-chalkboard-teacher"></i> My Classes</a></li>
            <li><a href="faculty_dashboard.html#attendance"><i class="fas fa-clipboard-check"></i> Attendance</a></li>
            <li><a href="faculty_dashboard.html#marks"><i class="fas fa-star"></i> Marks</a></li>
            <li><a href="survey_manage.html"><i class="fas fa-poll"></i> Surveys</a></li>
            <li><a href="documents.html"><i class="fas fa-folder-open"></i> Documents</a></li>
            <li><a href="assignments.html"><i class="fas fa-tasks"></i> Assignments</a></li>
            <li><a href="calendar.html"><i class="fas fa-calendar-alt"></i> Calendar</a></li>
            <li class="active"><a href="analytics.html"><i class="fas fa-chart-bar"></i> Analytics</a></li>
        `;
    }

    menu.innerHTML = menuHtml;

    // Show setting panel for Admin only
    const settingsPanel = document.getElementById('settings-panel');
    if (settingsPanel) {
        settingsPanel.style.display = role === 'admin' ? 'flex' : 'none';
    }
}

function getAuthHeaders() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

// ── Fetch Faculty / Admin Statistics ──
async function fetchSummaryMetrics() {
    try {
        const res = await fetch(`${API_BASE}/analytics/summary`, { headers: getAuthHeaders() });
        if (!res.ok) throw new Error();
        const data = await res.json();
        
        document.getElementById('metric-students').textContent = data.total_students || 0;
        document.getElementById('metric-at-risk').textContent = data.at_risk_count || 0;
        document.getElementById('metric-top-performers').textContent = data.top_performers_count || 0;
        document.getElementById('metric-avg-att').textContent = (data.average_attendance || 100.0) + '%';
        document.getElementById('metric-avg-assign').textContent = (data.average_assignment_completion || 100.0) + '%';
    } catch (e) {
        console.error('Failed to load metric summaries', e);
    }
}

// ── Load Dropdowns dynamically ──
async function loadDropdowns() {
    const classFilter = document.getElementById('class-filter');
    classFilter.innerHTML = '<option value="">All Taught Classes</option>';

    try {
        let res;
        if (role === 'admin') {
            res = await fetch(`${API_BASE}/admin/classes`, { headers: getAuthHeaders() });
        } else {
            res = await fetch(`${API_BASE}/faculty/my-classes`, { headers: getAuthHeaders() });
        }

        if (res.ok) {
            const classes = await res.json();
            classes.forEach(c => {
                const classId = c.class_id || c.id;
                const text = `${c.department} | Sem ${c.semester} | Sec ${c.section}`;
                classFilter.innerHTML += `<option value="${classId}">${escapeHtml(text)}</option>`;
            });
        }
    } catch (e) {
        console.error('Failed to populate class filters', e);
    }
}

// ── Switch Tabs ──
window.switchTab = function(tabName) {
    activeTab = tabName;
    document.getElementById('tab-btn-at-risk').classList.toggle('active', tabName === 'at-risk');
    document.getElementById('tab-btn-top-performers').classList.toggle('active', tabName === 'top-performers');
    
    currentOffset = 0;
    
    // Toggle reason/severity filter visibility
    const reasonFilter = document.getElementById('risk-reason-filter');
    const severityFilter = document.getElementById('severity-filter');
    if (tabName === 'at-risk') {
        reasonFilter.style.display = 'block';
        severityFilter.style.display = 'block';
    } else {
        reasonFilter.style.display = 'none';
        severityFilter.style.display = 'none';
    }

    fetchRoster();
};

// ── Fetch Roster Data ──
async function fetchRoster() {
    const classId = document.getElementById('class-filter').value;
    const reason = document.getElementById('risk-reason-filter').value;
    const severity = document.getElementById('severity-filter').value;
    const rosterBody = document.getElementById('roster-table-body');
    const rosterHead = document.getElementById('roster-table-head');
    
    if (!rosterBody || !rosterHead) return;

    rosterBody.innerHTML = '<tr><td colspan="7" style="text-align:center;">Loading roster list...</td></tr>';

    try {
        let url = `${API_BASE}/analytics/${activeTab}?limit=${currentLimit}&offset=${currentOffset}`;
        if (classId) url += `&class_id=${classId}`;
        if (searchQuery) url += `&search=${encodeURIComponent(searchQuery)}`;
        
        if (activeTab === 'at-risk') {
            if (reason) url += `&reason=${reason}`;
            if (severity) url += `&severity=${severity}`;
        }

        const res = await fetch(url, { headers: getAuthHeaders() });
        if (!res.ok) throw new Error();
        const payload = await res.json();
        
        rosterData = payload.students || [];
        totalRecords = payload.total || 0;

        // Render Table Headers
        if (activeTab === 'at-risk') {
            rosterHead.innerHTML = `
                <tr>
                    <th>Reg Number</th>
                    <th>Student Name</th>
                    <th>Class</th>
                    <th>Attendance %</th>
                    <th>Assign %</th>
                    <th>Avg Marks</th>
                    <th>Trend</th>
                    <th>Severity</th>
                </tr>
            `;
        } else {
            rosterHead.innerHTML = `
                <tr>
                    <th>Reg Number</th>
                    <th>Student Name</th>
                    <th>Class</th>
                    <th>Avg Marks</th>
                    <th>Attendance %</th>
                    <th>Assign %</th>
                    <th>Trend</th>
                </tr>
            `;
        }

        // Render Rows
        rosterBody.innerHTML = '';
        if (rosterData.length === 0) {
            const cols = activeTab === 'at-risk' ? 8 : 7;
            rosterBody.innerHTML = `<tr><td colspan="${cols}" style="text-align:center; color:var(--text-muted);">No records found matching filters.</td></tr>`;
        } else {
            rosterData.forEach(s => {
                const tr = document.createElement('tr');
                const classText = `Sem ${s.semester_number} | ${s.class_section}`;
                const trendClass = s.trend === 'IMPROVING' ? 'improving' : s.trend === 'DECLINING' ? 'declining' : 'stable';
                const trendIcon = s.trend === 'IMPROVING' ? 'fa-arrow-trend-up' : s.trend === 'DECLINING' ? 'fa-arrow-trend-down' : 'fa-arrows-left-right';
                
                const trendHtml = `<span class="trend-indicator ${trendClass}"><i class="fas ${trendIcon}"></i> ${s.trend}</span>`;

                if (activeTab === 'at-risk') {
                    // Reason tags rendering
                    let reasonsHtml = '<div style="margin-top:0.35rem;">';
                    s.risk_reasons.forEach(r => {
                        reasonsHtml += `<span class="reason-tag">${r.replace('_', ' ')}</span>`;
                    });
                    reasonsHtml += '</div>';

                    tr.innerHTML = `
                        <td><strong>${escapeHtml(s.register_number)}</strong></td>
                        <td>
                            <div><strong>${escapeHtml(s.student_name)}</strong></div>
                            ${reasonsHtml}
                        </td>
                        <td>${escapeHtml(classText)}</td>
                        <td>${s.attendance_percentage.toFixed(1)}%</td>
                        <td>${s.assignment_completion_percentage.toFixed(1)}%</td>
                        <td><strong>${s.average_marks.toFixed(1)}</strong></td>
                        <td>${trendHtml}</td>
                        <td><span class="severity-badge ${s.severity.toLowerCase()}">${s.severity}</span></td>
                    `;
                } else {
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(s.register_number)}</strong></td>
                        <td><strong>${escapeHtml(s.student_name)}</strong></td>
                        <td>${escapeHtml(classText)}</td>
                        <td><strong style="color:#10b981;">${s.average_marks.toFixed(1)}</strong></td>
                        <td>${s.attendance_percentage.toFixed(1)}%</td>
                        <td>${s.assignment_completion_percentage.toFixed(1)}%</td>
                        <td>${trendHtml}</td>
                    `;
                }
                rosterBody.appendChild(tr);
            });
        }

        // Update pagination labels
        document.getElementById('total-records').textContent = totalRecords;
        document.getElementById('page-start').textContent = totalRecords === 0 ? 0 : currentOffset + 1;
        document.getElementById('page-end').textContent = Math.min(currentOffset + currentLimit, totalRecords);

    } catch (e) {
        rosterBody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--error);">Failed to load roster rows.</td></tr>';
    }
}

// ── Switch Pages ──
window.navigatePage = function(direction) {
    const nextOffset = currentOffset + (direction * currentLimit);
    if (nextOffset >= 0 && nextOffset < totalRecords) {
        currentOffset = nextOffset;
        fetchRoster();
    }
};

window.handleFilterChange = function() {
    currentOffset = 0;
    fetchRoster();
};

let searchTimeout;
window.handleSearch = function() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        searchQuery = document.getElementById('analytics-search').value.trim();
        currentOffset = 0;
        fetchRoster();
    }, 300);
};

// ── Save/Load Threshold Settings (Admin-Only) ──
async function loadThresholdSettings() {
    if (role !== 'admin') return;

    try {
        const res = await fetch(`${API_BASE}/analytics/settings`, { headers: getAuthHeaders() });
        if (!res.ok) throw new Error();
        const data = await res.json();
        
        document.getElementById('slider-att').value = Math.round(data.attendance);
        document.getElementById('slider-assign').value = Math.round(data.assignment);
        document.getElementById('slider-marks').value = Math.round(data.marks);

        updateSliderLbl('att');
        updateSliderLbl('assign');
        updateSliderLbl('marks');
    } catch (e) {
        console.error('Failed to load threshold settings', e);
    }
}

window.updateSliderLbl = function(type) {
    const val = document.getElementById(`slider-${type}`).value;
    document.getElementById(`${type}-val-lbl`).textContent = `${val}%`;
};

window.saveAnalyticsThresholds = async function() {
    const attendance = parseInt(document.getElementById('slider-att').value);
    const assignment = parseInt(document.getElementById('slider-assign').value);
    const marks = parseInt(document.getElementById('slider-marks').value);

    try {
        const res = await fetch(`${API_BASE}/analytics/settings`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ attendance, assignment, marks })
        });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.message);

        showToast('Analytics thresholds updated successfully!', 'success');
        fetchSummaryMetrics();
        fetchRoster();
    } catch (e) {
        showToast(e.message || 'Save failed.', 'error');
    }
};

// ── Class Performance Insights & Subjects ──
async function handleClassChange() {
    currentOffset = 0;
    fetchRoster();

    const classId = document.getElementById('class-filter').value;
    const insightsCard = document.getElementById('class-insights-card');
    const subjectSelector = document.getElementById('subject-selector');
    
    // Clear subject dropdown
    subjectSelector.innerHTML = '<option value="" disabled selected>Select Subject</option>';
    document.getElementById('subject-stats-mount').innerHTML = '<p style="color:var(--text-muted); font-size:0.78rem; text-align:center;">Select a class and a subject to review statistics details</p>';

    if (!classId) {
        insightsCard.style.display = 'none';
        return;
    }

    try {
        // 1. Fetch Class report card distribution
        const reportRes = await fetch(`${API_BASE}/analytics/class/${classId}`, { headers: getAuthHeaders() });
        if (reportRes.ok) {
            const data = await reportRes.json();
            insightsCard.style.display = 'flex';
            renderClassInsights(data);
        }

        // 2. Fetch subjects for this class to populate details inspector dropdown
        const subRes = await fetch(`${API_BASE}/admin/subjects?class_id=${classId}`, { headers: getAuthHeaders() });
        if (subRes.ok) {
            const subjects = await subRes.json();
            subjects.forEach(s => {
                subjectSelector.innerHTML += `<option value="${s.id}">${escapeHtml(s.name)} (${escapeHtml(s.code || '—')})</option>`;
            });
        }
    } catch (e) {
        console.error('Failed to load class metrics', e);
    }
}

function renderClassInsights(data) {
    const mount = document.getElementById('class-insights-container');
    if (!mount) return;

    // Calculate maximum count to map percentage distribution bars cleanly
    const dist = data.marks_distribution || {};
    const maxCount = Math.max(...Object.values(dist), 1);

    let barsHtml = '<div class="distribution-grid">';
    Object.keys(dist).forEach(grade => {
        const count = dist[grade];
        const pct = (count / maxCount) * 100;
        barsHtml += `
            <div class="dist-row">
                <strong style="width:25px;">${grade}</strong>
                <div class="dist-bar-bg">
                    <div class="dist-bar-fill" style="width: ${pct}%;"></div>
                </div>
                <span style="font-weight:700; width:20px; text-align:right;">${count}</span>
            </div>
        `;
    });
    barsHtml += '</div>';

    mount.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:0.5rem; justify-content:center;">
            <div style="font-size:0.85rem; color:var(--text-muted);">Class Average Marks: <strong style="color:var(--primary-color); font-size:1.15rem; margin-left:0.25rem;">${data.average_class_marks.toFixed(1)}</strong></div>
            <div style="font-size:0.85rem; color:var(--text-muted);">Class Average Attendance: <strong style="color:#fbbf24; font-size:1.15rem; margin-left:0.25rem;">${data.average_attendance.toFixed(1)}%</strong></div>
            <div style="font-size:0.85rem; color:var(--text-muted);">Assignment Completion Rate: <strong style="color:#10b981; font-size:1.15rem; margin-left:0.25rem;">${data.average_assignment_completion.toFixed(1)}%</strong></div>
        </div>
        <div>
            <h4 style="font-size:0.75rem; font-weight:700; text-transform:uppercase; color:var(--text-muted); margin-bottom:0.75rem;">Grade Distribution Profile</h4>
            ${barsHtml}
        </div>
    `;
}

window.handleSubjectChange = async function() {
    const subjectId = document.getElementById('subject-selector').value;
    const mount = document.getElementById('subject-stats-mount');
    if (!subjectId || !mount) return;

    mount.innerHTML = '<p style="text-align:center; font-size:0.8rem; color:var(--text-muted);">Loading subject metrics details...</p>';

    try {
        const res = await fetch(`${API_BASE}/analytics/subject/${subjectId}`, { headers: getAuthHeaders() });
        if (!res.ok) throw new Error();
        const s = await res.json();

        mount.innerHTML = `
            <div style="background:rgba(15,23,42,0.4); border:1px solid var(--border-color); border-radius:0.5rem; padding:0.85rem; display:flex; flex-direction:column; gap:0.4rem; font-size:0.82rem;">
                <div style="display:flex; justify-content:space-between;">
                    <span style="color:var(--text-muted);">Subject Average Marks:</span>
                    <strong>${s.average_marks.toFixed(1)}</strong>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span style="color:var(--text-muted);">Highest Score:</span>
                    <strong style="color:#10b981;">${s.highest_marks.toFixed(1)}</strong>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span style="color:var(--text-muted);">Lowest Score:</span>
                    <strong style="color:#f87171;">${s.lowest_marks.toFixed(1)}</strong>
                </div>
            </div>
            <div style="background:rgba(15,23,42,0.4); border:1px solid var(--border-color); border-radius:0.5rem; padding:0.85rem; display:flex; flex-direction:column; gap:0.4rem; font-size:0.82rem;">
                <div style="display:flex; justify-content:space-between;">
                    <span style="color:var(--text-muted);">Subject Attendance Rate:</span>
                    <strong>${s.subject_attendance_percentage.toFixed(1)}%</strong>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span style="color:var(--text-muted);">Total Hours Conducted:</span>
                    <strong>${s.total_hours} Hours</strong>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span style="color:var(--text-muted);">Total Student Absences:</span>
                    <strong style="color:#f87171;">${s.total_absences} AB</strong>
                </div>
            </div>
        `;
    } catch (e) {
        mount.innerHTML = '<p style="text-align:center; font-size:0.8rem; color:var(--error);">Failed to load subject report.</p>';
    }
};

// ── Export utilities ──
window.triggerCSVExport = function() {
    const classId = document.getElementById('class-filter').value;
    let url = `${API_BASE}/analytics/export/csv?type=${activeTab}&Authorization=Bearer+${token}`;
    if (classId) url += `&class_id=${classId}`;
    
    // Redirect browser to stream files
    window.location.href = url;
    showToast('CSV export request dispatched successfully.', 'success');
};

window.triggerPDFExport = function() {
    const classId = document.getElementById('class-filter').value;
    if (!classId) {
        showToast('Please select a specific class to export Class Performance PDF.', 'error');
        return;
    }

    let url = `${API_BASE}/analytics/export/pdf?class_id=${classId}&Authorization=Bearer+${token}`;
    window.location.href = url;
    showToast('PDF generation request dispatched successfully.', 'success');
};

// ── Toast utility ──
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

document.addEventListener('DOMContentLoaded', () => {
    renderSidebar();
    fetchSummaryMetrics();
    loadDropdowns();
    loadThresholdSettings();
    fetchRoster();
});
