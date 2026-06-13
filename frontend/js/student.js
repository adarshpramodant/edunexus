// ─────────────────────────────────────────────────────────────────────────────
// EduNexus — Student Dashboard JS  (Marks v2 + Performance)
// ─────────────────────────────────────────────────────────────────────────────

const API_URL = 'http://localhost:5000/api/student';
const token   = localStorage.getItem('token');
const role    = localStorage.getItem('role');

if (!token || role !== 'student') {
    window.location.href = 'login.html';
}

function getAuthHeaders() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

// ── Nav ───────────────────────────────────────────────────────────────────────
function showSection(sectionId, anchor) {
    document.querySelectorAll('.section-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-links li').forEach(el => el.classList.remove('active'));
    document.getElementById(sectionId).classList.add('active');
    if (anchor) anchor.parentElement.classList.add('active');

    if (sectionId === 'attendance') fetchAttendanceHistory();
    if (sectionId === 'marks')      fetchMarksAndPerformance();
    if (sectionId === 'schedule')   fetchTimetable();
    if (sectionId === 'analytics')  fetchStudentAnalytics();
}

function logout() {
    localStorage.clear();
    window.location.href = 'login.html';
}

// ── Profile ───────────────────────────────────────────────────────────────────
async function fetchProfile() {
    try {
        const res  = await fetch(`${API_URL}/profile`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (res.ok && data) {
            document.getElementById('student-name').innerText = data.name;
            document.getElementById('reg-no-display').innerText = data.register_number || 'N/A';
            document.getElementById('class-display').innerText = data.department
                ? `${data.department} | Sem ${data.semester} | Sec ${data.section}`
                : 'Not assigned to class';
        }
    } catch (err) { console.error(err); }
}

// ── Status badge helper ───────────────────────────────────────────────────────
function getStatusBadge(pct) {
    if (pct >= 85) return `<span style="color:#10b981;font-weight:bold;">${pct}%</span> <span style="color:var(--text-muted);font-size:0.8rem;">(Excellent)</span>`;
    if (pct >= 75) return `<span style="color:#fcd34d;font-weight:bold;">${pct}%</span> <span style="color:var(--text-muted);font-size:0.8rem;">(Good)</span>`;
    return `<span style="color:#ef4444;font-weight:bold;">${pct}%</span> <span style="color:var(--text-muted);font-size:0.8rem;">(Low)</span>`;
}

// ── Courses ───────────────────────────────────────────────────────────────────
async function fetchCourses() {
    try {
        const res  = await fetch(`${API_URL}/courses`, { headers: getAuthHeaders() });
        const data = await res.json();
        const grid = document.getElementById('courses-grid');
        grid.innerHTML = '';

        if (data.length === 0) {
            grid.innerHTML = '<div class="dashboard-card" style="grid-column:1/-1;"><p>No courses assigned yet.</p></div>';
            return;
        }

        data.forEach(course => {
            let marksHtml = '<p style="font-size:0.875rem;color:var(--text-muted);">No marks recorded</p>';
            if (course.marks && course.marks.length > 0) {
                marksHtml = '<ul style="list-style:none;padding:0;margin:0;font-size:0.875rem;">';
                course.marks.slice(0, 3).forEach(m => {
                    marksHtml += `<li style="display:flex;justify-content:space-between;margin-bottom:0.2rem;">
                        <span><span style="font-weight:600;">${m.mark_type}</span>: ${m.mark_name}</span>
                        <span style="font-weight:bold;">${m.marks}</span>
                    </li>`;
                });
                if (course.marks.length > 3) marksHtml += `<li style="font-style:italic;color:var(--text-muted);font-size:0.8rem;margin-top:0.2rem;">+ more in Marks tab</li>`;
                marksHtml += '</ul>';
            }

            grid.innerHTML += `
                <div class="dashboard-card" style="border-top:4px solid var(--primary-color);">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.5rem;">
                        <h3 style="font-size:1.2rem;margin:0;">${course.subject_name}</h3>
                        <span style="background:var(--primary-color);color:white;padding:0.2rem 0.5rem;border-radius:4px;font-size:0.75rem;font-weight:bold;">${course.subject_code || 'N/A'}</span>
                    </div>
                    <p style="color:var(--text-muted);margin-bottom:1.5rem;font-size:0.9rem;"><i class="fas fa-user-tie"></i> ${course.teacher_name || 'Unassigned'}</p>
                    <div style="background:rgba(15,23,42,0.5);padding:1rem;border-radius:0.5rem;margin-bottom:1rem;">
                        <p style="font-size:0.9rem;color:var(--text-muted);margin-bottom:0.25rem;">Attendance</p>
                        <p style="font-size:1.5rem;font-weight:bold;">${course.present_hours} / ${course.total_hours}</p>
                        <p style="font-size:1rem;margin-top:0.5rem;">${getStatusBadge(course.percentage)}</p>
                    </div>
                    <div style="background:rgba(15,23,42,0.5);padding:1rem;border-radius:0.5rem;">
                        <p style="font-size:0.9rem;color:var(--text-muted);margin-bottom:0.5rem;">Recent Marks</p>
                        ${marksHtml}
                    </div>
                </div>`;
        });
    } catch (err) { console.error(err); }
}

// ── Attendance ────────────────────────────────────────────────────────────────
async function fetchAttendanceHistory() {
    try {
        const res  = await fetch(`${API_URL}/attendance/history`, { headers: getAuthHeaders() });
        const data = await res.json();
        const tbody = document.querySelector('#attendance-history-table tbody');
        tbody.innerHTML = '';
        if (res.ok) {
            data.forEach(row => {
                tbody.innerHTML += `
                    <tr>
                        <td>${row.date}</td>
                        <td>Hour ${row.hour}</td>
                        <td>${row.subject_name}</td>
                        <td><span class="att-chip ${row.status}">${row.status}</span></td>
                    </tr>`;
            });
        }
    } catch (err) { console.error(err); }
}

// ── Timetable ─────────────────────────────────────────────────────────────────
async function fetchTimetable() {
    const container = document.getElementById('student-tt-grid');
    const loading   = document.getElementById('tt-loading');
    const DAYS      = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
    const HOURS     = [1,2,3,4,5,6,7,8];
    const todayName = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][new Date().getDay()];

    try {
        const res  = await fetch(`${API_URL}/timetable`, { headers: getAuthHeaders() });
        const data = await res.json();
        loading.style.display = 'none';

        let html = '<table><thead><tr><th>Day</th>';
        HOURS.forEach(h => { html += `<th>H${h}</th>`; });
        html += '</tr></thead><tbody>';

        DAYS.forEach(day => {
            const isToday = day === todayName;
            html += `<tr><td class="day-col${isToday ? ' today-row' : ''}">${day}${isToday ? ' <span style="color:var(--primary-color);font-size:0.65rem;">▶</span>' : ''}</td>`;
            HOURS.forEach(h => {
                const slot = data[day]?.[h];
                const cls  = isToday ? ' today-row' : '';
                if (slot && slot.subject_name) {
                    html += `<td class="${cls}">
                        <span class="tt-cell-name">${slot.subject_name}</span>
                        <span class="tt-cell-teacher">${slot.teacher_name || ''}</span>
                    </td>`;
                } else {
                    html += `<td class="${cls}"><span class="tt-empty">—</span></td>`;
                }
            });
            html += '</tr>';
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (err) {
        loading.textContent = 'Failed to load timetable.';
    }
}

// ── Marks & Performance ───────────────────────────────────────────────────────

/** Grade CSS class helper */
function gradeChipClass(g) {
    const map = { 'A+': 'Ap', 'A': 'A', 'B+': 'Bp', 'B': 'B', 'C': 'C', 'D': 'D' };
    return map[g] || 'D';
}

/** Value colour class based on percentage of 100 */
function markValueClass(val) {
    if (val >= 75) return 'mark-val-high';
    if (val >= 50) return 'mark-val-mid';
    return 'mark-val-low';
}

/** Toggle subject card open/close */
function toggleSubjectCard(el) {
    const body     = el.nextElementSibling;
    const chevron  = el.querySelector('.card-chevron');
    const isOpen   = body.classList.contains('open');
    body.classList.toggle('open', !isOpen);
    chevron.classList.toggle('open', !isOpen);
}

/** Fetch marks and performance, then render */
async function fetchMarksAndPerformance() {
    const container = document.getElementById('marks-subjects-container');
    container.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:2rem 0;"><i class="fas fa-spinner fa-spin"></i> Loading…</p>';

    try {
        // Parallel: marks data + performance summary
        const [marksRes, perfRes] = await Promise.all([
            fetch(`${API_URL}/marks`,       { headers: getAuthHeaders() }),
            fetch(`${API_URL}/performance`, { headers: getAuthHeaders() })
        ]);

        const marksData = await marksRes.json();
        const perfData  = await perfRes.json();

        // ── Overall performance cards ──
        if (perfData && perfData.overall_average !== undefined) {
            document.getElementById('perf-avg').textContent   = `${perfData.overall_average}%`;
            const gEl = document.getElementById('perf-grade');
            gEl.textContent = perfData.overall_grade;
            gEl.className   = `perf-value grade grade-${gradeChipClass(perfData.overall_grade)}`;
        }

        const subjectsArr = Array.isArray(marksData) ? marksData : [];
        const totalEvals  = subjectsArr.reduce((acc, s) => {
            return acc + (s.groups || []).reduce((a2, g) => a2 + (g.entries || []).length, 0);
        }, 0);

        document.getElementById('perf-subjects').textContent = subjectsArr.length;
        document.getElementById('perf-evals').textContent    = totalEvals;

        // ── Subject cards ──
        if (subjectsArr.length === 0) {
            container.innerHTML = `<div style="text-align:center; padding:3rem; color:var(--text-muted);">
                <i class="fas fa-chart-bar" style="font-size:3rem; margin-bottom:1rem; opacity:0.3;"></i>
                <p style="font-size:1rem;">No marks have been recorded yet.</p>
            </div>`;
            return;
        }

        container.innerHTML = '';
        subjectsArr.forEach((subject, idx) => {
            const gradeKey   = gradeChipClass(subject.grade);
            const avgDisplay = subject.average || 0;

            // Build groups HTML
            let groupsHtml = '';
            const typeIcons = {
                'Internal':   'fa-scroll',
                'Assignment': 'fa-file-alt',
                'Lab':        'fa-flask',
                'Quiz':       'fa-question-circle',
                'Activity':   'fa-running',
                'Custom':     'fa-star'
            };

            (subject.groups || []).forEach(group => {
                const icon = typeIcons[group.mark_type] || 'fa-tag';
                const entriesHtml = (group.entries || []).map(entry => {
                    const valCls = markValueClass(entry.marks);
                    const dateStr = entry.updated_at ? new Date(entry.updated_at).toLocaleDateString() : '';
                    return `<div class="mark-entry">
                        <div class="mark-entry-name">${entry.mark_name}</div>
                        <div class="mark-entry-val ${valCls}">${entry.marks}</div>
                        ${dateStr ? `<div class="mark-entry-date">${dateStr}</div>` : ''}
                    </div>`;
                }).join('');

                groupsHtml += `<div class="mark-group">
                    <div class="mark-group-title">
                        <i class="fas ${icon}"></i> ${group.mark_type}
                        <span style="font-weight:400; color:var(--text-muted); text-transform:none; letter-spacing:0;">(${(group.entries || []).length} item${(group.entries||[]).length !== 1 ? 's' : ''})</span>
                    </div>
                    <div class="mark-entries">${entriesHtml}</div>
                </div>`;
            });

            // Total & average row
            const totalHtml = `<div class="subject-total-row">
                <span class="total-label">Total marks scored</span>
                <div style="display:flex; align-items:center; gap:1rem;">
                    <span class="total-val">${subject.total.toFixed(1)}</span>
                    <span style="color:var(--text-muted); font-size:0.82rem;">Avg: <strong>${avgDisplay}</strong></span>
                </div>
            </div>`;

            container.innerHTML += `
                <div class="marks-subject-card">
                    <div class="subject-card-header" onclick="toggleSubjectCard(this)">
                        <div class="subject-card-left">
                            ${subject.subject_code ? `<span class="subject-code-badge">${subject.subject_code}</span>` : ''}
                            <span class="subject-name-title">${subject.subject_name}</span>
                        </div>
                        <div class="subject-card-right">
                            <span class="subject-avg-pill">
                                <i class="fas fa-chart-line" style="font-size:0.7rem;"></i>
                                Avg: ${avgDisplay}
                            </span>
                            <span class="grade-chip ${gradeKey}">${subject.grade}</span>
                            <i class="fas fa-chevron-down card-chevron${idx === 0 ? ' open' : ''}"></i>
                        </div>
                    </div>
                    <div class="subject-card-body${idx === 0 ? ' open' : ''}">
                        ${groupsHtml || '<div class="mark-group" style="color:var(--text-muted); font-size:0.875rem;">No marks entered yet.</div>'}
                        ${totalHtml}
                    </div>
                </div>`;
        });

    } catch (err) {
        console.error(err);
        container.innerHTML = '<p style="color:var(--error);text-align:center;padding:2rem 0;">Failed to load marks.</p>';
    }
}

// ── Download Report Card ──────────────────────────────────────────────────────
window.downloadReportCard = async function() {
    const btn  = document.getElementById('btn-download-report');
    const orig = btn.innerHTML;
    btn.disabled  = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating PDF…';
    btn.style.opacity = '0.7';

    try {
        const res = await fetch('http://localhost:5000/api/student/report', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ message: 'Unknown error' }));
            alert('Report generation failed: ' + (err.message || res.statusText));
            return;
        }

        // Extract filename from Content-Disposition header if present
        const cd       = res.headers.get('Content-Disposition') || '';
        const match    = cd.match(/filename="?([^"]+)"?/);
        const filename = match ? match[1] : `ReportCard_${Date.now()}.pdf`;

        // Blob download
        const blob = await res.blob();
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 10000);

        // Show brief success state
        btn.innerHTML      = '<i class="fas fa-check-circle"></i> Downloaded!';
        btn.style.background = 'linear-gradient(135deg,#059669,#10b981)';
        btn.style.opacity  = '1';
        setTimeout(() => {
            btn.innerHTML      = orig;
            btn.style.background = '';
            btn.disabled       = false;
            btn.style.opacity  = '1';
        }, 3000);

    } catch (err) {
        console.error(err);
        alert('Network error — could not download report.');
        btn.disabled  = false;
        btn.innerHTML = orig;
        btn.style.opacity = '1';
    }
};

// ── Fetch Upcoming Academic Events ──
async function fetchUpcomingEvents() {
    try {
        const container = document.getElementById('upcoming-events-container');
        const list = document.getElementById('upcoming-events-list');
        if (!container || !list) return;

        const res = await fetch('http://localhost:5000/api/calendar/events/upcoming', { headers: getAuthHeaders() });
        if (!res.ok) return;

        const events = await res.json();
        if (events.length === 0) {
            container.style.display = 'none';
            return;
        }

        list.innerHTML = '';
        events.forEach(e => {
            const start = new Date(e.start_date);
            const dateStr = start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            const timeStr = start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            
            let color = '#818cf8';
            if (e.event_color === 'red') color = '#f87171';
            else if (e.event_color === 'yellow') color = '#fbbf24';
            else if (e.event_color === 'green') color = '#34d399';
            else if (e.event_color === 'purple') color = '#c084fc';
            
            list.innerHTML += `
                <div style="background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(255, 255, 255, 0.05); border-left: 4px solid ${color}; padding: 0.85rem; border-radius: 0.5rem; display: flex; flex-direction: column; gap: 0.25rem;">
                    <span style="font-size:0.65rem; color:var(--text-muted); font-weight:700; text-transform:uppercase;">${e.event_type.replace('_', ' ')}</span>
                    <h4 style="margin:0; font-size:0.88rem; font-weight:700; color:var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${e.title}">${e.title}</h4>
                    <span style="font-size:0.75rem; color:var(--text-muted);"><i class="far fa-clock"></i> ${dateStr} at ${timeStr}</span>
                </div>
            `;
        });
        container.style.display = 'block';
    } catch (err) {
        console.error('Failed to load upcoming events', err);
    }
}

// ── Analytics Summary (Student Personal Analytics) ──────────────────────────
async function fetchStudentAnalytics() {
    try {
        const res = await fetch('http://localhost:5000/api/analytics/student', { headers: getAuthHeaders() });
        if (!res.ok) throw new Error('Failed to load personal analytics');
        const s = await res.json();

        // 1. Populate Metrics summary cards
        document.getElementById('analytics-rank').textContent = `#${s.class_rank} / ${s.class_total_students}`;
        document.getElementById('analytics-marks').textContent = s.average_marks.toFixed(1);
        document.getElementById('analytics-attendance').textContent = s.attendance_percentage.toFixed(1) + '%';
        document.getElementById('analytics-assignments').textContent = s.assignment_completion_percentage.toFixed(1) + '%';

        // 2. Populate benchmarks vs class average values
        document.getElementById('benchmark-my-marks').textContent = s.average_marks.toFixed(1);
        document.getElementById('benchmark-class-marks').textContent = s.class_average_marks.toFixed(1);
        document.getElementById('benchmark-my-att').textContent = s.attendance_percentage.toFixed(1) + '%';
        document.getElementById('benchmark-class-att').textContent = s.class_average_attendance.toFixed(1) + '%';
        document.getElementById('benchmark-my-assign').textContent = s.assignment_completion_percentage.toFixed(1) + '%';
        document.getElementById('benchmark-class-assign').textContent = s.class_average_assignment_completion.toFixed(1) + '%';

        // Update progress/comparison fill widths (capped at 100%)
        const marksPct = Math.min((s.average_marks / Math.max(s.class_average_marks, 1)) * 50, 100);
        document.getElementById('benchmark-marks-fill').style.width = `${s.class_average_marks > 0 ? (s.average_marks / 100) * 100 : 0}%`;
        document.getElementById('benchmark-att-fill').style.width = `${s.attendance_percentage}%`;
        document.getElementById('benchmark-assign-fill').style.width = `${s.assignment_completion_percentage}%`;

        // 3. Risk alert display
        const alertMount = document.getElementById('analytics-alert-container');
        if (s.severity === 'NONE') {
            alertMount.innerHTML = `
                <div style="background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.3); border-radius:0.5rem; padding:0.85rem; color:#10b981; font-size:0.8rem; display:flex; align-items:center; gap:0.5rem;">
                    <i class="fas fa-check-circle" style="font-size:1.15rem;"></i>
                    <div>
                        <strong>Good Standing</strong>
                        <div style="font-size:0.7rem; opacity:0.85; margin-top:0.1rem;">You are in good standing! Keep up the excellent work.</div>
                    </div>
                </div>
            `;
        } else {
            const sevColor = s.severity === 'LOW' ? '#94a3b8' : s.severity === 'MEDIUM' ? '#fbbf24' : s.severity === 'HIGH' ? '#f59e0b' : '#ef4444';
            const reasonsText = s.risk_reasons.map(r => r.replace('_', ' ').toLowerCase()).join(', ');
            alertMount.innerHTML = `
                <div style="background:rgba(239,68,68,0.08); border:1px solid ${sevColor}; border-radius:0.5rem; padding:0.85rem; color:${sevColor}; font-size:0.8rem; display:flex; align-items:center; gap:0.5rem;">
                    <i class="fas fa-exclamation-triangle" style="font-size:1.15rem;"></i>
                    <div>
                        <strong>${s.severity} Risk Alert</strong>
                        <div style="font-size:0.7rem; opacity:0.85; margin-top:0.1rem;">Flagged for: ${reasonsText}. Please review your courses and seek teacher guidance.</div>
                    </div>
                </div>
            `;
        }

        // 4. Trend display
        const trendMount = document.getElementById('analytics-trend-container');
        const trendClass = s.trend === 'IMPROVING' ? 'improving' : s.trend === 'DECLINING' ? 'declining' : 'stable';
        const trendColor = s.trend === 'IMPROVING' ? '#10b981' : s.trend === 'DECLINING' ? '#f87171' : '#64748b';
        const trendIcon = s.trend === 'IMPROVING' ? 'fa-arrow-trend-up' : s.trend === 'DECLINING' ? 'fa-arrow-trend-down' : 'fa-arrows-left-right';
        
        trendMount.innerHTML = `
            <div style="display:flex; align-items:center; gap:0.5rem; color:${trendColor}; font-size:1.05rem; font-weight:800; padding: 0.25rem 0;">
                <i class="fas ${trendIcon}" style="font-size:1.35rem;"></i>
                <span>${s.trend}</span>
            </div>
            <p style="color:var(--text-muted); font-size:0.72rem; margin:0.25rem 0 0;">Trend based on chronological assessment marks variations.</p>
        `;

    } catch (err) {
        console.error('Failed to load student analytics metrics', err);
    }
}

// ── Initial Load ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    fetchProfile();
    fetchCourses();
    fetchTimetable(); // preload timetable
    fetchUpcomingEvents();
});
