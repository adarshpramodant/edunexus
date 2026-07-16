// EduNexus — Enterprise Bulk Academic Data Processing Script

const API_BASE = "http://localhost:5000/api"; // backend API target

let currentStep = 1;
let selectedFile = null;
let currentJobId = null;
let currentJobData = null;
let activeMapping = {};
let activeHeaders = [];
let classRoster = []; // cache students for bulk edit
let classesList = [];

// Column database targets
const DB_TARGETS = [
    { field: 'register_number', label: 'Student Register Number (Required)', required: true },
    { field: 'student_name', label: 'Student Full Name (Optional)', required: false },
    { field: 'attendance_status', label: 'Attendance Status (P/AB/DL/SR)', required: false },
    { field: 'cia1', label: 'Internal Assessment 1 (CIA1)', required: false },
    { field: 'cia2', label: 'Internal Assessment 2 (CIA2)', required: false },
    { field: 'cia3', label: 'Internal Assessment 3 (CIA3)', required: false },
    { field: 'assignment', label: 'Assignment Score', required: false },
    { field: 'lab', label: 'Lab / Practical Score', required: false },
    { field: 'project', label: 'Project Score', required: false },
    { field: 'quiz', label: 'Quiz Score', required: false },
    { field: 'seminar', label: 'Seminar Score', required: false },
    { field: 'total', label: 'Total Score', required: false },
    { field: 'percentage', label: 'Percentage (%)', required: false },
    { field: 'grade', label: 'Grade (A+/A/B...)', required: false }
];

document.addEventListener('DOMContentLoaded', () => {
    // 1. Fetch Class Rosters
    fetchAssignedClasses();
    
    // 2. Setup drag and drop
    setupDragAndDrop();
    
    // Set default date for attendance option
    document.getElementById('sel-date').valueAsDate = new Date();
});

// ─────────────────────────────────────────────────────────────────────────────
// DATA FETCHERS
// ─────────────────────────────────────────────────────────────────────────────

async function fetchAssignedClasses() {
    try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_BASE}/faculty/my-classes`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!res.ok) throw new Error('Failed to fetch assigned classes.');
        
        const data = await res.json();
        classesList = Object.values(data);
        
        const selClass = document.getElementById('sel-class');
        selClass.innerHTML = '<option value="" disabled selected>Select Class Section</option>';
        
        classesList.forEach(cls => {
            const opt = document.createElement('option');
            opt.value = cls.class_id;
            opt.textContent = `${cls.department} - Sem ${cls.semester} (Sec ${cls.section})`;
            selClass.appendChild(opt);
        });
        
    } catch (err) {
        console.error(err);
        showToast('Error loading assigned classes.', 'error');
    }
}

async function onClassSelected() {
    const classId = document.getElementById('sel-class').value;
    const selSubject = document.getElementById('sel-subject');
    
    if (!classId) return;
    
    try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_BASE}/faculty/class/${classId}/subjects`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!res.ok) throw new Error('Failed to fetch class subjects.');
        
        const subjects = await res.json();
        selSubject.innerHTML = '<option value="" disabled selected>Select Subject</option>';
        selSubject.disabled = false;
        
        subjects.forEach(sub => {
            const opt = document.createElement('option');
            opt.value = sub.id;
            opt.textContent = `${sub.name} (${sub.code || 'No Code'})`;
            selSubject.appendChild(opt);
        });
        
        // Pre-fetch class student roster for dynamic templating / bulk edits
        const rosterRes = await fetch(`${API_BASE}/faculty/class/${classId}/students`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (rosterRes.ok) {
            classRoster = await rosterRes.json();
        }
        
    } catch (err) {
        console.error(err);
        showToast('Error loading class subjects.', 'error');
    }
}

function onTypeSelected() {
    const type = document.getElementById('sel-type').value;
    const marksOpts = document.querySelectorAll('.marks-opt');
    const attOpts = document.querySelectorAll('.att-opt');
    
    if (type === 'attendance') {
        marksOpts.forEach(el => el.style.display = 'none');
        attOpts.forEach(el => el.style.display = 'block');
    } else if (type === 'marks') {
        marksOpts.forEach(el => el.style.display = 'block');
        attOpts.forEach(el => el.style.display = 'none');
    } else {
        // Combined or Auto-detect
        marksOpts.forEach(el => el.style.display = 'block');
        attOpts.forEach(el => el.style.display = 'block');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// FILE UPLOAD AND DRAG-AND-DROP
// ─────────────────────────────────────────────────────────────────────────────

function setupDragAndDrop() {
    const dropzone = document.getElementById('dropzone');
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, e => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, e => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
        }, false);
    });
    
    dropzone.addEventListener('drop', e => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length) {
            handleFile(files[0]);
        }
    });
}

function triggerFileSelect() {
    document.getElementById('file-input').click();
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length) {
        handleFile(files[0]);
    }
}

function handleFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['csv', 'xlsx', 'xls', 'ods'].includes(ext)) {
        showToast('Unsupported file type. Please upload Excel, CSV or ODS.', 'error');
        return;
    }
    selectedFile = file;
    
    // Update step 2 UI with file info
    document.getElementById('file-name-lbl').textContent = file.name;
    document.getElementById('file-meta-lbl').textContent = `Size: ${(file.size / 1024).toFixed(1)} KB | Type: .${ext.toUpperCase()}`;
    document.getElementById('file-info').style.display = 'flex';
    
    showToast('File selected successfully.', 'success');
}

// ─────────────────────────────────────────────────────────────────────────────
// WIZARD NAVIGATION
// ─────────────────────────────────────────────────────────────────────────────

async function nextStep() {
    if (currentStep === 1) {
        const classId = document.getElementById('sel-class').value;
        const subjectId = document.getElementById('sel-subject').value;
        if (!classId || !subjectId) {
            showToast('Please select Class and Subject first.', 'warning');
            return;
        }
        transitionToStep(2);
    } 
    else if (currentStep === 2) {
        if (!selectedFile) {
            showToast('Please select or upload a document first.', 'warning');
            return;
        }
        
        // Execute API Upload
        const ok = await uploadSpreadsheet();
        if (ok) transitionToStep(3);
    } 
    else if (currentStep === 3) {
        // Collect mapping adjustments
        const mapping = {};
        DB_TARGETS.forEach(target => {
            const val = document.getElementById(`map-field-${target.field}`).value;
            if (val) {
                mapping[target.field] = val;
            }
        });
        
        // Send mapping to Validation engine
        const ok = await startValidation(mapping);
        if (ok) {
            transitionToStep(4);
            pollValidationStatus();
        }
    } 
    else if (currentStep === 4) {
        // Trigger execution
        const ok = await executeImport();
        if (ok) {
            transitionToStep(5);
            pollImportStatus();
        }
    }
    else if (currentStep === 5) {
        // Complete wizard, redirect
        window.location.href = "faculty_dashboard.html";
    }
}

function prevStep() {
    if (currentStep > 1) {
        transitionToStep(currentStep - 1);
    }
}

function transitionToStep(step) {
    document.getElementById(`panel-step-${currentStep}`).classList.remove('active');
    document.getElementById(`step-${currentStep}`).classList.remove('active');
    if (currentStep < step) {
        document.getElementById(`step-${currentStep}`).classList.add('completed');
    }
    
    currentStep = step;
    
    document.getElementById(`panel-step-${currentStep}`).classList.add('active');
    document.getElementById(`step-${currentStep}`).classList.add('active');
    document.getElementById(`step-${currentStep}`).classList.remove('completed');
    
    // Button visibility
    const backBtn = document.getElementById('btn-back');
    const nextBtn = document.getElementById('btn-next');
    
    backBtn.style.visibility = currentStep === 1 || currentStep === 5 ? 'hidden' : 'visible';
    
    if (currentStep === 4) {
        nextBtn.innerHTML = '<i class="fas fa-file-import"></i> Execute Import';
        nextBtn.style.background = '#10b981';
    } else if (currentStep === 5) {
        nextBtn.innerHTML = 'Finish <i class="fas fa-check"></i>';
        nextBtn.style.background = '#6366f1';
        nextBtn.disabled = true; // Wait until completion
    } else {
        nextBtn.innerHTML = 'Continue';
        nextBtn.style.background = '#6366f1';
        nextBtn.disabled = false;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// AJAX API HANDLERS
// ─────────────────────────────────────────────────────────────────────────────

async function uploadSpreadsheet() {
    const classId = document.getElementById('sel-class').value;
    const subjectId = document.getElementById('sel-subject').value;
    const type = document.getElementById('sel-type').value;
    const ay = document.getElementById('sel-ay').value;
    const examType = document.getElementById('sel-exam-type').value;
    const hour = document.getElementById('sel-hour').value;
    const dateVal = document.getElementById('sel-date').value;
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('class_id', classId);
    formData.append('subject_id', subjectId);
    formData.append('import_type', type);
    formData.append('academic_year', ay);
    formData.append('exam_type', examType);
    if (type === 'attendance') {
        formData.append('hour', hour);
        formData.append('date', dateVal);
    }
    
    showToast('Uploading and parsing document...', 'info');
    
    try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_BASE}/import/upload`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });
        
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.message || 'File upload failed.');
        }
        
        const data = await res.json();
        currentJobId = data.job_id;
        activeMapping = data.detected_mapping;
        activeHeaders = data.headers;
        
        // Display AI confidence alerts
        document.getElementById('lbl-ai-confidence').textContent = `${data.confidence}%`;
        document.getElementById('detection-pill').textContent = `Detected type: ${data.detected_type.toUpperCase()}`;
        
        // Populate Step 3 headers mapping rows
        renderHeaderMappings();
        return true;
        
    } catch (err) {
        console.error(err);
        showToast(err.message, 'error');
        return false;
    }
}

function renderHeaderMappings() {
    const mount = document.getElementById('mapping-rows-mount');
    mount.innerHTML = '';
    
    DB_TARGETS.forEach(target => {
        const tr = document.createElement('tr');
        
        // DB target label cell
        const tdFld = document.createElement('td');
        tdFld.innerHTML = `<strong>${target.label}</strong>`;
        tr.appendChild(tdFld);
        
        // Mapped select cell
        const tdSel = document.createElement('td');
        const select = document.createElement('select');
        select.id = `map-field-${target.field}`;
        select.className = 'form-control form-select';
        
        // Default empty option
        select.innerHTML = '<option value="">-- Ignore Column --</option>';
        activeHeaders.forEach(hdr => {
            const opt = document.createElement('option');
            opt.value = hdr;
            opt.textContent = hdr;
            if (activeMapping[target.field] === hdr) {
                opt.selected = true;
            }
            select.appendChild(opt);
        });
        tdSel.appendChild(select);
        tr.appendChild(tdSel);
        
        // Status cell
        const tdStatus = document.createElement('td');
        const matched = activeMapping[target.field];
        if (matched) {
            tdStatus.innerHTML = '<span style="color:#10b981;"><i class="fas fa-check-circle"></i> AI Matched</span>';
        } else {
            tdStatus.innerHTML = '<span style="color:#9ca3af;"><i class="far fa-circle"></i> Unmapped</span>';
        }
        tr.appendChild(tdStatus);
        
        mount.appendChild(tr);
    });
}

async function startValidation(mapping) {
    try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_BASE}/import/validate`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                job_id: currentJobId,
                column_mapping: mapping,
                duplicate_strategy: document.getElementById('sel-conflict-strategy').value
            })
        });
        
        if (!res.ok) throw new Error('Failed to initiate validation engine.');
        
        showToast('Validation queued successfully.', 'success');
        return true;
        
    } catch (err) {
        console.error(err);
        showToast(err.message, 'error');
        return false;
    }
}

function pollValidationStatus() {
    const timer = setInterval(async () => {
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(`${API_BASE}/import/job/${currentJobId}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await res.json();
            
            if (data.status === 'validated') {
                clearInterval(timer);
                showToast('Validation completed.', 'success');
                // Render stats
                document.getElementById('stat-total-rows').textContent = data.total_rows;
                document.getElementById('stat-valid-rows').textContent = data.valid_rows;
                document.getElementById('stat-warning-rows').textContent = data.warning_rows;
                document.getElementById('stat-error-rows').textContent = data.error_rows;
                
                // Fetch editable preview details
                loadPreviewData();
            } else if (data.status === 'failed') {
                clearInterval(timer);
                showToast('Validation failed. Check logs.', 'error');
            }
            
        } catch (err) {
            clearInterval(timer);
            console.error(err);
        }
    }, 1500);
}

async function loadPreviewData() {
    try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_BASE}/import/preview?job_id=${currentJobId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        currentJobData = data.rows;
        
        // Render headers
        const hdrMount = document.getElementById('grid-header-mount');
        hdrMount.innerHTML = '<th>Row</th><th>Register No</th><th>Name</th>';
        
        // Find mapped fields that have data
        const mappedFields = Object.keys(activeMapping);
        mappedFields.forEach(fld => {
            if (fld !== 'register_number' && fld !== 'student_name') {
                const th = document.createElement('th');
                th.textContent = fld.toUpperCase();
                hdrMount.appendChild(th);
            }
        });
        
        // Render rows
        const rowsMount = document.getElementById('grid-rows-mount');
        rowsMount.innerHTML = '';
        
        data.rows.forEach((row, rIdx) => {
            const tr = document.createElement('tr');
            if (row.status === 'error') tr.className = 'row-error';
            else if (row.status === 'warning') tr.className = 'row-warning';
            
            tr.innerHTML = `<td>${row.row_number}</td>
                            <td><input type="text" value="${row.register_number || ''}" onchange="updateCell(${rIdx}, 'register_number', this.value)"></td>
                            <td><input type="text" value="${row.student_name || ''}" onchange="updateCell(${rIdx}, 'student_name', this.value)"></td>`;
            
            mappedFields.forEach(fld => {
                if (fld !== 'register_number' && fld !== 'student_name') {
                    const td = document.createElement('td');
                    const val = row.raw_data[fld] !== undefined ? row.raw_data[fld] : '';
                    td.innerHTML = `<input type="text" value="${val}" onchange="updateCell(${rIdx}, '${fld}', this.value, true)">`;
                    tr.appendChild(td);
                }
            });
            rowsMount.appendChild(tr);
        });
        
        // Render specific errors mount
        const errMount = document.getElementById('validation-errors-mount');
        if (data.errors && data.errors.length) {
            document.getElementById('validation-errors-section').style.display = 'block';
            errMount.innerHTML = '';
            data.errors.forEach(err => {
                const tr = document.createElement('tr');
                tr.innerHTML = `<td>Row ${err.row_number}</td>
                                <td><code>${err.student_identifier || '-'}</code></td>
                                <td style="color:#ef4444;">${err.message}</td>
                                <td>${err.suggestion}</td>`;
                errMount.appendChild(tr);
            });
        } else {
            document.getElementById('validation-errors-section').style.display = 'none';
        }
        
    } catch (err) {
        console.error(err);
        showToast('Error loading editable preview.', 'error');
    }
}

function updateCell(rowIdx, field, val, isRaw = false) {
    if (isRaw) {
        currentJobData[rowIdx].raw_data[field] = val;
    } else {
        currentJobData[rowIdx][field] = val;
    }
}

// Bulk cell actions
function bulkSetAttendance(status) {
    const inputs = document.querySelectorAll('.excel-grid td input');
    // find inputs belonging to attendance_status columns
    // updates cell values
    currentJobData.forEach((row, idx) => {
        if (row.raw_data.attendance_status !== undefined) {
            row.raw_data.attendance_status = status;
        }
    });
    // reload preview HTML
    refreshGridUI();
}

function fillDownMarks() {
    let lastVal = null;
    currentJobData.forEach(row => {
        const marks_keys = ['cia1', 'cia2', 'cia3', 'assignment', 'lab', 'total'];
        marks_keys.forEach(k => {
            if (row.raw_data[k] !== undefined) {
                if (row.raw_data[k] !== null && row.raw_data[k] !== "") {
                    lastVal = row.raw_data[k];
                } else if (lastVal !== null) {
                    row.raw_data[k] = lastVal;
                }
            }
        });
    });
    refreshGridUI();
}

function refreshGridUI() {
    const rowsMount = document.getElementById('grid-rows-mount');
    rowsMount.innerHTML = '';
    
    const mappedFields = Object.keys(activeMapping);
    currentJobData.forEach((row, rIdx) => {
        const tr = document.createElement('tr');
        if (row.status === 'error') tr.className = 'row-error';
        else if (row.status === 'warning') tr.className = 'row-warning';
        
        tr.innerHTML = `<td>${row.row_number}</td>
                        <td><input type="text" value="${row.register_number || ''}" onchange="updateCell(${rIdx}, 'register_number', this.value)"></td>
                        <td><input type="text" value="${row.student_name || ''}" onchange="updateCell(${rIdx}, 'student_name', this.value)"></td>`;
        
        mappedFields.forEach(fld => {
            if (fld !== 'register_number' && fld !== 'student_name') {
                const td = document.createElement('td');
                const val = row.raw_data[fld] !== undefined ? row.raw_data[fld] : '';
                td.innerHTML = `<input type="text" value="${val}" onchange="updateCell(${rIdx}, '${fld}', this.value, true)">`;
                tr.appendChild(td);
            }
        });
        rowsMount.appendChild(tr);
    });
}

async function executeImport() {
    try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_BASE}/import/execute`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                job_id: currentJobId,
                duplicate_strategy: document.getElementById('sel-conflict-strategy').value
            })
        });
        
        if (!res.ok) throw new Error('Failed to execute database transactions.');
        
        showToast('Saving records transactionally...', 'info');
        return true;
        
    } catch (err) {
        console.error(err);
        showToast(err.message, 'error');
        return false;
    }
}

function pollImportStatus() {
    const terminal = document.getElementById('log-terminal-mount');
    terminal.innerHTML = '[SYSTEM] Initializing insertions...\n';
    
    const timer = setInterval(async () => {
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(`${API_BASE}/import/job/${currentJobId}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await res.json();
            
            // Render progress
            document.getElementById('lbl-progress-percent').textContent = `${data.progress_percent}%`;
            document.getElementById('progress-bar-fill').style.width = `${data.progress_percent}%`;
            
            // Append terminal logs
            terminal.innerHTML = '';
            data.logs.forEach(l => {
                terminal.innerHTML += `[${l.level}] ${l.message}\n`;
            });
            terminal.scrollTop = terminal.scrollHeight;
            
            if (data.status === 'completed') {
                clearInterval(timer);
                showToast('Import completed successfully.', 'success');
                document.getElementById('lbl-progress-status').textContent = 'Processing completed!';
                document.getElementById('btn-next').disabled = false;
            } else if (data.status === 'failed') {
                clearInterval(timer);
                showToast('Import transaction failed. Rolled back.', 'error');
                document.getElementById('lbl-progress-status').textContent = 'Transaction failed.';
            }
            
        } catch (err) {
            clearInterval(timer);
            console.error(err);
        }
    }, 1500);
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE DOWNLOADS
// ─────────────────────────────────────────────────────────────────────────────

function downloadRosterTemplate() {
    const classId = document.getElementById('sel-class').value;
    const subjectId = document.getElementById('sel-subject').value;
    const type = document.getElementById('sel-type').value;
    const examType = document.getElementById('sel-exam-type').value;
    
    if (!classId || !subjectId) {
        showToast('Please select Class Section and Subject first.', 'warning');
        return;
    }
    
    const url = `${API_BASE}/import/download-template?class_id=${classId}&subject_id=${subjectId}&type=${type}&exam_type=${examType}`;
    window.open(url, '_blank');
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPACT FEEDBACK NOTIFIER (TOAST)
// ─────────────────────────────────────────────────────────────────────────────

function showToast(msg, type = 'info') {
    // Create element if not exists
    let toast = document.getElementById('notif-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'notif-toast';
        toast.style.cssText = "position:fixed; bottom:20px; right:20px; z-index:9999; padding:1rem 1.5rem; border-radius:0.5rem; color:white; font-weight:600; box-shadow:0 10px 30px rgba(0,0,0,0.3); transition:all 0.3s; transform:translateY(100px); opacity:0;";
        document.body.appendChild(toast);
    }
    
    toast.textContent = msg;
    if (type === 'success') {
        toast.style.background = "linear-gradient(135deg, #10b981, #059669)";
    } else if (type === 'error') {
        toast.style.background = "linear-gradient(135deg, #ef4444, #dc2626)";
    } else if (type === 'warning') {
        toast.style.background = "linear-gradient(135deg, #f59e0b, #d97706)";
    } else {
        toast.style.background = "linear-gradient(135deg, #6366f1, #4f46e5)";
    }
    
    toast.style.transform = "translateY(0)";
    toast.style.opacity = "1";
    
    setTimeout(() => {
        toast.style.transform = "translateY(100px)";
        toast.style.opacity = "0";
    }, 4000);
}
