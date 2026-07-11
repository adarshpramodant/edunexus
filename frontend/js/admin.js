/* ═══════════════════════════════════════════════════════════════════════════════
   EDUNEXUS ADMIN DASHBOARD — Full User Management
   ═══════════════════════════════════════════════════════════════════════════════ */

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:'
    ? 'http://localhost:5000/api'
    : 'https://edunexus-quw3.onrender.com/api';
const API_URL = `${API_BASE}/admin`;

const token   = localStorage.getItem('token');
const role    = localStorage.getItem('role');
if (!token || role !== 'admin') window.location.href = 'login.html';

function getAuthHeaders() {
    return { 'Content-Type':'application/json', Authorization:`Bearer ${token}` };
}

function showSection(sectionId, anchor) {
    if (typeof event !== 'undefined' && event) {
        event.preventDefault();
    }
    try {
        history.pushState(null, null, '#' + sectionId);
    } catch (e) {
        window.location.hash = sectionId;
    }

    document.querySelectorAll('.section-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-links li').forEach(el => el.classList.remove('active'));
    
    const targetSection = document.getElementById(sectionId);
    if (targetSection) targetSection.classList.add('active');
    
    let activeItem = null;
    if (anchor) {
        activeItem = anchor.parentElement;
    } else if (typeof event !== 'undefined' && event && event.currentTarget) {
        activeItem = event.currentTarget.parentElement;
    } else {
        const link = document.querySelector(`.nav-links a[href="#${sectionId}"]`);
        if (link) activeItem = link.parentElement;
    }
    if (activeItem) activeItem.classList.add('active');

    if (sectionId === 'overview') fetchOverview();
    if (sectionId === 'departments') { fetchDepartments(); fetchSemesters(); }
    if (sectionId === 'classes') { fetchDepartmentsDropdown(); fetchSemestersDropdown(); fetchClasses(); }
    if (sectionId === 'assign-faculty') { fetchAssignFacultyDropdowns(); fetchClassAssignments(); }
    if (sectionId === 'manage-users') { loadStudents(); loadFaculty(); }
}

function logout() { localStorage.clear(); window.location.href = 'login.html'; }

function showMessage(elementId, message, isError = false) {
    const el = document.getElementById(elementId);
    el.textContent = message;
    el.className = `message-container ${isError ? 'message-error' : 'message-success'}`;
    setTimeout(() => { el.style.display = 'none'; el.className = 'message-container'; }, 5000);
}

// ═══════════════════════════════════════════════════════════════════════════════
// TOAST SYSTEM
// ═══════════════════════════════════════════════════════════════════════════════

function toast(msg, type = 'success') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<i class="fas ${type==='success'?'fa-check-circle':'fa-exclamation-circle'}"></i>${esc(msg)}`;
    container.appendChild(el);
    requestAnimationFrame(() => el.classList.add('visible'));
    setTimeout(() => { el.classList.remove('visible'); setTimeout(() => el.remove(), 400); }, 3500);
}

// ═══════════════════════════════════════════════════════════════════════════════
// MODAL SYSTEM
// ═══════════════════════════════════════════════════════════════════════════════

let modalCallback = null;

function openModal(title, desc, bodyHtml, confirmText, callback) {
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-desc').textContent  = desc;
    document.getElementById('modal-body').innerHTML     = bodyHtml;
    document.getElementById('modal-confirm').textContent = confirmText || 'Confirm';
    document.getElementById('modal-error').classList.remove('visible');
    document.getElementById('modal-error').textContent = '';
    modalCallback = callback;
    document.getElementById('modal').classList.add('open');
}

function closeModal() {
    document.getElementById('modal').classList.remove('open');
    modalCallback = null;
}

async function modalConfirm() {
    if (modalCallback) {
        const btn = document.getElementById('modal-confirm');
        btn.disabled = true; btn.textContent = 'Processing…';
        try { await modalCallback(); }
        finally { btn.disabled = false; btn.textContent = 'Confirm'; }
    }
}

function modalError(msg) {
    const el = document.getElementById('modal-error');
    el.textContent = msg; el.classList.add('visible');
}

// ═══════════════════════════════════════════════════════════════════════════════
// SUB-TABS (Manage Users)
// ═══════════════════════════════════════════════════════════════════════════════

function showSubTab(id, btn) {
    document.querySelectorAll('.sub-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
    document.getElementById('sub-' + id).classList.add('active');
    if (btn) btn.classList.add('active');
}

// ═══════════════════════════════════════════════════════════════════════════════
// OVERVIEW
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchOverview() {
    try {
        const res = await fetch(`${API_URL}/dashboard`, { headers: getAuthHeaders() });
        const d   = await res.json();
        if (res.ok) {
            document.getElementById('stat-students').innerText    = d.students;
            document.getElementById('stat-faculty').innerText     = d.faculty;
            document.getElementById('stat-departments').innerText = d.departments;
            document.getElementById('stat-classes').innerText     = d.classes;
        }
    } catch(e) { console.error(e); }
}

// ═══════════════════════════════════════════════════════════════════════════════
// DEPARTMENTS & SEMESTERS
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchDepartments() {
    const res  = await fetch(`${API_URL}/departments`, { headers: getAuthHeaders() });
    const data = await res.json();
    const tbody = document.querySelector('#dept-table tbody');
    tbody.innerHTML = '';
    data.forEach(d => {
        tbody.innerHTML += `<tr><td>${d.id}</td><td>${d.name}</td><td><button onclick="deleteDept(${d.id})" style="background:transparent;border:none;color:var(--error);cursor:pointer;"><i class="fas fa-trash"></i></button></td></tr>`;
    });
}
document.getElementById('add-dept-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('dept-name').value;
    const res = await fetch(`${API_URL}/departments`, { method:'POST', headers:getAuthHeaders(), body:JSON.stringify({name}) });
    if (res.ok) { document.getElementById('dept-name').value=''; fetchDepartments(); toast('Department added'); }
});
async function deleteDept(id) {
    if (!confirm('Delete this department?')) return;
    await fetch(`${API_URL}/departments?id=${id}`, { method:'DELETE', headers:getAuthHeaders() });
    fetchDepartments(); toast('Department deleted');
}

async function fetchSemesters() {
    const res  = await fetch(`${API_URL}/semesters`, { headers: getAuthHeaders() });
    const data = await res.json();
    const tbody = document.querySelector('#sem-table tbody');
    tbody.innerHTML = '';
    data.forEach(s => { tbody.innerHTML += `<tr><td>${s.id}</td><td>Semester ${s.number}</td></tr>`; });
}
document.getElementById('add-sem-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const number = document.getElementById('sem-number').value;
    const res = await fetch(`${API_URL}/semesters`, { method:'POST', headers:getAuthHeaders(), body:JSON.stringify({number}) });
    if (res.ok) { document.getElementById('sem-number').value=''; fetchSemesters(); toast('Semester added'); }
});

// ═══════════════════════════════════════════════════════════════════════════════
// CLASSES
// ═══════════════════════════════════════════════════════════════════════════════

let allClasses = [];

async function fetchDepartmentsDropdown() {
    const res  = await fetch(`${API_URL}/departments`, { headers: getAuthHeaders() });
    const data = await res.json();
    const sel  = document.getElementById('class-dept');
    sel.innerHTML = '<option value="" disabled selected>Select Department</option>';
    data.forEach(d => sel.innerHTML += `<option value="${d.id}">${d.name}</option>`);
}
async function fetchSemestersDropdown() {
    const res  = await fetch(`${API_URL}/semesters`, { headers: getAuthHeaders() });
    const data = await res.json();
    const sel  = document.getElementById('class-sem');
    sel.innerHTML = '<option value="" disabled selected>Select Semester</option>';
    data.forEach(s => sel.innerHTML += `<option value="${s.id}">Semester ${s.number}</option>`);
}
async function fetchClasses() {
    const res  = await fetch(`${API_URL}/classes`, { headers: getAuthHeaders() });
    allClasses = await res.json();
    const tbody = document.querySelector('#classes-table tbody');
    tbody.innerHTML = '';
    allClasses.forEach(c => {
        tbody.innerHTML += `<tr><td>${c.id}</td><td>${c.department}</td><td>Sem ${c.semester}</td><td>${c.section}</td></tr>`;
    });
}
document.getElementById('add-class-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const res = await fetch(`${API_URL}/classes`, {
        method:'POST', headers:getAuthHeaders(),
        body:JSON.stringify({ department_id:document.getElementById('class-dept').value, semester_id:document.getElementById('class-sem').value, section:document.getElementById('class-section').value })
    });
    if (res.ok) { document.getElementById('class-section').value=''; showMessage('class-msg','Class created successfully'); fetchClasses(); toast('Class created'); }
    else { const d = await res.json(); showMessage('class-msg', d.message, true); }
});

// ═══════════════════════════════════════════════════════════════════════════════
// ADD USERS
// ═══════════════════════════════════════════════════════════════════════════════

function toggleStudentFields() {
    const r      = document.getElementById('user-role').value;
    const fields = document.querySelectorAll('.student-field');
    fields.forEach(f => { f.style.display = r==='student'?'block':'none'; f.required = r==='student'; });
    if (r === 'student') populateClassDropdown();
}
async function populateClassDropdown() {
    const res  = await fetch(`${API_URL}/classes`, { headers: getAuthHeaders() });
    const data = await res.json();
    const sel  = document.getElementById('user-class');
    sel.innerHTML = '<option value="" disabled selected>Assign Class</option>';
    data.forEach(c => sel.innerHTML += `<option value="${c.id}">${c.department} - Sem ${c.semester} (${c.section})</option>`);
}
document.getElementById('add-user-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('user-email').value;
    const role  = document.getElementById('user-role').value;
    const payload = { email, role };
    if (role === 'student') { payload.register_number = document.getElementById('user-reg-no').value; payload.class_id = document.getElementById('user-class').value; }
    const res = await fetch(`${API_URL}/users/add`, { method:'POST', headers:getAuthHeaders(), body:JSON.stringify(payload) });
    const d   = await res.json();
    if (res.ok) { showMessage('add-user-msg', d.message); document.getElementById('add-user-form').reset(); toggleStudentFields(); toast(d.message); }
    else showMessage('add-user-msg', d.message, true);
});

// ═══════════════════════════════════════════════════════════════════════════════
// ASSIGN FACULTY
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchAssignFacultyDropdowns() {
    const cRes = await fetch(`${API_URL}/classes`, { headers:getAuthHeaders() });
    const classes = await cRes.json();
    const cSel = document.getElementById('assign-class');
    cSel.innerHTML = '<option value="" disabled selected>Select Class</option>';
    classes.forEach(c => cSel.innerHTML += `<option value="${c.id}">${c.department} - Sem ${c.semester} (${c.section})</option>`);

    const fRes = await fetch(`${API_URL}/faculty`, { headers:getAuthHeaders() });
    const faculty = await fRes.json();
    const fSel = document.getElementById('assign-teacher');
    fSel.innerHTML = '<option value="" disabled selected>Select Faculty</option>';
    faculty.forEach(f => fSel.innerHTML += `<option value="${f.id}">${f.name}</option>`);
}
async function fetchClassAssignments() {
    const res  = await fetch(`${API_URL}/class-assignments`, { headers:getAuthHeaders() });
    const data = await res.json();
    const tbody = document.querySelector('#assign-faculty-table tbody');
    tbody.innerHTML = '';
    data.forEach(a => {
        const roleStr = a.role.split('_').map(w => w[0].toUpperCase()+w.slice(1)).join(' ');
        tbody.innerHTML += `<tr><td>${a.teacher_name}</td><td>${a.class_name}</td><td>${roleStr}</td></tr>`;
    });
}
document.getElementById('assign-faculty-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const res = await fetch(`${API_URL}/assign-faculty`, {
        method:'POST', headers:getAuthHeaders(),
        body:JSON.stringify({ teacher_id:document.getElementById('assign-teacher').value, class_id:document.getElementById('assign-class').value, role:document.getElementById('assign-role').value })
    });
    const d = await res.json();
    if (res.ok) { showMessage('assign-faculty-msg',d.message); document.getElementById('assign-role').value=''; fetchClassAssignments(); toast(d.message); }
    else showMessage('assign-faculty-msg', d.message, true);
});

// ═══════════════════════════════════════════════════════════════════════════════
// MANAGE USERS — STUDENTS
// ═══════════════════════════════════════════════════════════════════════════════

let allStudents = [];

async function loadStudents() {
    const el = document.getElementById('stu-list');
    el.innerHTML = '<p style="color:var(--text-muted)">Loading…</p>';
    try {
        const r = await fetch(`${API_URL}/students`, { headers:getAuthHeaders() });
        allStudents = await r.json();
        // Also refresh class list for modals
        const cr = await fetch(`${API_URL}/classes`, { headers:getAuthHeaders() });
        allClasses = await cr.json();
        renderStudents(allStudents);
    } catch(e) { el.innerHTML = '<p style="color:var(--error)">Failed to load students.</p>'; }
}

function renderStudents(list) {
    const el = document.getElementById('stu-list');
    const stats = document.getElementById('stu-stats');
    const assigned   = list.filter(s => s.class_name);
    const unassigned = list.filter(s => !s.class_name);
    stats.innerHTML = `
        <span class="section-stat"><i class="fas fa-users" style="color:var(--primary-color);"></i> Total: <strong>${list.length}</strong></span>
        <span class="section-stat"><i class="fas fa-check-circle" style="color:var(--success);"></i> Assigned: <strong>${assigned.length}</strong></span>
        <span class="section-stat"><i class="fas fa-exclamation-circle" style="color:#fbbf24;"></i> Unassigned: <strong>${unassigned.length}</strong></span>
    `;

    if (!list.length) { el.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:2rem;">No students found.</p>'; return; }

    el.innerHTML = list.map(s => {
        const initials = (s.name || '??').split(' ').map(w => w[0]).join('').toUpperCase().slice(0,2);
        return `<div class="user-row">
            <div class="user-avatar stu">${initials}</div>
            <div class="user-info">
                <div class="user-name">${esc(s.name)}</div>
                <div class="user-email">${esc(s.register_number)}</div>
            </div>
            <div class="user-details">
                ${s.class_name
                    ? `<span class="detail-chip">${esc(s.class_name)}</span>`
                    : `<span class="detail-chip red">Unassigned</span>`}
            </div>
            <div class="user-actions">
                <button class="act-btn" onclick="openTransferStudent(${s.user_id},'${escJs(s.name)}')"><i class="fas fa-exchange-alt"></i> Transfer</button>
                ${s.class_name
                    ? `<button class="act-btn danger" onclick="removeStudentFromClass(${s.user_id},'${escJs(s.name)}')"><i class="fas fa-unlink"></i> Unlink</button>`
                    : ''}
                <button class="act-btn danger" onclick="dropStudent(${s.user_id},'${escJs(s.name)}')"><i class="fas fa-user-slash"></i> Drop</button>
            </div>
        </div>`;
    }).join('');
}

function filterStudents() {
    const q = document.getElementById('stu-search').value.toLowerCase();
    const filtered = allStudents.filter(s =>
        (s.name||'').toLowerCase().includes(q) ||
        (s.register_number||'').toLowerCase().includes(q) ||
        (s.class_name||'').toLowerCase().includes(q)
    );
    renderStudents(filtered);
}

function openTransferStudent(uid, name) {
    const classOpts = allClasses.map(c => `<option value="${c.id}">${c.department} - Sem ${c.semester} (${c.section})</option>`).join('');
    openModal(
        `Transfer: ${name}`,
        `Select the new class to assign ${name} to.`,
        `<div class="form-group"><label>Destination Class</label><select class="form-control form-select" id="m-transfer-class"><option value="" disabled selected>Select Class…</option>${classOpts}</select></div>`,
        'Transfer',
        async () => {
            const newClass = document.getElementById('m-transfer-class').value;
            if (!newClass) { modalError('Please select a class.'); return; }
            const r = await fetch(`${API_URL}/transfer-student`, { method:'PUT', headers:getAuthHeaders(), body:JSON.stringify({ user_id:uid, new_class_id:newClass }) });
            const d = await r.json();
            if (r.ok) { closeModal(); toast(d.message); loadStudents(); }
            else modalError(d.message);
        }
    );
}

function removeStudentFromClass(uid, name) {
    openModal(
        `Remove from Class: ${name}`,
        `This will unlink ${name} from their current class. Their account and academic records will be preserved.`,
        '',
        'Remove from Class',
        async () => {
            const r = await fetch(`${API_URL}/remove-student-from-class`, { method:'POST', headers:getAuthHeaders(), body:JSON.stringify({ student_id:uid }) });
            const d = await r.json();
            if (r.ok) { closeModal(); toast(d.message); loadStudents(); }
            else modalError(d.message);
        }
    );
}

function dropStudent(uid, name) {
    openModal(
        `Drop Student: ${name}`,
        `⚠ This will permanently remove ${name} from the institution's student roster. Their user account will remain, but all student data will be deleted.`,
        '',
        'Drop Student',
        async () => {
            const r = await fetch(`${API_URL}/remove-student`, { method:'DELETE', headers:getAuthHeaders(), body:JSON.stringify({ user_id:uid }) });
            const d = await r.json();
            if (r.ok) { closeModal(); toast(d.message); loadStudents(); }
            else modalError(d.message);
        }
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MANAGE USERS — FACULTY
// ═══════════════════════════════════════════════════════════════════════════════

let allFacultyDetailed = [];

async function loadFaculty() {
    const el = document.getElementById('fac-list');
    el.innerHTML = '<p style="color:var(--text-muted)">Loading…</p>';
    try {
        const r = await fetch(`${API_URL}/faculty-detailed`, { headers:getAuthHeaders() });
        allFacultyDetailed = await r.json();
        const cr = await fetch(`${API_URL}/classes`, { headers:getAuthHeaders() });
        allClasses = await cr.json();
        renderFaculty(allFacultyDetailed);
    } catch(e) { el.innerHTML = '<p style="color:var(--error)">Failed to load faculty.</p>'; }
}

function renderFaculty(list) {
    const el    = document.getElementById('fac-list');
    const stats = document.getElementById('fac-stats');
    stats.innerHTML = `<span class="section-stat"><i class="fas fa-chalkboard-teacher" style="color:var(--success);"></i> Total: <strong>${list.length}</strong></span>`;

    if (!list.length) { el.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:2rem;">No faculty found.</p>'; return; }

    el.innerHTML = list.map(f => {
        const initials = (f.name || '??').split(' ').map(w => w[0]).join('').toUpperCase().slice(0,2);
        const assignChips = f.assignments.map(a => {
            const roleLabel = a.role.split('_').map(w=>w[0].toUpperCase()+w.slice(1)).join(' ');
            const chipClass = a.role === 'class_teacher' ? 'green' : a.role === 'vice_class_teacher' ? 'amber' : '';
            return `<span class="detail-chip ${chipClass}" title="${roleLabel}">${esc(a.class_name)} (${roleLabel})</span>`;
        }).join('');
        const subChips = f.subjects.map(s =>
            `<span class="detail-chip" style="background:rgba(56,189,248,.1);color:#38bdf8;" title="Subject">${esc(s.subject_name)} — ${esc(s.class_name)}</span>`
        ).join('');

        return `<div class="user-row" style="align-items:flex-start;">
            <div class="user-avatar fac">${initials}</div>
            <div class="user-info">
                <div class="user-name">${esc(f.name)}</div>
                <div class="user-email">${esc(f.email)}</div>
                <div style="margin-top:.5rem;display:flex;flex-wrap:wrap;gap:.35rem;">
                    ${assignChips || '<span class="detail-chip red">No class assignments</span>'}
                </div>
                ${subChips ? `<div style="margin-top:.35rem;display:flex;flex-wrap:wrap;gap:.35rem;">${subChips}</div>` : ''}
            </div>
            <div class="user-actions" style="flex-direction:column;gap:.35rem;">
                ${f.assignments.map(a => `
                    <div style="display:flex;gap:.3rem;">
                        <button class="act-btn" onclick="openTransferFaculty(${f.id},${a.class_id},'${escJs(a.role)}','${escJs(f.name)}','${escJs(a.class_name)}')"><i class="fas fa-exchange-alt"></i></button>
                        <button class="act-btn danger" onclick="removeFacultyFromClass(${f.id},${a.class_id},'${escJs(f.name)}','${escJs(a.class_name)}')"><i class="fas fa-unlink"></i></button>
                    </div>
                `).join('')}
                ${f.subjects.map(s => `
                    <button class="act-btn" style="font-size:.7rem;" onclick="openReassignSubject(${s.subject_id},'${escJs(s.subject_name)}','${escJs(s.class_name)}')"><i class="fas fa-user-edit"></i> Reassign "${esc(s.subject_name)}"</button>
                `).join('')}
            </div>
        </div>`;
    }).join('');
}

function filterFaculty() {
    const q = document.getElementById('fac-search').value.toLowerCase();
    const filtered = allFacultyDetailed.filter(f =>
        (f.name||'').toLowerCase().includes(q) ||
        (f.email||'').toLowerCase().includes(q)
    );
    renderFaculty(filtered);
}

function openTransferFaculty(teacherId, oldClassId, roleStr, name, className) {
    const classOpts = allClasses.map(c => `<option value="${c.id}">${c.department} - Sem ${c.semester} (${c.section})</option>`).join('');
    openModal(
        `Transfer: ${name}`,
        `Move ${name}'s "${roleStr.replace(/_/g,' ')}" assignment from "${className}" to a new class.`,
        `<div class="form-group"><label>Destination Class</label><select class="form-control form-select" id="m-fac-class"><option value="" disabled selected>Select Class…</option>${classOpts}</select></div>`,
        'Transfer',
        async () => {
            const newClass = document.getElementById('m-fac-class').value;
            if (!newClass) { modalError('Please select a class.'); return; }
            if (parseInt(newClass) === oldClassId) { modalError('New class must be different.'); return; }
            const r = await fetch(`${API_URL}/transfer-faculty`, {
                method:'PUT', headers:getAuthHeaders(),
                body:JSON.stringify({ teacher_id:teacherId, old_class_id:oldClassId, new_class_id:newClass, role:roleStr })
            });
            const d = await r.json();
            if (r.ok) { closeModal(); toast(d.message); loadFaculty(); fetchClassAssignments(); }
            else modalError(d.message);
        }
    );
}

function removeFacultyFromClass(teacherId, classId, name, className) {
    openModal(
        `Remove: ${name}`,
        `Remove ${name} from class "${className}"? This will also remove their subject assignments in that class.`,
        '',
        'Remove',
        async () => {
            // Try normal remove first
            let r = await fetch(`${API_URL}/remove-faculty`, {
                method:'DELETE', headers:getAuthHeaders(),
                body:JSON.stringify({ teacher_id:teacherId, class_id:classId })
            });
            let d = await r.json();

            // Handle safety confirmation
            if (r.status === 409 && d.needs_confirmation) {
                if (confirm(d.message + '\n\nProceed anyway?')) {
                    r = await fetch(`${API_URL}/remove-faculty`, {
                        method:'DELETE', headers:getAuthHeaders(),
                        body:JSON.stringify({ teacher_id:teacherId, class_id:classId, force:true })
                    });
                    d = await r.json();
                    if (r.ok) { closeModal(); toast(d.message); loadFaculty(); fetchClassAssignments(); }
                    else modalError(d.message);
                }
                return;
            }

            if (r.ok) { closeModal(); toast(d.message); loadFaculty(); fetchClassAssignments(); }
            else modalError(d.message);
        }
    );
}

function openReassignSubject(subjectId, subjectName, className) {
    // Need all faculty for the dropdown
    const facOpts = allFacultyDetailed.map(f => `<option value="${f.id}">${f.name}</option>`).join('');
    openModal(
        `Reassign: ${subjectName}`,
        `Select a new teacher for "${subjectName}" in ${className}.`,
        `<div class="form-group"><label>New Teacher</label><select class="form-control form-select" id="m-new-teacher"><option value="" disabled selected>Select Faculty…</option>${facOpts}</select></div>`,
        'Reassign',
        async () => {
            const newTeacher = document.getElementById('m-new-teacher').value;
            if (!newTeacher) { modalError('Please select a teacher.'); return; }
            const r = await fetch(`${API_URL}/reassign-subject`, {
                method:'POST', headers:getAuthHeaders(),
                body:JSON.stringify({ subject_id:subjectId, new_teacher_id:newTeacher })
            });
            const d = await r.json();
            if (r.ok) { closeModal(); toast(d.message); loadFaculty(); }
            else modalError(d.message);
        }
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SEMESTER PROMOTION
// ═══════════════════════════════════════════════════════════════════════════════

async function handlePromoteSemester() {
    if (!confirm("Promote all students to next semester?\nEnsure all academic tasks are finalized!")) return;
    const mode = document.getElementById('promote-mode').value;
    const btn  = document.getElementById('promote-btn');
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing…';
    try {
        const res = await fetch(`${API_URL}/promote-semester`, { method:'POST', headers:getAuthHeaders(), body:JSON.stringify({mode}) });
        const d   = await res.json();
        document.getElementById('promote-msg').style.display = 'block';
        if (res.ok) { showMessage('promote-msg', d.message); toast(d.message); }
        else showMessage('promote-msg', d.message, true);
    } catch(e) { showMessage('promote-msg','Server error',true); }
    finally { btn.disabled = false; btn.innerHTML = '<i class="fas fa-level-up-alt"></i> Promote All Students'; }
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

function esc(s)   { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escJs(s) { return String(s||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }

// ── Fetch Upcoming Academic Events ──
async function fetchUpcomingEvents() {
    try {
        const container = document.getElementById('upcoming-events-container');
        const list = document.getElementById('upcoming-events-list');
        if (!container || !list) return;

        const res = await fetch(`${API_BASE}/calendar/events/upcoming`, { headers: getAuthHeaders() });
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

// ── Quick Analytics Metrics ──
async function fetchQuickAnalytics() {
    try {
        const atRiskEl = document.getElementById('admin-quick-at-risk');
        const avgAttEl = document.getElementById('admin-quick-avg-att');
        if (!atRiskEl && !avgAttEl) return;

        const res = await fetch(`${API_BASE}/analytics/summary`, { headers: getAuthHeaders() });
        if (!res.ok) return;

        const data = await res.json();
        if (atRiskEl) {
            atRiskEl.textContent = data.at_risk_count ?? 0;
        }
        if (avgAttEl) {
            avgAttEl.textContent = (data.average_attendance ?? 100.0) + '%';
        }
    } catch (err) {
        console.error('Failed to load quick analytics summary', err);
    }
}

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    const hash = window.location.hash;
    if (hash) {
        const sectionId = hash.substring(1);
        showSection(sectionId);
    } else {
        fetchOverview();
    }
    toggleStudentFields();
    fetchUpcomingEvents();
    fetchQuickAnalytics();
});
