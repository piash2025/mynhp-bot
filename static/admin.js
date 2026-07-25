let adminToken = sessionStorage.getItem('adminToken') || null;
let authChecking = true;
let currentPage = 0;
let allUsers = [];
let currentWithdrawalFilter = '';
let pendingWithdrawalId = null;
let editingPlatformId = null;
let deletingPlatformId = null;
let userGrowthChart = null;
let impressionsChart = null;
let payoutsChart = null;
let platformsPieChart = null;

// ===== TOAST SYSTEM =====
function showToast(message, type) {
    type = type || 'success';
    var icons = { success: '&#10004;', error: '&#10008;', warning: '&#9888;', info: '&#8505;' };
    var container = document.getElementById('toast-container');
    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML = '<span class="toast-icon">' + (icons[type] || '') + '</span>' + message;
    container.appendChild(toast);
    setTimeout(function() { toast.remove(); }, 3000);
}

// ===== LOGIN =====
document.getElementById('login-form').addEventListener('submit', async function(e) {
    e.preventDefault();
    var password = document.getElementById('admin-password').value;
    try {
        var resp = await fetch('/api/admin/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: password }),
        });
        var data = await resp.json();
        if (data.status === 'ok') {
            adminToken = password;
            sessionStorage.setItem('adminToken', password);
            document.getElementById('login-screen').classList.add('hidden');
            document.getElementById('admin-dashboard').classList.remove('hidden');
            loadDashboard();
            showToast('Login successful!', 'success');
        } else {
            document.getElementById('login-error').classList.remove('hidden');
            showToast('Wrong password!', 'error');
        }
    } catch (err) {
        document.getElementById('login-error').classList.remove('hidden');
        showToast('Connection error!', 'error');
    }
});

function logout() {
    adminToken = null;
    sessionStorage.removeItem('adminToken');
    document.getElementById('admin-dashboard').classList.add('hidden');
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('admin-password').value = '';
    showToast('Logged out', 'info');
}

// ===== DASHBOARD =====
async function loadDashboard() {
    await loadStats();
    await loadRates();
    await loadSettings();
    await loadUsers(0);
    await loadWithdrawals();
    await loadFraudLogs();
    loadFraudSettings();
    await loadPlatforms();
    await loadDashboardCharts();
}

async function loadStats() {
    try {
        var resp = await fetch('/api/admin/stats?password=' + adminToken);
        var data = await resp.json();
        document.getElementById('total-users').textContent = data.total_users || 0;
        document.getElementById('total-earnings').textContent = (data.total_earnings || 0).toFixed(4);
        document.getElementById('total-referrals').textContent = data.total_referrals || 0;
        document.getElementById('pending-withdrawals').textContent = data.pending_withdrawals || 0;
        document.getElementById('fraud-alerts').textContent = data.fraud_alerts || 0;

        var pendingTrend = document.getElementById('pending-withdraw-trend');
        if (data.pending_withdrawals > 0) {
            pendingTrend.className = 'stat-trend warn';
            pendingTrend.innerHTML = '&#9650; ' + data.pending_withdrawals + ' pending';
        } else {
            pendingTrend.className = 'stat-trend up';
            pendingTrend.innerHTML = '&#10003; Clear';
        }

        var fraudTrend = document.getElementById('fraud-trend');
        if (data.fraud_alerts > 0) {
            fraudTrend.className = 'stat-trend danger';
            fraudTrend.innerHTML = '&#9650; ' + data.fraud_alerts + ' alerts';
        } else {
            fraudTrend.className = 'stat-trend up';
            fraudTrend.innerHTML = '&#10003; Clean';
        }
    } catch (e) { /* ignore */ }
}

// ===== TABS =====
function switchAdminTab(tab) {
    document.querySelectorAll('.admin-panel').forEach(function(p) { p.classList.remove('active'); });
    document.querySelectorAll('.admin-tab').forEach(function(t) { t.classList.remove('active'); });
    document.getElementById('panel-' + tab).classList.add('active');
    document.querySelector('[data-tab="' + tab + '"]').classList.add('active');
}

// ===== AD RATES =====
var networkNames = { adsgream: 'AdsGram', monetag: 'Monetag', adexium: 'Adexium', bonus: 'Bonus Offer' };
var networkTypes = { adsgream: 'Rewarded Ad', monetag: 'Interstitial Ad', adexium: 'Banner Ad', bonus: 'Special Offer' };

async function loadRates() {
    try {
        var resp = await fetch('/api/admin/rates?password=' + adminToken);
        var rates = await resp.json();
        var container = document.getElementById('rates-list');
        container.innerHTML = '';
        rates.forEach(function(rate) {
            container.innerHTML += '<div class="rate-card">' +
                '<div><div class="network-name">' + (networkNames[rate.network] || rate.network) + '</div>' +
                '<div class="network-type">' + (networkTypes[rate.network] || 'Ad') + '</div></div>' +
                '<div><label>Reward (USDT)</label>' +
                '<input type="number" step="0.000001" value="' + rate.rate + '" data-network="' + rate.network + '" data-field="rate"></div>' +
                '<div><label>Daily Limit</label>' +
                '<input type="number" value="' + rate.daily_limit + '" data-network="' + rate.network + '" data-field="daily_limit"></div>' +
                '<div><label>Enabled</label><div class="toggle">' +
                '<input type="checkbox" ' + (rate.enabled ? 'checked' : '') + ' data-network="' + rate.network + '" data-field="enabled" onchange="toggleRate(this)">' +
                '<span class="slider"></span></div></div></div>';
        });
    } catch (e) { /* ignore */ }
}

function toggleRate(checkbox) {
    checkbox.value = checkbox.checked ? 1 : 0;
}

async function saveAllRates() {
    var cards = document.querySelectorAll('.rate-card');
    for (var i = 0; i < cards.length; i++) {
        var card = cards[i];
        var rateInput = card.querySelector('[data-field="rate"]');
        var limitInput = card.querySelector('[data-field="daily_limit"]');
        var enabledInput = card.querySelector('[data-field="enabled"]');
        var network = rateInput.dataset.network;
        await fetch('/api/admin/rates/' + network, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                password: adminToken,
                rate: parseFloat(rateInput.value),
                daily_limit: parseInt(limitInput.value),
                enabled: enabledInput.checked ? 1 : 0,
            }),
        });
    }
    showToast('All rates saved successfully!', 'success');
}

// ===== SETTINGS =====
async function loadSettings() {
    try {
        var resp = await fetch('/api/admin/settings?password=' + adminToken);
        var settings = await resp.json();
        document.getElementById('set-referral-reward').value = settings.referral_reward || 0.001;
        document.getElementById('set-min-withdraw').value = settings.min_withdraw || 0.01;
        document.getElementById('set-farm-rate').value = settings.farm_rate || 0.001;
        document.getElementById('set-farm-duration').value = settings.farm_duration_hours || 4;
        document.getElementById('set-admin-password').value = '';
    } catch (e) { /* ignore */ }
}

async function saveSettings() {
    var data = {
        password: adminToken,
        referral_reward: document.getElementById('set-referral-reward').value,
        min_withdraw: document.getElementById('set-min-withdraw').value,
        farm_rate: document.getElementById('set-farm-rate').value,
        farm_duration_hours: document.getElementById('set-farm-duration').value,
    };
    var newPass = document.getElementById('set-admin-password').value;
    if (newPass) data.admin_password = newPass;

    await fetch('/api/admin/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    showToast('Settings saved!', 'success');
}

// ===== USERS =====
async function loadUsers(page) {
    if (page < 0) page = 0;
    currentPage = page;
    try {
        var resp = await fetch('/api/admin/users?password=' + adminToken + '&page=' + page);
        var data = await resp.json();
        allUsers = data.users || [];
        renderUsers(allUsers);
        document.getElementById('page-info').textContent = 'Page ' + (page + 1);
        document.getElementById('prev-page').disabled = page === 0;
        document.getElementById('next-page').disabled = allUsers.length < 50;
    } catch (e) { /* ignore */ }
}

function renderUsers(users) {
    var tbody = document.getElementById('users-table');
    tbody.innerHTML = '';
    users.forEach(function(u) {
        var date = u.created_at ? new Date(u.created_at).toLocaleDateString() : '-';
        tbody.innerHTML += '<tr>' +
            '<td>' + u.user_id + '</td>' +
            '<td>@' + (u.username || '-') + '</td>' +
            '<td>' + (u.first_name || '-') + '</td>' +
            '<td>' + (u.balance || 0).toFixed(4) + '</td>' +
            '<td>' + (u.tasks_done || 0) + '</td>' +
            '<td>' + (u.total_referrals || 0) + '</td>' +
            '<td>' + date + '</td></tr>';
    });
}

function searchUsers() {
    var query = document.getElementById('user-search').value.toLowerCase();
    var filtered = allUsers.filter(function(u) {
        return String(u.user_id).includes(query) ||
            (u.username && u.username.toLowerCase().includes(query)) ||
            (u.first_name && u.first_name.toLowerCase().includes(query));
    });
    renderUsers(filtered);
}

// ===== WITHDRAWALS =====
async function loadWithdrawals() {
    try {
        var url = '/api/admin/withdrawals?password=' + adminToken;
        if (currentWithdrawalFilter) url += '&status=' + currentWithdrawalFilter;
        var resp = await fetch(url);
        var data = await resp.json();

        var stats = data.stats || {};
        document.getElementById('w-pending-count').textContent = (stats.pending || {}).count || 0;
        document.getElementById('w-approved-count').textContent = (stats.approved || {}).count || 0;
        document.getElementById('w-rejected-count').textContent = (stats.rejected || {}).count || 0;
        document.getElementById('w-pending-amount').textContent = ((stats.pending || {}).amount || 0).toFixed(4);

        var tbody = document.getElementById('withdrawals-table');
        tbody.innerHTML = '';
        var withdrawals = data.withdrawals || [];
        if (withdrawals.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text2);padding:30px;">No withdrawal requests</td></tr>';
            return;
        }
        withdrawals.forEach(function(w) {
            var date = w.created_at ? new Date(w.created_at).toLocaleDateString() + ' ' + new Date(w.created_at).toLocaleTimeString() : '-';
            var statusBadge = '<span class="badge badge-' + w.status + '">' + w.status + '</span>';
            var actions = '';
            if (w.status === 'pending') {
                actions = '<div class="action-btns">' +
                    '<button class="btn-approve" onclick="openApproveModal(' + w.id + ', \'' + (w.username || '') + '\', ' + w.amount + ')">&#10004; Approve</button>' +
                    '<button class="btn-reject" onclick="openRejectModal(' + w.id + ', \'' + (w.username || '') + '\', ' + w.amount + ')">&#10008; Reject</button></div>';
            } else if (w.admin_note) {
                actions = '<span style="font-size:11px;color:var(--text2);">' + w.admin_note + '</span>';
            }
            tbody.innerHTML += '<tr>' +
                '<td>#' + w.id + '</td>' +
                '<td>' + (w.username ? '@' + w.username : w.user_id) + '</td>' +
                '<td><strong>' + w.amount.toFixed(4) + ' USDT</strong></td>' +
                '<td>' + (w.payment_method || 'USDT') + '</td>' +
                '<td style="font-size:11px;word-break:break-all;max-width:120px;">' + (w.wallet_address || '-') + '</td>' +
                '<td>' + date + '</td>' +
                '<td>' + statusBadge + '</td>' +
                '<td>' + actions + '</td></tr>';
        });
    } catch (e) { /* ignore */ }
}

function filterWithdrawals(status) {
    currentWithdrawalFilter = status;
    document.querySelectorAll('.filter-btn').forEach(function(b) { b.classList.remove('active'); });
    document.querySelector('[data-filter="' + status + '"]').classList.add('active');
    loadWithdrawals();
}

function openApproveModal(id, username, amount) {
    pendingWithdrawalId = id;
    document.getElementById('approve-info').innerHTML = 'Approve <strong>' + amount.toFixed(4) + ' USDT</strong> withdrawal for <strong>@' + username + '</strong>?';
    document.getElementById('approve-note').value = '';
    document.getElementById('approve-modal').classList.remove('hidden');
}

function openRejectModal(id, username, amount) {
    pendingWithdrawalId = id;
    document.getElementById('reject-info').innerHTML = 'Reject <strong>' + amount.toFixed(4) + ' USDT</strong> withdrawal for <strong>@' + username + '</strong>?';
    document.getElementById('reject-note').value = '';
    document.getElementById('reject-modal').classList.remove('hidden');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.add('hidden');
    pendingWithdrawalId = null;
}

async function confirmApprove() {
    if (!pendingWithdrawalId) return;
    var note = document.getElementById('approve-note').value || 'Approved by admin';
    try {
        await fetch('/api/admin/withdrawals/' + pendingWithdrawalId + '/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: adminToken, note: note }),
        });
        closeModal('approve-modal');
        showToast('Withdrawal approved!', 'success');
        loadWithdrawals();
        loadStats();
    } catch (e) {
        showToast('Error approving withdrawal', 'error');
    }
}

async function confirmReject() {
    if (!pendingWithdrawalId) return;
    var note = document.getElementById('reject-note').value || 'Rejected by admin';
    try {
        await fetch('/api/admin/withdrawals/' + pendingWithdrawalId + '/reject', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: adminToken, note: note }),
        });
        closeModal('reject-modal');
        showToast('Withdrawal rejected', 'warning');
        loadWithdrawals();
        loadStats();
    } catch (e) {
        showToast('Error rejecting withdrawal', 'error');
    }
}

// ===== FRAUD DETECTION =====
async function loadFraudLogs() {
    try {
        var resp = await fetch('/api/admin/fraud-logs?password=' + adminToken);
        var data = await resp.json();

        var stats = data.stats || {};
        document.getElementById('f-total').textContent = stats.total || 0;
        document.getElementById('f-high').textContent = stats.high || 0;
        document.getElementById('f-medium').textContent = stats.medium || 0;

        var tbody = document.getElementById('fraud-logs-table');
        tbody.innerHTML = '';
        var logs = data.logs || [];
        if (logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text2);padding:30px;">No fraud logs - system clean</td></tr>';
            return;
        }
        logs.forEach(function(log) {
            var date = log.created_at ? new Date(log.created_at).toLocaleDateString() + ' ' + new Date(log.created_at).toLocaleTimeString() : '-';
            var severityBadge = '<span class="badge badge-' + log.severity + '">' + log.severity + '</span>';
            tbody.innerHTML += '<tr>' +
                '<td>' + (log.username ? '@' + log.username : log.user_id) + '</td>' +
                '<td><strong>' + (log.activity_type || '-') + '</strong></td>' +
                '<td>' + (log.description || '-') + '</td>' +
                '<td style="font-size:11px;">' + (log.ip_address || '-') + '</td>' +
                '<td>' + severityBadge + '</td>' +
                '<td>' + date + '</td></tr>';
        });
    } catch (e) { /* ignore */ }
}

function loadFraudSettings() {
    fetch('/api/admin/settings?password=' + adminToken)
        .then(function(r) { return r.json(); })
        .then(function(settings) {
            document.getElementById('set-vpn-blocker').checked = settings.vpn_blocker === '1';
            document.getElementById('set-max-ads-minute').value = settings.max_ads_per_minute || 10;
            document.getElementById('set-max-daily-withdrawals').value = settings.max_daily_withdrawals || 3;
        })
        .catch(function() {});
}

function toggleFraudSetting(checkbox) {
    checkbox.value = checkbox.checked ? 1 : 0;
}

async function saveFraudSettings() {
    await fetch('/api/admin/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            password: adminToken,
            vpn_blocker: document.getElementById('set-vpn-blocker').checked ? '1' : '0',
            max_ads_per_minute: document.getElementById('set-max-ads-minute').value,
            max_daily_withdrawals: document.getElementById('set-max-daily-withdrawals').value,
        }),
    });
    showToast('Fraud settings saved!', 'success');
}

// Close modals on backdrop click
document.getElementById('approve-modal').addEventListener('click', function(e) {
    if (e.target === this) closeModal('approve-modal');
});
document.getElementById('reject-modal').addEventListener('click', function(e) {
    if (e.target === this) closeModal('reject-modal');
});
document.getElementById('platform-modal').addEventListener('click', function(e) {
    if (e.target === this) closeModal('platform-modal');
});
document.getElementById('delete-platform-modal').addEventListener('click', function(e) {
    if (e.target === this) closeModal('delete-platform-modal');
});

// ===== DASHBOARD CHARTS =====
function formatShortDate(dateStr) {
    var d = new Date(dateStr);
    return (d.getMonth() + 1) + '/' + d.getDate();
}

async function loadDashboardCharts() {
    try {
        var resp = await fetch('/api/admin/dashboard?password=' + adminToken + '&days=30');
        var data = await resp.json();
        var summary = data.summary || {};
        var daily = data.daily || [];

        document.getElementById('d-total-users').textContent = summary.total_users || 0;
        document.getElementById('d-new-today').textContent = summary.new_today || 0;
        document.getElementById('d-total-earnings').textContent = (summary.total_earnings || 0).toFixed(4);
        document.getElementById('d-total-platforms').textContent = summary.total_platforms || 0;
        document.getElementById('d-total-payouts').textContent = (summary.total_payouts || 0).toFixed(4);
        document.getElementById('d-pending-count').textContent = summary.pending_payout_count || 0;

        var labels = daily.map(function(d) { return formatShortDate(d.date); });
        var usersData = daily.map(function(d) { return d.total_users || 0; });
        var impressionsData = daily.map(function(d) { return d.impressions || 0; });
        var payoutsData = daily.map(function(d) { return d.payouts || 0; });
        var adViewsData = daily.map(function(d) { return d.ad_views || 0; });

        var chartOpts = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { color: 'rgba(51,65,85,0.3)' }, ticks: { color: '#94a3b8', font: { size: 10 } } }, y: { grid: { color: 'rgba(51,65,85,0.3)' }, ticks: { color: '#94a3b8', font: { size: 10 } } } } };

        if (userGrowthChart) userGrowthChart.destroy();
        userGrowthChart = new Chart(document.getElementById('chart-users'), {
            type: 'line', data: { labels: labels, datasets: [{ label: 'Total Users', data: usersData, borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', fill: true, tension: 0.4, pointRadius: 2 }] }, options: chartOpts
        });

        if (impressionsChart) impressionsChart.destroy();
        impressionsChart = new Chart(document.getElementById('chart-impressions'), {
            type: 'bar', data: { labels: labels, datasets: [{ label: 'Impressions', data: impressionsData, backgroundColor: 'rgba(139,92,246,0.6)', borderRadius: 4 }] }, options: chartOpts
        });

        if (payoutsChart) payoutsChart.destroy();
        payoutsChart = new Chart(document.getElementById('chart-payouts'), {
            type: 'line', data: { labels: labels, datasets: [{ label: 'Payouts (USDT)', data: payoutsData, borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.1)', fill: true, tension: 0.4, pointRadius: 2 }] }, options: chartOpts
        });

        if (platformsPieChart) platformsPieChart.destroy();
        var activeCount = summary.active_platforms || 0;
        var inactiveCount = (summary.total_platforms || 0) - activeCount;
        platformsPieChart = new Chart(document.getElementById('chart-platforms'), {
            type: 'doughnut', data: { labels: ['Active', 'Inactive'], datasets: [{ data: [activeCount, inactiveCount], backgroundColor: ['rgba(34,197,94,0.7)', 'rgba(239,68,68,0.5)'], borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 } } } } }
        });
    } catch (e) { /* ignore */ }
}

// ===== AD PLATFORMS =====
async function loadPlatforms() {
    try {
        var resp = await fetch('/api/admin/platforms?password=' + adminToken);
        var data = await resp.json();
        var platforms = data.platforms || [];
        var container = document.getElementById('platforms-list');
        container.innerHTML = '';

        if (platforms.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:var(--text2);padding:40px;">No platforms added yet. Click "Add New Platform" to start.</div>';
            return;
        }

        platforms.forEach(function(p) {
            container.innerHTML += '<div class="platform-card" id="platform-' + p.id + '">' +
                '<div><div class="p-name">' + p.name + '</div>' +
                '<div class="p-type">' + (p.ad_type || 'Ad') + '</div>' +
                '<div class="p-slug">' + p.slug + '</div>' +
                (p.placement_id ? '<div style="font-size:10px;color:var(--text2);margin-top:4px;">PID: ' + p.placement_id + '</div>' : '') +
                '</div>' +
                '<div><label>Reward</label><input type="number" step="0.000001" value="' + p.rate + '" data-id="' + p.id + '" data-field="rate"></div>' +
                '<div><label>Daily Limit</label><input type="number" value="' + p.daily_limit + '" data-id="' + p.id + '" data-field="daily_limit"></div>' +
                '<div><label>Status</label><div class="toggle">' +
                '<input type="checkbox" ' + (p.enabled ? 'checked' : '') + ' data-id="' + p.id + '" data-field="enabled">' +
                '<span class="slider"></span></div></div>' +
                '<div class="platform-actions">' +
                '<button class="btn-edit" onclick="editPlatform(' + p.id + ')">&#9998; Edit</button>' +
                '<button class="btn-delete" onclick="deletePlatform(' + p.id + ', \'' + p.name.replace(/'/g, "\\'") + '\')">&#128465; Delete</button>' +
                '</div></div>';
        });

        container.querySelectorAll('[data-field="enabled"]').forEach(function(cb) {
            cb.addEventListener('change', function() {
                savePlatformInline(this.dataset.id);
            });
        });
    } catch (e) { /* ignore */ }
}

async function savePlatformInline(id) {
    var card = document.getElementById('platform-' + id);
    if (!card) return;
    var rate = card.querySelector('[data-field="rate"]').value;
    var limit = card.querySelector('[data-field="daily_limit"]').value;
    var enabled = card.querySelector('[data-field="enabled"]').checked ? 1 : 0;

    await fetch('/api/admin/platforms/' + id, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: adminToken, rate: parseFloat(rate), daily_limit: parseInt(limit), enabled: enabled }),
    });
    showToast('Platform updated!', 'success');
}

function openPlatformModal(platformId) {
    editingPlatformId = platformId || null;
    document.getElementById('pf-name').value = '';
    document.getElementById('pf-slug').value = '';
    document.getElementById('pf-type').value = 'Rewarded Ad';
    document.getElementById('pf-script').value = '';
    document.getElementById('pf-placement').value = '';
    document.getElementById('pf-apikey').value = '';
    document.getElementById('pf-rate').value = '0.0005';
    document.getElementById('pf-limit').value = '50';
    document.getElementById('pf-enabled').checked = true;

    if (platformId) {
        document.getElementById('platform-modal-title').innerHTML = '&#9998; Edit Platform';
        fetch('/api/admin/platforms?password=' + adminToken)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var p = (data.platforms || []).find(function(x) { return x.id === platformId; });
                if (p) {
                    document.getElementById('pf-name').value = p.name;
                    document.getElementById('pf-slug').value = p.slug;
                    document.getElementById('pf-type').value = p.ad_type || 'Rewarded Ad';
                    document.getElementById('pf-script').value = p.script_code || '';
                    document.getElementById('pf-placement').value = p.placement_id || '';
                    document.getElementById('pf-apikey').value = p.api_key || '';
                    document.getElementById('pf-rate').value = p.rate;
                    document.getElementById('pf-limit').value = p.daily_limit;
                    document.getElementById('pf-enabled').checked = !!p.enabled;
                }
            });
    } else {
        document.getElementById('platform-modal-title').innerHTML = '&#10010; Add New Platform';
    }

    document.getElementById('platform-modal').classList.remove('hidden');
}

function editPlatform(id) {
    openPlatformModal(id);
}

async function savePlatform() {
    var name = document.getElementById('pf-name').value.trim();
    var slug = document.getElementById('pf-slug').value.trim();
    if (!name || !slug) {
        showToast('Name and Slug are required!', 'error');
        return;
    }

    var payload = {
        password: adminToken,
        name: name,
        slug: slug,
        ad_type: document.getElementById('pf-type').value,
        script_code: document.getElementById('pf-script').value,
        placement_id: document.getElementById('pf-placement').value,
        api_key: document.getElementById('pf-apikey').value,
        rate: parseFloat(document.getElementById('pf-rate').value) || 0.0005,
        daily_limit: parseInt(document.getElementById('pf-limit').value) || 50,
        enabled: document.getElementById('pf-enabled').checked ? 1 : 0,
    };

    try {
        var url = editingPlatformId ? '/api/admin/platforms/' + editingPlatformId : '/api/admin/platforms';
        var resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        var result = await resp.json();
        if (result.error) {
            showToast(result.error, 'error');
            return;
        }
        closeModal('platform-modal');
        showToast(editingPlatformId ? 'Platform updated!' : 'Platform created!', 'success');
        loadPlatforms();
        loadDashboardCharts();
    } catch (e) {
        showToast('Error saving platform', 'error');
    }
}

function deletePlatform(id, name) {
    deletingPlatformId = id;
    document.getElementById('delete-platform-info').innerHTML = 'Delete platform <strong>' + name + '</strong>? This cannot be undone.';
    document.getElementById('delete-platform-modal').classList.remove('hidden');
}

async function confirmDeletePlatform() {
    if (!deletingPlatformId) return;
    try {
        await fetch('/api/admin/platforms/' + deletingPlatformId + '/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: adminToken }),
        });
        closeModal('delete-platform-modal');
        showToast('Platform deleted!', 'warning');
        loadPlatforms();
        loadDashboardCharts();
    } catch (e) {
        showToast('Error deleting platform', 'error');
    }
    deletingPlatformId = null;
}

// ===== AUTH CHECK ON LOAD =====
(function checkAuth() {
    var loader = document.getElementById('auth-loader');
    var loginScreen = document.getElementById('login-screen');
    var dashboard = document.getElementById('admin-dashboard');

    if (!adminToken) {
        authChecking = false;
        loader.classList.add('hidden');
        loginScreen.classList.remove('hidden');
        return;
    }

    fetch('/api/admin/stats?password=' + adminToken)
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (!data.error) {
                authChecking = false;
                loader.classList.add('hidden');
                dashboard.classList.remove('hidden');
                loadDashboard();
            } else {
                authChecking = false;
                sessionStorage.removeItem('adminToken');
                adminToken = null;
                loader.classList.add('hidden');
                loginScreen.classList.remove('hidden');
            }
        })
        .catch(function() {
            authChecking = false;
            sessionStorage.removeItem('adminToken');
            adminToken = null;
            loader.classList.add('hidden');
            loginScreen.classList.remove('hidden');
        });
})();
