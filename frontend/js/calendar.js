// ─────────────────────────────────────────────────────────────────────────────
// EduNexus — Academic Calendar JS
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = 'https://edunexus-quw3.onrender.com/api';
const token = localStorage.getItem('token');
const role = localStorage.getItem('role');

// Guard against unauthenticated access
if (!token || !role) {
    window.location.href = 'login.html';
}

// Global state
let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth(); // 0-11
let selectedDate = new Date();
let eventsList = []; // Month events fetched from server
let filterCategory = ''; // 'holiday', 'exams', 'deadline', 'event'
let searchQuery = '';
let decodedUserId = null;

// Auth Headers helper
function getAuthHeaders() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

// Decode user id from JWT
try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(window.atob(base64));
    decodedUserId = payload.user_id;
} catch (e) {
    console.error('Failed to parse token payload', e);
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
            <li><a href="assignments.html"><i class="fas fa-tasks"></i> Assignments</a></li>
            <li class="active"><a href="calendar.html"><i class="fas fa-calendar-alt"></i> Calendar</a></li>
        `;
    } else if (role === 'faculty') {
        menuHtml = `
            <li><a href="faculty_dashboard.html#classes"><i class="fas fa-chalkboard-teacher"></i> My Classes</a></li>
            <li><a href="faculty_dashboard.html#attendance"><i class="fas fa-clipboard-check"></i> Attendance</a></li>
            <li><a href="faculty_dashboard.html#marks"><i class="fas fa-star"></i> Marks</a></li>
            <li><a href="survey_manage.html"><i class="fas fa-poll"></i> Surveys</a></li>
            <li><a href="documents.html"><i class="fas fa-folder-open"></i> Documents</a></li>
            <li><a href="assignments.html"><i class="fas fa-tasks"></i> Assignments</a></li>
            <li class="active"><a href="calendar.html"><i class="fas fa-calendar-alt"></i> Calendar</a></li>
        `;
    } else if (role === 'student') {
        menuHtml = `
            <li><a href="student_dashboard.html#courses"><i class="fas fa-book"></i> My Courses</a></li>
            <li><a href="student_dashboard.html#schedule"><i class="fas fa-calendar-alt"></i> Class Schedule</a></li>
            <li><a href="student_dashboard.html#attendance"><i class="fas fa-user-check"></i> Attendance</a></li>
            <li><a href="student_dashboard.html#marks"><i class="fas fa-chart-bar"></i> Marks &amp; Performance</a></li>
            <li><a href="survey_student.html"><i class="fas fa-poll"></i> Surveys</a></li>
            <li><a href="documents.html"><i class="fas fa-folder-open"></i> Documents</a></li>
            <li><a href="assignments.html"><i class="fas fa-tasks"></i> Assignments</a></li>
            <li class="active"><a href="calendar.html"><i class="fas fa-calendar-alt"></i> Calendar</a></li>
        `;
    }

    menu.innerHTML = menuHtml;

    // Faculty specific buttons
    const facultyActions = document.getElementById('faculty-actions-container');
    if (facultyActions) {
        if (role === 'admin' || role === 'faculty') {
            facultyActions.style.display = 'block';
        } else {
            facultyActions.style.display = 'none';
        }
    }
}

// ── Fetch Calendar Events ──
async function fetchMonthEvents() {
    try {
        // Calculate date bounds for the month
        // Pad slightly to fetch overlapping multi-day events
        const firstDayStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-01 00:00`;
        const lastDayCount = new Date(currentYear, currentMonth + 1, 0).getDate();
        const lastDayStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(lastDayCount).padStart(2, '0')} 23:59`;

        let url = `${API_BASE}/calendar/events?start=${encodeURIComponent(firstDayStr)}&end=${encodeURIComponent(lastDayStr)}`;
        
        if (searchQuery) {
            url += `&search=${encodeURIComponent(searchQuery)}`;
        }

        const res = await fetch(url, { headers: getAuthHeaders() });
        if (!res.ok) throw new Error('Failed to fetch events');

        eventsList = await res.json();
        drawCalendar();
        renderAgenda();
    } catch (e) {
        console.error(e);
        showToast('Error loading calendar events.', 'error');
    }
}

// ── Drawing Monthly Date Grid ──
function drawCalendar() {
    const grid = document.getElementById('days-grid-mount');
    const monthDisplay = document.getElementById('current-month-display');
    if (!grid || !monthDisplay) return;

    // Set Month Year title text
    const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    monthDisplay.textContent = `${monthNames[currentMonth]} ${currentYear}`;

    grid.innerHTML = '';

    const firstWeekday = new Date(currentYear, currentMonth, 1).getDay();
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    const daysInPrevMonth = new Date(currentYear, currentMonth, 0).getDate();

    const today = new Date();
    const todayDateOnly = new Date(today.getFullYear(), today.getMonth(), today.getDate());

    // 1. Draw previous month padding days
    for (let i = firstWeekday - 1; i >= 0; i--) {
        const d = daysInPrevMonth - i;
        grid.innerHTML += `<div class="day-cell other-month"><span class="day-number">${d}</span></div>`;
    }

    // 2. Draw active month days
    for (let d = 1; d <= daysInMonth; d++) {
        const cellDate = new Date(currentYear, currentMonth, d);
        const isToday = cellDate.getTime() === todayDateOnly.getTime();
        const isSelected = cellDate.getTime() === new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate()).getTime();

        // Filter events on this specific day
        const dayEvents = eventsList.filter(e => {
            const start = new Date(e.start_date);
            const end = new Date(e.end_date);
            // Day overlap check
            const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate());
            const endDay = new Date(end.getFullYear(), end.getMonth(), end.getDate());
            return cellDate >= startDay && cellDate <= endDay;
        });

        // Apply filters
        const activeEvents = dayEvents.filter(e => {
            if (!filterCategory) return true;
            if (filterCategory === 'holiday') return e.event_type === 'holiday';
            if (filterCategory === 'exams') return ['internal_exam', 'university_exam', 'lab_exam'].includes(e.event_type);
            if (filterCategory === 'deadline') return ['assignment_deadline', 'survey_deadline'].includes(e.event_type);
            if (filterCategory === 'event') return ['project_review', 'seminar', 'workshop', 'event'].includes(e.event_type);
            return true;
        });

        // Indicators HTML
        let indicatorsHtml = '';
        if (activeEvents.length > 0) {
            indicatorsHtml = '<div class="cell-events-indicator">';
            activeEvents.slice(0, 4).forEach(e => {
                let colorClass = 'color-dot-other';
                if (e.event_type === 'holiday') colorClass = 'color-dot-holiday';
                else if (['internal_exam', 'university_exam', 'lab_exam'].includes(e.event_type)) colorClass = 'color-dot-exam';
                else if (['assignment_deadline', 'survey_deadline'].includes(e.event_type)) colorClass = 'color-dot-deadline';
                else if (['project_review', 'seminar', 'workshop'].includes(e.event_type)) colorClass = 'color-dot-seminar';
                else if (e.event_type === 'event') colorClass = 'color-dot-event';
                
                // Allow customized override colors
                if (e.event_color === 'red') colorClass = 'color-dot-holiday';
                else if (e.event_color === 'yellow') colorClass = 'color-dot-deadline';
                else if (e.event_color === 'green') colorClass = 'color-dot-seminar';
                else if (e.event_color === 'purple') colorClass = 'color-dot-event';

                indicatorsHtml += `<span class="event-dot ${colorClass}" title="${escapeHtml(e.title)}"></span>`;
            });
            if (activeEvents.length > 4) {
                indicatorsHtml += `<span style="font-size:0.6rem; color:var(--text-muted); line-height:1;">+</span>`;
            }
            indicatorsHtml += '</div>';
        }

        const borderStyle = isSelected ? 'border: 2px solid var(--primary-color);' : '';
        grid.innerHTML += `
            <div class="day-cell ${isToday ? 'today' : ''}" style="${borderStyle}" onclick="selectDay(${d})">
                <span class="day-number">${d}</span>
                ${indicatorsHtml}
            </div>
        `;
    }

    // 3. Draw next month padding days
    const totalCells = firstWeekday + daysInMonth;
    const paddingCellsNeeded = totalCells % 7 === 0 ? 0 : 7 - (totalCells % 7);
    for (let d = 1; d <= paddingCellsNeeded; d++) {
        grid.innerHTML += `<div class="day-cell other-month"><span class="day-number">${d}</span></div>`;
    }
}

// ── Select Day Cell ──
window.selectDay = function(d) {
    selectedDate = new Date(currentYear, currentMonth, d);
    drawCalendar();
    renderAgenda();
};

// ── Agenda Detail Pane Render ──
function renderAgenda() {
    const agendaMount = document.getElementById('agenda-events-mount');
    const agendaLabel = document.getElementById('agenda-date-lbl');
    if (!agendaMount || !agendaLabel) return;

    const opt = { month: 'short', day: 'numeric', year: 'numeric' };
    agendaLabel.textContent = selectedDate.toLocaleDateString(undefined, opt);

    // Filter events overlapping with currently selectedDate
    const selectedDateOnly = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate());
    const dayEvents = eventsList.filter(e => {
        const start = new Date(e.start_date);
        const end = new Date(e.end_date);
        const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate());
        const endDay = new Date(end.getFullYear(), end.getMonth(), end.getDate());
        return selectedDateOnly >= startDay && selectedDateOnly <= endDay;
    });

    agendaMount.innerHTML = '';

    if (dayEvents.length === 0) {
        agendaMount.innerHTML = `<p style="color:var(--text-muted); font-size:0.8rem; text-align:center; padding-top:1.5rem;">No active events scheduled on this day.</p>`;
        return;
    }

    dayEvents.forEach(e => {
        const start = new Date(e.start_date);
        const end = new Date(e.end_date);
        const timeStr = `${start.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})} - ${end.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
        
        let typeBadgeClass = e.event_type;
        if (['internal_exam', 'university_exam', 'lab_exam'].includes(e.event_type)) typeBadgeClass = 'internal_exam';
        
        const audienceText = e.target_class_id ? `Class: ${e.class_section}` : `Audience: ${e.target_role || 'All'}`;
        const draftIndicator = e.status === 'draft' ? '<span class="status-pill draft" style="margin-left:auto;">Draft</span>' : '';

        agendaMount.innerHTML += `
            <div class="agenda-item" onclick="inspectEvent(${e.id})">
                <div style="display:flex; align-items:center; gap:0.5rem; justify-content:space-between; flex-wrap:wrap;">
                    <span class="type-badge ${typeBadgeClass}">${e.event_type.replace('_', ' ')}</span>
                    ${draftIndicator}
                </div>
                <h4 class="agenda-title">${escapeHtml(e.title)}</h4>
                <div class="agenda-time"><i class="far fa-clock"></i> ${timeStr}</div>
                <div class="agenda-meta">
                    <span><i class="fas fa-users"></i> ${escapeHtml(audienceText)}</span>
                </div>
            </div>
        `;
    });
}

// ── Switch Month ──
window.navigateMonth = function(direction) {
    currentMonth += direction;
    if (currentMonth > 11) {
        currentMonth = 0;
        currentYear += 1;
    } else if (currentMonth < 0) {
        currentMonth = 11;
        currentYear -= 1;
    }
    fetchMonthEvents();
};

window.jumpToToday = function() {
    const today = new Date();
    currentYear = today.getFullYear();
    currentMonth = today.getMonth();
    selectedDate = today;
    fetchMonthEvents();
};

// ── Filters & Searches ──
window.filterType = function(category, tabElement) {
    document.querySelectorAll('#category-filters .filter-tab').forEach(btn => btn.classList.remove('active'));
    tabElement.classList.add('active');

    filterCategory = category;
    drawCalendar();
    renderAgenda();
};

let searchTimeout;
window.handleSearch = function() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        searchQuery = document.getElementById('calendar-search').value.trim();
        fetchMonthEvents();
    }, 300);
};

// ── Inspect Event Modal ──
window.inspectEvent = function(eventId) {
    const event = eventsList.find(e => e.id === eventId);
    if (!event) return;

    document.getElementById('inspect-title').textContent = event.title;
    document.getElementById('inspect-desc').textContent = event.description || 'No description provided.';
    
    // Status
    const statusBadge = document.getElementById('inspect-status-badge');
    statusBadge.textContent = event.status;
    statusBadge.className = `status-pill ${event.status}`;

    // Time Label
    const start = new Date(event.start_date);
    const end = new Date(event.end_date);
    const opt = { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' };
    document.getElementById('inspect-time-lbl').textContent = `${start.toLocaleDateString(undefined, opt)} - ${end.toLocaleDateString(undefined, opt)}`;

    // Type and Class badges
    const typeBadge = document.getElementById('inspect-type-badge');
    typeBadge.textContent = event.event_type.replace('_', ' ');
    let typeClass = event.event_type;
    if (['internal_exam', 'university_exam', 'lab_exam'].includes(event.event_type)) typeClass = 'internal_exam';
    typeBadge.className = `type-badge ${typeClass}`;

    const classBadge = document.getElementById('inspect-class-badge');
    if (event.target_class_id) {
        classBadge.style.display = 'inline-flex';
        classBadge.textContent = `Class ${event.class_section}`;
    } else {
        classBadge.style.display = 'none';
    }

    // Linked document
    const docContainer = document.getElementById('inspect-doc-link-container');
    if (event.document_id) {
        docContainer.style.display = 'flex';
        document.getElementById('inspect-doc-filename').textContent = event.doc_filename || 'Linked Notice';
        
        // Setup download click handler
        const downloadBtn = document.getElementById('inspect-doc-download-btn');
        downloadBtn.onclick = (e) => {
            e.preventDefault();
            handleDownload(event.document_id, event.doc_filename);
        };
    } else {
        docContainer.style.display = 'none';
    }

    // Organizer details
    document.getElementById('inspect-organizer').textContent = event.creator_name || 'Admin';

    // Recurrence
    const recContainer = document.getElementById('inspect-recurrence-container');
    if (event.recurrence_pattern && event.recurrence_pattern !== 'none') {
        recContainer.style.display = 'block';
        document.getElementById('inspect-recurrence').textContent = event.recurrence_pattern;
    } else {
        recContainer.style.display = 'none';
    }

    // Dynamic Edit/Delete triggers (Admin or Creator)
    const isOwnerOrAdmin = (role === 'admin' || event.created_by === decodedUserId);
    const editBtn = document.getElementById('inspect-edit-btn');
    const deleteBtn = document.getElementById('inspect-delete-btn');

    if (isOwnerOrAdmin) {
        editBtn.style.display = 'inline-flex';
        deleteBtn.style.display = 'inline-flex';
        editBtn.onclick = () => openEditModal(event);
        deleteBtn.onclick = () => handleDeleteEvent(event.id);
    } else {
        editBtn.style.display = 'none';
        deleteBtn.style.display = 'none';
    }

    document.getElementById('inspect-modal').classList.add('open');
};

window.closeInspectModal = function() {
    document.getElementById('inspect-modal').classList.remove('open');
};

// ── Secure document download integration ──
async function handleDownload(docId, filename) {
    try {
        const res = await fetch(`${API_BASE}/documents/${docId}/download`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Download failed');

        const a = document.createElement('a');
        a.href = data.download_url;
        a.download = filename;
        a.target = '_blank';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        showToast('Download started.', 'success');
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// ── CRUD Modals ──
window.openCreateModal = function() {
    closeInspectModal();
    document.getElementById('modal-title-text').textContent = 'Add Academic Event';
    document.getElementById('event-form').reset();
    document.getElementById('edit-event-id').value = '';
    document.getElementById('event-error').textContent = '';
    
    // Default dates populate (selected date + hour padding)
    const year = selectedDate.getFullYear();
    const month = String(selectedDate.getMonth() + 1).padStart(2, '0');
    const day = String(selectedDate.getDate()).padStart(2, '0');
    document.getElementById('event-start-date').value = `${year}-${month}-${day}T09:00`;
    document.getElementById('event-end-date').value = `${year}-${month}-${day}T10:00`;

    populateModalDropdowns();
    document.getElementById('event-modal').classList.add('open');
};

function openEditModal(event) {
    closeInspectModal();
    document.getElementById('modal-title-text').textContent = 'Edit Academic Event';
    document.getElementById('edit-event-id').value = event.id;
    document.getElementById('event-error').textContent = '';

    document.getElementById('event-title').value = event.title;
    document.getElementById('event-desc').value = event.description || '';
    document.getElementById('event-type').value = event.event_type;
    document.getElementById('event-color').value = event.event_color || 'indigo';
    
    // Format dates to datetime-local values
    document.getElementById('event-start-date').value = event.start_date.substring(0, 16);
    document.getElementById('event-end-date').value = event.end_date.substring(0, 16);

    document.getElementById('event-status').value = event.status;
    document.getElementById('event-recurrence').value = event.recurrence_pattern || 'none';

    populateModalDropdowns(event);
    document.getElementById('event-modal').classList.add('open');
}

window.closeEventModal = function() {
    document.getElementById('event-modal').classList.remove('open');
};

// Handle event type changes to automatically scope target parameters
window.handleEventTypeChange = function() {
    const type = document.getElementById('event-type').value;
    const colorSelect = document.getElementById('event-color');
    const roleSelect = document.getElementById('event-target-role');

    // Auto colors mapping
    if (type === 'holiday') {
        colorSelect.value = 'red';
        roleSelect.value = 'all';
    } else if (['internal_exam', 'university_exam', 'lab_exam'].includes(type)) {
        colorSelect.value = 'indigo';
        roleSelect.value = 'student';
    } else if (['assignment_deadline', 'survey_deadline'].includes(type)) {
        colorSelect.value = 'yellow';
        roleSelect.value = 'student';
    } else if (['seminar', 'workshop', 'project_review'].includes(type)) {
        colorSelect.value = 'green';
    } else if (type === 'event') {
        colorSelect.value = 'purple';
    }
};

window.handleTargetRoleChange = function() {
    // If targeting admins only, usually class selection is cleared/disabled
    const roleVal = document.getElementById('event-target-role').value;
    const classSelect = document.getElementById('event-target-class');
    if (roleVal === 'admin') {
        classSelect.value = '';
        classSelect.disabled = true;
    } else {
        classSelect.disabled = false;
    }
};

// Populate Classes and Documents lists dynamically inside Modal
async function populateModalDropdowns(existingEvent = null) {
    const classSelect = document.getElementById('event-target-class');
    const docSelect = document.getElementById('event-document-id');

    // For faculty, target class is mandatory so they can only target classes they teach
    classSelect.innerHTML = '<option value="">Institution-Wide</option>';
    if (role === 'faculty') {
        classSelect.innerHTML = ''; // Institution-wide disabled for faculty
    }

    try {
        // 1. Load classes
        let classesRes;
        if (role === 'admin') {
            classesRes = await fetch(`${API_BASE}/admin/classes`, { headers: getAuthHeaders() });
        } else {
            classesRes = await fetch(`${API_BASE}/faculty/my-classes`, { headers: getAuthHeaders() });
        }
        
        if (classesRes.ok) {
            const classes = await classesRes.json();
            classes.forEach(c => {
                const classId = c.class_id || c.id;
                const text = `${c.department} | Sem ${c.semester} | Sec ${c.section}`;
                classSelect.innerHTML += `<option value="${classId}">${escapeHtml(text)}</option>`;
            });
        }
        
        if (existingEvent) {
            classSelect.value = existingEvent.target_class_id || '';
        }

        // 2. Load Documents
        docSelect.innerHTML = '<option value="">No Document</option>';
        const docsRes = await fetch(`${API_BASE}/documents`, { headers: getAuthHeaders() });
        if (docsRes.ok) {
            const docs = await docsRes.json();
            docs.forEach(d => {
                docSelect.innerHTML += `<option value="${d.id}">${escapeHtml(d.title)} (${escapeHtml(d.original_filename)})</option>`;
            });
        }

        if (existingEvent) {
            docSelect.value = existingEvent.document_id || '';
            document.getElementById('event-target-role').value = existingEvent.target_role || 'all';
        }
    } catch (e) {
        console.error('Dropdown population failed', e);
    }
}

// ── Submit Event Form ──
window.handleEventSubmit = async function(e) {
    e.preventDefault();

    const editId = document.getElementById('edit-event-id').value;
    const title = document.getElementById('event-title').value.trim();
    const description = document.getElementById('event-desc').value.trim();
    const event_type = document.getElementById('event-type').value;
    const event_color = document.getElementById('event-color').value;
    const start_date = document.getElementById('event-start-date').value.replace('T', ' ');
    const end_date = document.getElementById('event-end-date').value.replace('T', ' ');
    const target_role = document.getElementById('event-target-role').value;
    const target_class_id = document.getElementById('event-target-class').value;
    const document_id = document.getElementById('event-document-id').value;
    const status = document.getElementById('event-status').value;
    const recurrence_pattern = document.getElementById('event-recurrence').value;
    const errDiv = document.getElementById('event-error');

    errDiv.textContent = '';

    const payload = {
        title, description, event_type, event_color, start_date, end_date,
        target_role: target_role === 'all' ? null : target_role,
        target_class_id: target_class_id ? parseInt(target_class_id) : null,
        document_id: document_id ? parseInt(document_id) : null,
        status, recurrence_pattern
    };

    const method = editId ? 'PUT' : 'POST';
    const url = editId ? `${API_BASE}/calendar/events/${editId}` : `${API_BASE}/calendar/events`;

    try {
        const res = await fetch(url, {
            method,
            headers: getAuthHeaders(),
            body: jsonStringify(payload)
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Operation failed.');

        showToast(editId ? 'Event updated successfully!' : 'Event created successfully!', 'success');
        closeEventModal();
        fetchMonthEvents();
    } catch (err) {
        errDiv.textContent = err.message;
    }
};

// ── Soft Delete Event ──
async function handleDeleteEvent(eventId) {
    if (!confirm('Are you sure you want to delete this event? It will be soft-cancelled.')) {
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/calendar/events/${eventId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Failed to delete event');

        showToast(data.message, 'success');
        closeInspectModal();
        fetchMonthEvents();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// ── Utility Helpers ──
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

function jsonStringify(obj) {
    return JSON.stringify(obj);
}

// ── Initial Setup ──
document.addEventListener('DOMContentLoaded', () => {
    renderSidebar();
    fetchMonthEvents();
});
