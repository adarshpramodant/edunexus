/**
 * EduNexus — Notification Bell Module
 * Include this script AFTER your auth check on any dashboard page.
 *
 * Usage:
 *   1. Add <div id="notif-bell-mount"></div> inside your <header class="topbar">
 *   2. Add <div id="notif-panel-mount"></div> anywhere in <body>
 *   3. Include this script: <script src="js/notifications.js"></script>
 *
 * Requires: token in localStorage, notifApiBase defined or defaults to /api/notifications
 */

const NOTIF_API  = 'https://edunexus-quw3.onrender.com/api/notifications';
const NOTIF_POLL = 20000; // poll every 20 s

let _notifPollTimer = null;
let _notifOpen      = false;
let _notifData      = [];
let _notifUnread    = 0;

// ── Type metadata ─────────────────────────────────────────────────────────────
const NOTIF_META = {
    marks:      { icon: 'fa-chart-bar',     color: '#818cf8', label: 'Marks'      },
    attendance: { icon: 'fa-user-check',    color: '#10b981', label: 'Attendance' },
    survey:     { icon: 'fa-poll',          color: '#f59e0b', label: 'Survey'     },
    system:     { icon: 'fa-bell',          color: '#6366f1', label: 'System'     },
    promotion:  { icon: 'fa-graduation-cap',color: '#c084fc', label: 'Promotion'  },
    assignment: { icon: 'fa-chalkboard',    color: '#38bdf8', label: 'Assignment' }
};

function _notifHeaders() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
    };
}

function _timeAgo(isoStr) {
    if (!isoStr) return '';
    const diff = (Date.now() - new Date(isoStr)) / 1000;
    if (diff < 60)   return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400)return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

// ── Inject HTML ───────────────────────────────────────────────────────────────
function _injectNotifUI() {
    // Bell button into header mount
    const bellMount = document.getElementById('notif-bell-mount');
    if (bellMount) {
        bellMount.innerHTML = `
            <button id="notif-bell-btn" aria-label="Notifications" title="Notifications"
                style="position:relative; background:none; border:none; cursor:pointer; padding:0.4rem 0.5rem;
                       color:var(--text-muted); font-size:1.2rem; transition:color .2s; border-radius:0.5rem;"
                onmouseenter="this.style.color='var(--primary-color)'"
                onmouseleave="this.style.color='var(--text-muted)'"
                onclick="toggleNotifPanel(event)">
                <i class="fas fa-bell"></i>
                <span id="notif-badge" style="
                    display:none; position:absolute; top:-2px; right:-3px;
                    background:linear-gradient(135deg,#ef4444,#dc2626);
                    color:#fff; font-size:0.6rem; font-weight:800;
                    min-width:16px; height:16px; border-radius:8px;
                    padding:0 4px; line-height:16px; text-align:center;
                    box-shadow:0 2px 6px rgba(239,68,68,0.5);
                    animation: notif-pulse 2s infinite;">0</span>
            </button>`;
    }

    // Panel container
    const panelMount = document.getElementById('notif-panel-mount');
    if (panelMount) {
        panelMount.innerHTML = `
            <div id="notif-panel" style="
                display:none; position:fixed; top:70px; right:1.5rem; z-index:9900;
                width:360px; max-height:520px;
                background:#0f172a; border:1px solid rgba(99,102,241,0.2);
                border-radius:1rem; box-shadow:0 24px 60px rgba(0,0,0,0.6);
                display:none; flex-direction:column; overflow:hidden;
                animation: notif-slide-in 0.25s cubic-bezier(.34,1.56,.64,1);">

                <!-- Header -->
                <div style="display:flex; align-items:center; justify-content:space-between;
                            padding:1rem 1.25rem; border-bottom:1px solid rgba(255,255,255,0.06);">
                    <div style="display:flex; align-items:center; gap:0.6rem;">
                        <i class="fas fa-bell" style="color:var(--primary-color); font-size:0.95rem;"></i>
                        <span style="font-weight:700; font-size:1rem; color:var(--text-main);">Notifications</span>
                        <span id="notif-unread-label" style="
                            background:rgba(99,102,241,0.15); color:#818cf8;
                            font-size:0.7rem; font-weight:700; padding:0.1rem 0.5rem;
                            border-radius:1rem; display:none;">0 unread</span>
                    </div>
                    <div style="display:flex; gap:0.5rem; align-items:center;">
                        <button onclick="markAllNotifRead()"
                            style="background:none; border:none; color:var(--text-muted); font-size:0.75rem;
                                   cursor:pointer; font-weight:600; transition:color .15s; padding:0.2rem 0.4rem;
                                   border-radius:0.3rem;"
                            onmouseenter="this.style.color='var(--primary-color)'"
                            onmouseleave="this.style.color='var(--text-muted)'">
                            Mark all read
                        </button>
                        <button onclick="closeNotifPanel()"
                            style="background:none; border:none; color:var(--text-muted); font-size:1.1rem;
                                   cursor:pointer; line-height:1; padding:0.2rem 0.4rem; border-radius:0.3rem;
                                   transition:color .15s;"
                            onmouseenter="this.style.color='var(--text-main)'"
                            onmouseleave="this.style.color='var(--text-muted)'">&#x2715;</button>
                    </div>
                </div>

                <!-- Body -->
                <div id="notif-list" style="
                    overflow-y:auto; flex:1; max-height:420px;
                    scrollbar-width:thin; scrollbar-color:rgba(99,102,241,0.3) transparent;">
                    <p id="notif-empty" style="
                        text-align:center; padding:3rem 1rem;
                        color:rgba(148,163,184,0.5); font-size:0.875rem; display:none;">
                        <i class="fas fa-check-circle" style="font-size:2rem; display:block; margin-bottom:0.5rem;"></i>
                        All caught up!
                    </p>
                    <p id="notif-loading" style="
                        text-align:center; padding:2rem; color:var(--text-muted); font-size:0.875rem;">
                        <i class="fas fa-spinner fa-spin"></i> Loading…
                    </p>
                </div>
            </div>`;
    }

    // Global styles
    if (!document.getElementById('notif-global-styles')) {
        const style = document.createElement('style');
        style.id = 'notif-global-styles';
        style.textContent = `
            @keyframes notif-pulse {
                0%,100% { box-shadow: 0 2px 6px rgba(239,68,68,0.5); }
                50%      { box-shadow: 0 2px 14px rgba(239,68,68,0.9); }
            }
            @keyframes notif-slide-in {
                from { opacity:0; transform:translateY(-10px) scale(0.97); }
                to   { opacity:1; transform:translateY(0) scale(1); }
            }
            .notif-item {
                display: flex; align-items: flex-start; gap: 0.75rem;
                padding: 0.9rem 1.25rem; cursor: pointer;
                border-bottom: 1px solid rgba(255,255,255,0.03);
                transition: background .15s;
                position: relative;
            }
            .notif-item:hover { background: rgba(99,102,241,0.06); }
            .notif-item.unread { background: rgba(99,102,241,0.04); }
            .notif-item.unread::before {
                content: '';
                position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
                background: linear-gradient(180deg,#6366f1,#8b5cf6);
                border-radius: 0 2px 2px 0;
            }
            .notif-icon-wrap {
                width:34px; height:34px; border-radius:50%; flex-shrink:0;
                display:flex; align-items:center; justify-content:center; font-size:0.8rem;
            }
            .notif-content { flex:1; min-width:0; }
            .notif-title {
                font-size:0.82rem; font-weight:700; color:var(--text-main);
                white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
                margin-bottom:0.2rem;
            }
            .notif-item.read .notif-title { color:rgba(148,163,184,0.7); font-weight:500; }
            .notif-msg { font-size:0.75rem; color:var(--text-muted); line-height:1.45; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
            .notif-time { font-size:0.68rem; color:rgba(148,163,184,0.5); margin-top:0.25rem; }
            .notif-del-btn {
                background:none; border:none; color:rgba(148,163,184,0.3);
                font-size:0.75rem; cursor:pointer; padding:0.2rem;
                transition:color .15s; flex-shrink:0; align-self:center;
            }
            .notif-del-btn:hover { color:#ef4444; }
            #notif-list::-webkit-scrollbar { width:4px; }
            #notif-list::-webkit-scrollbar-thumb { background:rgba(99,102,241,0.3); border-radius:2px; }
        `;
        document.head.appendChild(style);
    }
}

// ── Render notifications ───────────────────────────────────────────────────────
function _renderNotifList() {
    const list    = document.getElementById('notif-list');
    const empty   = document.getElementById('notif-empty');
    const loading = document.getElementById('notif-loading');
    if (!list) return;

    loading.style.display = 'none';
    list.innerHTML        = '';
    list.appendChild(empty);   // keep the empty placeholder
    list.appendChild(loading); // keep loading placeholder

    if (_notifData.length === 0) {
        empty.style.display = 'block';
        return;
    }
    empty.style.display = 'none';

    _notifData.forEach(n => {
        const meta = NOTIF_META[n.type] || NOTIF_META.system;
        const item = document.createElement('div');
        item.className = `notif-item ${n.is_read ? 'read' : 'unread'}`;
        item.dataset.id = n.id;
        item.innerHTML  = `
            <div class="notif-icon-wrap" style="background:${meta.color}18;">
                <i class="fas ${meta.icon}" style="color:${meta.color};"></i>
            </div>
            <div class="notif-content">
                <div class="notif-title">${_esc(n.title)}</div>
                <div class="notif-msg">${_esc(n.message)}</div>
                <div class="notif-time">${_timeAgo(n.created_at)}</div>
            </div>
            <button class="notif-del-btn" onclick="deleteNotif(event,${n.id})" title="Dismiss">
                <i class="fas fa-times"></i>
            </button>`;
        item.addEventListener('click', (e) => {
            if (e.target.closest('.notif-del-btn')) return;
            markNotifRead(n.id);
        });
        list.insertBefore(item, empty);
    });
}

function _esc(str) {
    return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── badge + header label ──────────────────────────────────────────────────────
function _updateBadge() {
    const badge  = document.getElementById('notif-badge');
    const label  = document.getElementById('notif-unread-label');
    if (!badge) return;
    if (_notifUnread > 0) {
        badge.textContent  = _notifUnread > 99 ? '99+' : _notifUnread;
        badge.style.display = 'block';
    } else {
        badge.style.display = 'none';
    }
    if (label) {
        if (_notifUnread > 0) {
            label.textContent   = `${_notifUnread} unread`;
            label.style.display = 'inline-block';
        } else {
            label.style.display = 'none';
        }
    }
}

// ── Fetch from API ────────────────────────────────────────────────────────────
async function fetchNotifications(silent = false) {
    try {
        const res  = await fetch(NOTIF_API, { headers: _notifHeaders() });
        if (!res.ok) return;
        const data = await res.json();
        const prevUnread = _notifUnread;

        _notifData   = data.notifications || [];
        _notifUnread = data.unread_count   || 0;

        _updateBadge();
        if (_notifOpen) _renderNotifList();

        // Subtle pulse if new notifications arrived
        if (!silent && _notifUnread > prevUnread) {
            const bellBtn = document.getElementById('notif-bell-btn');
            if (bellBtn) {
                bellBtn.style.color = 'var(--primary-color)';
                setTimeout(() => { bellBtn.style.color = ''; }, 2000);
            }
        }
    } catch (e) { /* silent fail */ }
}

// ── Public API ────────────────────────────────────────────────────────────────
window.toggleNotifPanel = function(e) {
    if (e) e.stopPropagation();
    _notifOpen ? closeNotifPanel() : openNotifPanel();
};

window.openNotifPanel = function() {
    _notifOpen = true;
    const panel = document.getElementById('notif-panel');
    if (panel) { panel.style.display = 'flex'; }
    fetchNotifications(true).then(_renderNotifList);
};

window.closeNotifPanel = function() {
    _notifOpen = false;
    const panel = document.getElementById('notif-panel');
    if (panel) panel.style.display = 'none';
};

window.markNotifRead = async function(id) {
    try {
        await fetch(`${NOTIF_API}/read`, {
            method: 'POST', headers: _notifHeaders(),
            body: JSON.stringify({ notification_id: id })
        });
        const n = _notifData.find(x => x.id === id);
        if (n && !n.is_read) { n.is_read = true; _notifUnread = Math.max(0, _notifUnread - 1); }
        _updateBadge();
        _renderNotifList();
    } catch (e) { /* silent */ }
};

window.markAllNotifRead = async function() {
    try {
        await fetch(`${NOTIF_API}/read-all`, { method: 'POST', headers: _notifHeaders() });
        _notifData.forEach(n => { n.is_read = true; });
        _notifUnread = 0;
        _updateBadge();
        _renderNotifList();
    } catch (e) { /* silent */ }
};

window.deleteNotif = async function(e, id) {
    e.stopPropagation();
    try {
        await fetch(`${NOTIF_API}/${id}`, { method: 'DELETE', headers: _notifHeaders() });
        const idx = _notifData.findIndex(x => x.id === id);
        if (idx !== -1) {
            if (!_notifData[idx].is_read) _notifUnread = Math.max(0, _notifUnread - 1);
            _notifData.splice(idx, 1);
        }
        _updateBadge();
        _renderNotifList();
    } catch (e) { /* silent */ }
};

// ── Close on outside click ────────────────────────────────────────────────────
document.addEventListener('click', (e) => {
    if (!_notifOpen) return;
    const panel = document.getElementById('notif-panel');
    const bell  = document.getElementById('notif-bell-btn');
    if (panel && !panel.contains(e.target) && bell && !bell.contains(e.target)) {
        closeNotifPanel();
    }
});

// ── Init ──────────────────────────────────────────────────────────────────────
function initNotifications() {
    _injectNotifUI();
    fetchNotifications(true);
    // Start polling
    if (_notifPollTimer) clearInterval(_notifPollTimer);
    _notifPollTimer = setInterval(() => fetchNotifications(false), NOTIF_POLL);
}

document.addEventListener('DOMContentLoaded', initNotifications);
