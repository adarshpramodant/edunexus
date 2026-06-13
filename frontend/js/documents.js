// ─────────────────────────────────────────────────────────────────────────────
// EduNexus — Enterprise Document Portal JS
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = 'https://edunexus-quw3.onrender.com/api';
const token = localStorage.getItem('token');
const role = localStorage.getItem('role');
const institutionId = localStorage.getItem('institution_id');

// Guard against unauthenticated access
if (!token || !role) {
    window.location.href = 'login.html';
}

// Global state for filters
let currentCategory = '';
let currentSearch = '';
let showArchived = false;
let studentClassId = null;
let studentClassName = '';
let selectedFile = null;

// Auth Headers helper
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

    // Set page header title
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
            <li class="active"><a href="documents.html"><i class="fas fa-folder-open"></i> Documents</a></li>
        `;
    } else if (role === 'faculty') {
        menuHtml = `
            <li><a href="faculty_dashboard.html#classes"><i class="fas fa-chalkboard-teacher"></i> My Classes</a></li>
            <li><a href="faculty_dashboard.html#attendance"><i class="fas fa-clipboard-check"></i> Attendance</a></li>
            <li><a href="faculty_dashboard.html#marks"><i class="fas fa-star"></i> Marks</a></li>
            <li><a href="survey_manage.html"><i class="fas fa-poll"></i> Surveys</a></li>
            <li class="active"><a href="documents.html"><i class="fas fa-folder-open"></i> Documents</a></li>
        `;
    } else if (role === 'student') {
        menuHtml = `
            <li><a href="student_dashboard.html#courses"><i class="fas fa-book"></i> My Courses</a></li>
            <li><a href="student_dashboard.html#schedule"><i class="fas fa-calendar-alt"></i> Class Schedule</a></li>
            <li><a href="student_dashboard.html#attendance"><i class="fas fa-user-check"></i> Attendance</a></li>
            <li><a href="student_dashboard.html#marks"><i class="fas fa-chart-bar"></i> Marks &amp; Performance</a></li>
            <li><a href="survey_student.html"><i class="fas fa-poll"></i> Surveys</a></li>
            <li class="active"><a href="documents.html"><i class="fas fa-folder-open"></i> Documents</a></li>
        `;
    }

    menu.innerHTML = menuHtml;

    // Archive controls management: Only admins and faculty see archived files toggle
    const archiveToggleContainer = document.getElementById('archive-toggle-container');
    if (archiveToggleContainer) {
        if (role === 'student') {
            archiveToggleContainer.style.display = 'none';
        } else {
            archiveToggleContainer.style.display = 'flex';
        }
    }
}

// Logout helper
window.logout = function() {
    localStorage.clear();
    window.location.href = 'login.html';
};

// ── Fetch Documents ──
async function fetchDocuments() {
    const listContainer = document.getElementById('files-list');
    listContainer.innerHTML = '<p style="color:var(--text-muted); text-align:center; padding:2rem;"><i class="fas fa-circle-notch fa-spin"></i> Loading documents…</p>';

    try {
        let url = `${API_BASE}/documents?is_archived=${showArchived}`;
        if (currentCategory) {
            url += `&category=${currentCategory}`;
        }
        if (currentSearch) {
            url += `&search=${encodeURIComponent(currentSearch)}`;
        }

        const res = await fetch(url, { headers: getAuthHeaders() });
        if (!res.ok) {
            throw new Error(`Failed to load listings: ${res.statusText}`);
        }

        const docs = await res.json();
        listContainer.innerHTML = '';

        if (docs.length === 0) {
            listContainer.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 3rem; background: rgba(30, 41, 59, 0.2); border: 1px dashed var(--border-color); border-radius: 1rem;">
                    <i class="fas fa-folder-open" style="font-size: 3rem; color: var(--text-muted); margin-bottom: 1rem; opacity: 0.4;"></i>
                    <p style="color: var(--text-muted); font-size: 0.95rem; margin: 0;">No documents found matching the filters.</p>
                </div>
            `;
            return;
        }

        // Get current user ID (decoded from token or fetched)
        // We can check user id by getting profile or decoding token if needed. 
        // For simplicity, we can decode JWT to get the user_id or we'll retrieve it dynamically.
        let curUserId = null;
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const payload = JSON.parse(window.atob(base64));
            curUserId = payload.user_id;
        } catch (e) {
            console.error('Failed to parse token payload', e);
        }

        docs.forEach(doc => {
            const ext = doc.original_filename.split('.').pop().toLowerCase();
            let iconClass = 'fa-file';
            let colorType = '';

            if (['pdf'].includes(ext)) { iconClass = 'fa-file-pdf'; colorType = 'pdf'; }
            else if (['doc', 'docx'].includes(ext)) { iconClass = 'fa-file-word'; }
            else if (['xls', 'xlsx', 'csv'].includes(ext)) { iconClass = 'fa-file-excel'; colorType = 'sheet'; }
            else if (['ppt', 'pptx'].includes(ext)) { iconClass = 'fa-file-powerpoint'; }
            else if (['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(ext)) { iconClass = 'fa-file-image'; colorType = 'img'; }
            else if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) { iconClass = 'fa-file-archive'; colorType = 'zip'; }

            // Access buttons
            const isOwnerOrAdmin = (role === 'admin' || doc.uploaded_by === curUserId);
            let actionButtons = '';

            if (isOwnerOrAdmin) {
                const archiveIcon = doc.is_archived ? 'fa-box-open' : 'fa-archive';
                const archiveTitle = doc.is_archived ? 'Unarchive' : 'Archive';
                actionButtons = `
                    <div style="display:flex; gap:0.35rem;">
                        <button class="act-btn" onclick="handleToggleArchive(${doc.id})" title="${archiveTitle}">
                            <i class="fas ${archiveIcon}"></i>
                        </button>
                        <button class="act-btn danger" onclick="handleDelete(${doc.id})" title="Delete File">
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </div>
                `;
            }

            const sizeMb = (doc.file_size / (1024 * 1024)).toFixed(2);
            const createdDate = doc.created_at ? new Date(doc.created_at).toLocaleDateString(undefined, {
                month: 'short', day: 'numeric', year: 'numeric'
            }) : 'N/A';

            listContainer.innerHTML += `
                <div class="doc-card">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <i class="fas ${iconClass} doc-icon ${colorType}"></i>
                        <span class="doc-badge ${doc.visibility}">${doc.visibility}</span>
                    </div>
                    <h4 class="doc-title" title="${escapeHtml(doc.title)}">${escapeHtml(doc.title)}</h4>
                    <p class="doc-desc" title="${escapeHtml(doc.description || '')}">${escapeHtml(doc.description || 'No description provided.')}</p>
                    
                    <div class="doc-meta">
                        <span class="doc-size"><i class="fas fa-hdd"></i> ${sizeMb} MB</span>
                        <span class="doc-size"><i class="fas fa-tag"></i> ${escapeHtml(doc.category)}</span>
                    </div>

                    <div style="font-size:0.7rem; color:var(--text-muted); display:flex; flex-direction:column; gap:0.15rem; margin-top: auto;">
                        <span>Uploaded by: <strong>${escapeHtml(doc.uploader_name)}</strong></span>
                        <span>Date: ${createdDate}</span>
                    </div>

                    <div class="doc-actions">
                        <button class="btn" style="padding:0.45rem 0.95rem; font-size:0.8rem; margin:0;" onclick="handleDownload(${doc.id}, '${escapeHtml(doc.original_filename)}')">
                            <i class="fas fa-download"></i> Download
                        </button>
                        ${actionButtons}
                    </div>
                </div>
            `;
        });

    } catch (err) {
        console.error(err);
        showToast(err.message, 'error');
        listContainer.innerHTML = '<p style="color:var(--error); text-align:center; padding:2rem;">Failed to load documents.</p>';
    }
}

// ── Text Search & Filter Switch ──
let searchTimeout;
window.handleSearch = function() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        currentSearch = document.getElementById('doc-search').value.trim();
        fetchDocuments();
    }, 300);
};

window.filterCategory = function(category, tabElement) {
    // Manage active tab styling
    document.querySelectorAll('#cat-filters .cat-tab').forEach(btn => btn.classList.remove('active'));
    tabElement.classList.add('active');

    currentCategory = category;
    fetchDocuments();
};

window.toggleShowArchived = function() {
    showArchived = document.getElementById('show-archived').checked;
    fetchDocuments();
};

// ── Download File via Signed URL ──
window.handleDownload = async function(docId, filename) {
    try {
        const res = await fetch(`${API_BASE}/documents/${docId}/download`, { headers: getAuthHeaders() });
        const data = await res.json();
        
        if (!res.ok) {
            throw new Error(data.message || 'Failed to download.');
        }

        // Trigger dynamic download
        const a = document.createElement('a');
        a.href = data.download_url;
        a.download = filename;
        a.target = '_blank';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        showToast('Secure signed link generated. Download starting...', 'success');
    } catch (err) {
        console.error(err);
        showToast(err.message, 'error');
    }
};

// ── Archive toggle & Delete ──
window.handleToggleArchive = async function(docId) {
    try {
        const res = await fetch(`${API_BASE}/documents/${docId}/archive`, {
            method: 'PUT',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.message || 'Failed to toggle archive.');
        }

        showToast(data.message, 'success');
        fetchDocuments();
    } catch (err) {
        showToast(err.message, 'error');
    }
};

window.handleDelete = async function(docId) {
    if (!confirm('Are you sure you want to delete this document? It will be soft-deleted.')) {
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/documents/${docId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.message || 'Failed to delete.');
        }

        showToast(data.message, 'success');
        fetchDocuments();
    } catch (err) {
        showToast(err.message, 'error');
    }
};

// ── Modal Management ──
window.openUploadModal = function() {
    document.getElementById('upload-modal').classList.add('open');
    clearUploadForm();
    populateUploaderDropdowns();
};

window.closeUploadModal = function() {
    document.getElementById('upload-modal').classList.remove('open');
};

function clearUploadForm() {
    document.getElementById('upload-form').reset();
    clearSelectedFile();
    document.getElementById('upload-error').style.display = 'none';
    document.getElementById('upload-error').textContent = '';
    document.getElementById('visibility-target-wrapper').style.display = 'none';
    document.getElementById('visibility-target-wrapper').innerHTML = '';
}

// ── Dropzone & File inputs ──
window.triggerFileInput = function() {
    document.getElementById('file-input').click();
};

window.handleFileSelect = function(e) {
    const files = e.target.files;
    if (files.length > 0) {
        const file = files[0];
        
        // Enforce 50MB Upload limit check before sending to server
        const sizeLimit = 50 * 1024 * 1024;
        if (file.size > sizeLimit) {
            alert('File exceeds the 50MB limit.');
            clearSelectedFile();
            return;
        }

        selectedFile = file;
        document.getElementById('selected-file-name').textContent = file.name;
        document.getElementById('selected-file-badge').style.display = 'flex';
        
        // Auto fill title if blank
        const titleInput = document.getElementById('upload-title');
        if (!titleInput.value) {
            const nameWithoutExt = file.name.split('.').slice(0, -1).join('.');
            titleInput.value = nameWithoutExt.replace(/[-_]/g, ' ');
        }
    }
};

window.clearSelectedFile = function() {
    selectedFile = null;
    document.getElementById('file-input').value = '';
    document.getElementById('selected-file-badge').style.display = 'none';
};

// ── Populate Uploader Fields ──
function populateUploaderDropdowns() {
    const catSelect = document.getElementById('upload-category');
    const visSelect = document.getElementById('upload-visibility');

    // Populate categories based on role
    catSelect.innerHTML = '<option value="" disabled selected>Select Category</option>';
    let categories = [];
    if (role === 'student') {
        categories = [
            { val: 'assignment', text: 'Assignment Submission' },
            { val: 'certificate', text: 'Certificate / Diploma' },
            { val: 'project', text: 'Project Document' }
        ];
    } else if (role === 'faculty') {
        categories = [
            { val: 'notes', text: 'Lecture Notes' },
            { val: 'lab_manual', text: 'Lab Manual' },
            { val: 'question_bank', text: 'Question Bank' }
        ];
    } else if (role === 'admin') {
        categories = [
            { val: 'circular', text: 'Circular / Official letter' },
            { val: 'notice', text: 'Public Notice' },
            { val: 'institution', text: 'Institution Document' }
        ];
    }
    categories.forEach(c => {
        catSelect.innerHTML += `<option value="${c.val}">${c.text}</option>`;
    });

    // Populate Visibility based on role
    visSelect.innerHTML = '';
    if (role === 'admin' || role === 'faculty') {
        visSelect.innerHTML = `
            <option value="public" selected>Public (Everyone)</option>
            <option value="role">Role Scoped</option>
            <option value="class">Class Scoped</option>
        `;
    } else {
        // Students usually upload class-scoped (assignments) or public/role (optional)
        visSelect.innerHTML = `
            <option value="class" selected>Class Scoped</option>
            <option value="public">Public (Everyone)</option>
        `;
    }
    
    handleVisibilityChange();
}

// ── Handle Visibility Target Dropdown Changes ──
window.handleVisibilityChange = async function() {
    const visibility = document.getElementById('upload-visibility').value;
    const wrapper = document.getElementById('visibility-target-wrapper');
    wrapper.innerHTML = '';
    wrapper.style.display = 'none';

    if (visibility === 'role') {
        wrapper.style.display = 'block';
        wrapper.innerHTML = `
            <label>Target Role</label>
            <select id="upload-target-role" class="form-control form-select" required>
                <option value="student" selected>Students</option>
                <option value="faculty">Faculty</option>
                <option value="admin">Admins</option>
            </select>
        `;
    } else if (visibility === 'class') {
        wrapper.style.display = 'block';
        
        if (role === 'admin') {
            wrapper.innerHTML = `
                <label>Target Class</label>
                <select id="upload-target-class" class="form-control form-select" required>
                    <option value="" disabled selected>Loading Classes…</option>
                </select>
            `;
            await fetchAndPopulateClassesSelect();
        } else if (role === 'faculty') {
            wrapper.innerHTML = `
                <label>Target Class</label>
                <select id="upload-target-class" class="form-control form-select" required>
                    <option value="" disabled selected>Loading My Classes…</option>
                </select>
            `;
            await fetchAndPopulateClassesSelect();
        } else if (role === 'student') {
            // For students, their class is resolved automatically from profile
            if (studentClassId) {
                wrapper.innerHTML = `
                    <label>Target Class</label>
                    <input type="text" class="form-control" value="${escapeHtml(studentClassName)}" readonly disabled>
                    <input type="hidden" id="upload-target-class" value="${studentClassId}">
                `;
            } else {
                wrapper.innerHTML = `
                    <label>Target Class</label>
                    <div style="color:var(--error); font-size:0.8rem;"><i class="fas fa-exclamation-triangle"></i> You are not assigned to a class. Class-scoped upload disabled.</div>
                    <input type="hidden" id="upload-target-class" value="">
                `;
            }
        }
    }
};

async function fetchAndPopulateClassesSelect() {
    const select = document.getElementById('upload-target-class');
    if (!select) return;

    try {
        let res;
        if (role === 'admin') {
            res = await fetch(`${API_BASE}/admin/classes`, { headers: getAuthHeaders() });
        } else if (role === 'faculty') {
            res = await fetch(`${API_BASE}/faculty/my-classes`, { headers: getAuthHeaders() });
        }

        if (!res.ok) {
            throw new Error('Failed to fetch class listings.');
        }

        const classes = await res.json();
        select.innerHTML = '<option value="" disabled selected>Select Class</option>';

        if (classes.length === 0) {
            select.innerHTML = '<option value="" disabled>No classes available</option>';
            return;
        }

        classes.forEach(c => {
            const classId = c.class_id || c.id;
            const text = `${c.department} | Sem ${c.semester} | Sec ${c.section}`;
            select.innerHTML += `<option value="${classId}">${escapeHtml(text)}</option>`;
        });
    } catch (err) {
        console.error(err);
        select.innerHTML = '<option value="" disabled>Error loading classes</option>';
    }
}

// ── Submit File Upload ──
window.handleUploadSubmit = async function(e) {
    e.preventDefault();

    const title = document.getElementById('upload-title').value.trim();
    const description = document.getElementById('upload-desc').value.trim();
    const category = document.getElementById('upload-category').value;
    const visibility = document.getElementById('upload-visibility').value;
    const errDiv = document.getElementById('upload-error');
    const btn = document.getElementById('upload-btn');

    errDiv.style.display = 'none';
    errDiv.textContent = '';

    if (!selectedFile) {
        errDiv.style.display = 'block';
        errDiv.textContent = 'Please select a file to upload.';
        return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('title', title);
    formData.append('description', description);
    formData.append('category', category);
    formData.append('visibility', visibility);

    if (visibility === 'role') {
        const targetRole = document.getElementById('upload-target-role').value;
        formData.append('target_role', targetRole);
    } else if (visibility === 'class') {
        const targetClass = document.getElementById('upload-target-class').value;
        if (!targetClass) {
            errDiv.style.display = 'block';
            errDiv.textContent = 'A valid target class is required.';
            return;
        }
        formData.append('target_class_id', targetClass);
    }

    // Set loading state
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading…';

    try {
        const res = await fetch(`${API_BASE}/documents`, {
            method: 'POST',
            headers: getAuthHeaders(), // fetch is smart enough to set Content-Type with boundary automatically for FormData
            body: formData
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.message || 'File upload failed.');
        }

        showToast('Document uploaded successfully!', 'success');
        closeUploadModal();
        fetchDocuments();
    } catch (err) {
        console.error(err);
        errDiv.style.display = 'block';
        errDiv.textContent = err.message;
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
};

// ── Fetch Student Profile (To automatically resolve their class_id) ──
async function fetchStudentProfileIfNeeded() {
    if (role !== 'student') return;

    try {
        const res = await fetch(`${API_BASE}/student/profile`, { headers: getAuthHeaders() });
        if (res.ok) {
            const profile = await res.json();
            if (profile && profile.class_id) {
                studentClassId = profile.class_id;
                studentClassName = `${profile.department} | Sem ${profile.semester} | Sec ${profile.section}`;
            }
        }
    } catch (e) {
        console.error('Failed to pre-fetch student profile class', e);
    }
}

// ── Utility Toast & Escape functions ──
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}"></i> ${message}`;
    container.appendChild(toast);

    // Fade-in trigger
    setTimeout(() => toast.classList.add('visible'), 50);

    // Automatically remove after 4.5 seconds
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
document.addEventListener('DOMContentLoaded', async () => {
    renderSidebar();
    await fetchStudentProfileIfNeeded();
    fetchDocuments();
});

// ── Responsive Drawer Toggle ──
window.toggleSidebar = function() {
    const sidebar = document.querySelector('.sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (sidebar && backdrop) {
        sidebar.classList.toggle('open');
        backdrop.classList.toggle('active');
    }
};
