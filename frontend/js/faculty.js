const API_URL = 'http://localhost:5000/api/faculty';
const token = localStorage.getItem('token');
const role = localStorage.getItem('role');

if (!token || role !== 'faculty') {
    window.location.href = 'login.html';
}

function getAuthHeaders() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

function showSection(sectionId) {
    document.querySelectorAll('.section-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-links li').forEach(el => el.classList.remove('active'));
    
    document.getElementById(sectionId).classList.add('active');
    event.currentTarget.parentElement.classList.add('active');

    if (sectionId === 'classes') fetchMyClasses();
    if (sectionId === 'attendance') populateClassDropdowns('att-class');
    if (sectionId === 'marks') populateClassDropdowns('marks-class');
}

function logout() {
    localStorage.clear();
    window.location.href = 'login.html';
}

function showMessage(elementId, message, isError = false) {
    const el = document.getElementById(elementId);
    el.textContent = message;
    el.className = `message-container ${isError ? 'message-error' : 'message-success'}`;
    el.style.display = 'block';
    setTimeout(() => { el.style.display = 'none'; el.className = 'message-container'; }, 5000);
}

let classesCache = [];

async function fetchMyClasses() {
    try {
        const res = await fetch(`${API_URL}/my-classes`, { headers: getAuthHeaders() });
        const data = await res.json();
        
        classesCache = data;

        const tbody = document.querySelector('#my-classes-table tbody');
        tbody.innerHTML = '';
        
        if (res.ok) {
            data.forEach(c => {
                let rolesStr = c.roles.length > 0 ? c.roles.map(r => r.replace(/_/g, ' ')).join(', ') : '<span style="color:var(--text-muted);">Subject Teacher Only</span>';
                let subjectsStr = c.subjects.length > 0 ? c.subjects.join(', ') : '<span style="color:var(--text-muted);">None Assigned</span>';
                
                tbody.innerHTML += `
                    <tr>
                        <td style="font-weight: 600;">${c.department} Sem ${c.semester} ${c.section}</td>
                        <td style="text-transform: capitalize;">${rolesStr}</td>
                        <td>${subjectsStr}</td>
                        <td><button class="btn" onclick="window.location.href='faculty_class.html?class_id=${c.class_id}'" style="padding: 0.4rem 0.8rem; height: auto;">Manage Workspace</button></td>
                    </tr>
                `;
            });
        }
    } catch(err) { console.error(err); }
}

async function populateClassDropdowns(selectId) {
    if(classesCache.length === 0) {
        const res = await fetch(`${API_URL}/classes`, { headers: getAuthHeaders() });
        classesCache = await res.json();
    }
    const select = document.getElementById(selectId);
    select.innerHTML = '<option value="" disabled selected>Select Class</option>';
    
    // Quick dedup
    const seen = new Set();
    classesCache.forEach(c => {
        if(!seen.has(c.id)) {
            seen.add(c.id);
            select.innerHTML += `<option value="${c.id}">${c.department} - Sem ${c.semester} (${c.section})</option>`;
        }
    });
}

async function loadClassSubjectsForAttendance() {
    const classId = document.getElementById('att-class').value;
    await populateSubjectsDropdown(classId, 'att-subject');
}

async function loadClassSubjectsForMarks() {
    const classId = document.getElementById('marks-class').value;
    await populateSubjectsDropdown(classId, 'marks-subject');
}

async function populateSubjectsDropdown(classId, selectId) {
    try {
        const res = await fetch(`${API_URL}/class/${classId}/subjects`, { headers: getAuthHeaders() });
        const data = await res.json();
        const select = document.getElementById(selectId);
        select.innerHTML = '<option value="" disabled selected>Select Subject</option>';
        data.forEach(s => {
            select.innerHTML += `<option value="${s.id}">${s.name}</option>`;
        });
    } catch(err) { console.error(err); }
}

// --- Attendance Module ---
document.getElementById('attendance-filter-form')?.addEventListener('submit', async(e) => {
    e.preventDefault();
    const classId = document.getElementById('att-class').value;
    const date = document.getElementById('att-date').value;
    const hour = document.getElementById('att-hour').value;
    const subjectId = document.getElementById('att-subject').value;
    
    try {
        // Fetch Students
        const stuRes = await fetch(`${API_URL}/class/${classId}/students`, { headers: getAuthHeaders() });
        const students = await stuRes.json();
        
        // Fetch Existing Attendance
        const attRes = await fetch(`${API_URL}/attendance?class_id=${classId}&date=${date}&hour=${hour}&subject_id=${subjectId}`, { headers: getAuthHeaders() });
        const existingAtt = await attRes.json(); // {student_id: status}
        
        const tbody = document.querySelector('#attendance-table tbody');
        tbody.innerHTML = '';
        
        students.forEach(stu => {
            const status = existingAtt[stu.id] || '';
            tbody.innerHTML += `
                <tr data-student-id="${stu.id}">
                    <td>${stu.register_number}</td>
                    <td>${stu.name}</td>
                    <td>
                        <select class="form-control form-select att-status-select" style="min-width: 120px; padding:0.5rem; background-position: right 0.5rem center;">
                            <option value="">Select</option>
                            <option value="P" ${status==='P'?'selected':''}>Present</option>
                            <option value="AB" ${status==='AB'?'selected':''}>Absent</option>
                            <option value="SR" ${status==='SR'?'selected':''}>Sick Room</option>
                            <option value="DL" ${status==='DL'?'selected':''}>Duty Leave</option>
                        </select>
                    </td>
                </tr>
            `;
        });
        
        document.getElementById('attendance-sheet-container').style.display = 'block';
    } catch(err) { console.error(err); }
});

async function saveAttendance() {
    const classId = document.getElementById('att-class').value;
    const date = document.getElementById('att-date').value;
    const hour = document.getElementById('att-hour').value;
    const subjectId = document.getElementById('att-subject').value;
    
    const attendance = {};
    document.querySelectorAll('#attendance-table tbody tr').forEach(tr => {
        const sId = tr.getAttribute('data-student-id');
        const status = tr.querySelector('.att-status-select').value;
        if(status) {
            attendance[sId] = status;
        }
    });
    
    try {
        const res = await fetch(`${API_URL}/attendance`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ class_id: classId, date, hour, subject_id: subjectId, attendance })
        });
        const data = await res.json();
        if(res.ok) {
            showMessage('attendance-msg', 'Attendance saved successfully');
        } else {
            showMessage('attendance-msg', data.message, true);
        }
    } catch(err) { console.error(err); showMessage('attendance-msg', 'Error saving', true); }
}

// --- Marks Module ---
document.getElementById('marks-filter-form')?.addEventListener('submit', async(e) => {
    e.preventDefault();
    const classId = document.getElementById('marks-class').value;
    
    try {
        const stuRes = await fetch(`${API_URL}/class/${classId}/students`, { headers: getAuthHeaders() });
        const students = await stuRes.json();
        
        const tbody = document.querySelector('#marks-table tbody');
        tbody.innerHTML = '';
        
        students.forEach(stu => {
            tbody.innerHTML += `
                <tr data-student-id="${stu.id}">
                    <td>${stu.register_number}</td>
                    <td>${stu.name}</td>
                    <td>
                        <input type="number" step="0.01" class="form-control mark-input" style="padding:0.5rem;" placeholder="Marks">
                    </td>
                </tr>
            `;
        });
        
        document.getElementById('marks-sheet-container').style.display = 'block';
    } catch(err) { console.error(err); }
});

async function saveMarks() {
    const subjectId = document.getElementById('marks-subject').value;
    const markType = document.getElementById('marks-type').value;
    const markName = document.getElementById('marks-name').value;
    
    const marksData = {};
    document.querySelectorAll('#marks-table tbody tr').forEach(tr => {
        const sId = tr.getAttribute('data-student-id');
        const mark = tr.querySelector('.mark-input').value;
        if(mark !== '') {
            marksData[sId] = parseFloat(mark);
        }
    });
    
    try {
        const res = await fetch(`${API_URL}/marks`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ subject_id: subjectId, mark_type: markType, mark_name: markName, marks: marksData })
        });
        const data = await res.json();
        if(res.ok) {
            showMessage('marks-msg', 'Marks saved successfully');
        } else {
            showMessage('marks-msg', data.message, true);
        }
    } catch(err) { console.error(err); showMessage('marks-msg', 'Error saving', true); }
}

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

// Fetch Quick summary metrics for analytics widgets
async function fetchQuickAnalytics() {
    try {
        const res = await fetch('http://localhost:5000/api/analytics/summary', { headers: getAuthHeaders() });
        if (!res.ok) throw new Error();
        const data = await res.json();
        
        document.getElementById('quick-avg-att').textContent = (data.average_attendance || 100.0) + '%';
        document.getElementById('quick-at-risk-count').textContent = data.at_risk_count || 0;
    } catch (e) {
        console.error('Failed to load quick analytics summary', e);
    }
}

// Initial Load
document.addEventListener('DOMContentLoaded', () => {
    fetchMyClasses();
    fetchUpcomingEvents();
    fetchQuickAnalytics();
});
