let adminToken = null;
let currentPage = 0;
let allUsers = [];

// ===== LOGIN =====
document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const password = document.getElementById('admin-password').value;
    try {
        const resp = await fetch('/api/admin/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password }),
        });
        const data = await resp.json();
        if (data.status === 'ok') {
            adminToken = password;
            document.getElementById('login-screen').classList.add('hidden');
            document.getElementById('admin-dashboard').classList.remove('hidden');
            loadDashboard();
        } else {
            document.getElementById('login-error').classList.remove('hidden');
        }
    } catch (err) {
        document.getElementById('login-error').classList.remove('hidden');
    }
});

function logout() {
    adminToken = null;
    document.getElementById('admin-dashboard').classList.add('hidden');
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('admin-password').value = '';
}

// ===== DASHBOARD =====
async function loadDashboard() {
    await loadStats();
    await loadRates();
    await loadSettings();
    await loadUsers(0);
}

async function loadStats() {
    try {
        const resp = await fetch('/api/admin/stats?password=' + adminToken);
        const data = await resp.json();
        document.getElementById('total-users').textContent = data.total_users || 0;
        document.getElementById('total-earnings').textContent = (data.total_earnings || 0).toFixed(4);
        document.getElementById('total-referrals').textContent = data.total_referrals || 0;
    } catch (e) { /* ignore */ }
}

// ===== TABS =====
function switchAdminTab(tab) {
    document.querySelectorAll('.admin-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
    document.getElementById('panel-' + tab).classList.add('active');
    document.querySelector('[data-tab="' + tab + '"]').classList.add('active');
}

// ===== AD RATES =====
const networkNames = {
    adsgream: 'AdsGram',
    monetag: 'Monetag',
    adexium: 'Adexium',
    bonus: 'Bonus Offer',
};

const networkTypes = {
    adsgream: 'Rewarded Ad',
    monetag: 'Interstitial Ad',
    adexium: 'Banner Ad',
    bonus: 'Special Offer',
};

async function loadRates() {
    try {
        const resp = await fetch('/api/admin/rates?password=' + adminToken);
        const rates = await resp.json();
        const container = document.getElementById('rates-list');
        container.innerHTML = '';

        rates.forEach(rate => {
            container.innerHTML += `
                <div class="rate-card">
                    <div>
                        <div class="network-name">${networkNames[rate.network] || rate.network}</div>
                        <div class="network-type">${networkTypes[rate.network] || 'Ad'}</div>
                    </div>
                    <div>
                        <label>Reward (USDT)</label>
                        <input type="number" step="0.0001" value="${rate.rate}" data-network="${rate.network}" data-field="rate">
                    </div>
                    <div>
                        <label>Daily Limit</label>
                        <input type="number" value="${rate.daily_limit}" data-network="${rate.network}" data-field="daily_limit">
                    </div>
                    <div>
                        <label>Enabled</label>
                        <div class="toggle">
                            <input type="checkbox" ${rate.enabled ? 'checked' : ''} data-network="${rate.network}" data-field="enabled" onchange="toggleRate(this)">
                            <span class="slider"></span>
                        </div>
                    </div>
                </div>
            `;
        });
    } catch (e) { /* ignore */ }
}

function toggleRate(checkbox) {
    checkbox.value = checkbox.checked ? 1 : 0;
}

async function saveAllRates() {
    const cards = document.querySelectorAll('.rate-card');
    for (const card of cards) {
        const rateInput = card.querySelector('[data-field="rate"]');
        const limitInput = card.querySelector('[data-field="daily_limit"]');
        const enabledInput = card.querySelector('[data-field="enabled"]');
        const network = rateInput.dataset.network;

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
    alert('Rates saved!');
}

// ===== SETTINGS =====
async function loadSettings() {
    try {
        const resp = await fetch('/api/admin/settings?password=' + adminToken);
        const settings = await resp.json();
        document.getElementById('set-referral-reward').value = settings.referral_reward || 0.001;
        document.getElementById('set-min-withdraw').value = settings.min_withdraw || 0.01;
        document.getElementById('set-farm-rate').value = settings.farm_rate || 0.001;
        document.getElementById('set-farm-duration').value = settings.farm_duration_hours || 4;
        document.getElementById('set-admin-password').value = '';
    } catch (e) { /* ignore */ }
}

async function saveSettings() {
    const data = {
        password: adminToken,
        referral_reward: document.getElementById('set-referral-reward').value,
        min_withdraw: document.getElementById('set-min-withdraw').value,
        farm_rate: document.getElementById('set-farm-rate').value,
        farm_duration_hours: document.getElementById('set-farm-duration').value,
    };
    const newPass = document.getElementById('set-admin-password').value;
    if (newPass) data.admin_password = newPass;

    await fetch('/api/admin/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    alert('Settings saved!');
}

// ===== USERS =====
async function loadUsers(page) {
    if (page < 0) page = 0;
    currentPage = page;
    try {
        const resp = await fetch('/api/admin/users?password=' + adminToken + '&page=' + page);
        const data = await resp.json();
        allUsers = data.users || [];
        renderUsers(allUsers);
        document.getElementById('page-info').textContent = 'Page ' + (page + 1);
        document.getElementById('prev-page').disabled = page === 0;
        document.getElementById('next-page').disabled = allUsers.length < 50;
    } catch (e) { /* ignore */ }
}

function renderUsers(users) {
    const tbody = document.getElementById('users-table');
    tbody.innerHTML = '';
    users.forEach(u => {
        const date = u.created_at ? new Date(u.created_at).toLocaleDateString() : '-';
        tbody.innerHTML += `
            <tr>
                <td>${u.user_id}</td>
                <td>@${u.username || '-'}</td>
                <td>${u.first_name || '-'}</td>
                <td>${(u.balance || 0).toFixed(4)}</td>
                <td>${u.tasks_done || 0}</td>
                <td>${u.total_referrals || 0}</td>
                <td>${date}</td>
            </tr>
        `;
    });
}

function searchUsers() {
    const query = document.getElementById('user-search').value.toLowerCase();
    const filtered = allUsers.filter(u =>
        String(u.user_id).includes(query) ||
        (u.username && u.username.toLowerCase().includes(query)) ||
        (u.first_name && u.first_name.toLowerCase().includes(query))
    );
    renderUsers(filtered);
}
