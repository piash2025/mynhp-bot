/* eslint-disable no-undef */
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.expand();
    tg.setHeaderColor('#111827');
    tg.setBackgroundColor('#0a0e17');
}

// ===== USER STATE =====
let currentUser = null;
let balance = 0;
let tasksDone = 0;
let todayEarned = 0;
let totalEarned = 0;
let isFarming = false;
let farmInterval = null;
let farmStartTime = null;
let farmBalance = 0;

// ===== INIT =====
if (tg?.initDataUnsafe?.user) {
    currentUser = tg.initDataUnsafe.user;
    document.getElementById('username').textContent = currentUser.first_name || 'User';
    document.getElementById('user-id').textContent = '@' + (currentUser.username || 'user');

    fetch('/api/user/track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_id: currentUser.id,
            username: currentUser.username,
            first_name: currentUser.first_name,
        }),
    });

    loadStats();
}

async function loadStats() {
    try {
        const resp = await fetch('/api/stats');
        const data = await resp.json();
        document.getElementById('stat-users').textContent = data.total_users || 0;
    } catch (e) { /* ignore */ }
}

// ===== TAB NAVIGATION =====
function switchTab(tabName) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));

    document.getElementById('page-' + tabName).classList.add('active');
    document.querySelector('[data-tab="' + tabName + '"]').classList.add('active');

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
    }
}

// ===== AD WATCHING =====
let currentAdNetwork = null;
let adTimerInterval = null;

function watchAd(network) {
    currentAdNetwork = network;
    const modal = document.getElementById('ad-modal');
    const title = document.getElementById('ad-modal-title');
    const timer = document.getElementById('ad-timer');
    const footer = document.getElementById('ad-modal-footer');
    const body = document.getElementById('ad-modal-body');

    const networkNames = {
        'adsgream': 'AdsGram',
        'monetag': 'Monetag',
        'adexium': 'Adexium',
        'bonus': 'Bonus Offer',
    };

    title.textContent = 'Watching ' + (networkNames[network] || network) + ' Ad...';
    timer.textContent = '5s';
    footer.classList.add('hidden');
    body.innerHTML = `
        <div class="ad-placeholder">
            <span>&#128250;</span>
            <p>Ad is loading...</p>
            <div class="ad-loading-bar">
                <div class="ad-loading-fill"></div>
            </div>
        </div>
    `;
    modal.classList.remove('hidden');

    let seconds = 5;
    adTimerInterval = setInterval(() => {
        seconds--;
        timer.textContent = seconds + 's';
        if (seconds <= 0) {
            clearInterval(adTimerInterval);
            timer.textContent = 'Done!';
            footer.classList.remove('hidden');
            body.innerHTML = `
                <div class="ad-placeholder">
                    <span>&#9989;</span>
                    <p>Ad completed! Ready to claim reward.</p>
                </div>
            `;
        }
    }, 1000);

    fetch('/api/tool/use', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: currentUser?.id, network: network }),
    });
}

function claimReward() {
    const reward = 0.0005;
    balance += reward;
    totalEarned += reward;
    todayEarned += reward;
    tasksDone++;

    updateUI();

    document.getElementById('ad-modal').classList.add('hidden');
    clearInterval(adTimerInterval);

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.notificationOccurred('success');
    }

    fetch('/api/user/balance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_id: currentUser?.id,
            reward: reward,
        }),
    });
}

function updateUI() {
    document.getElementById('balance').textContent = balance.toFixed(4);
    document.getElementById('stat-tasks').textContent = tasksDone;
    document.getElementById('stat-earned').textContent = totalEarned.toFixed(4);
    document.getElementById('stat-today').textContent = todayEarned.toFixed(4);
    document.getElementById('wallet-balance').textContent = balance.toFixed(4);
    document.getElementById('farm-amount').textContent = farmBalance.toFixed(4) + ' USDT';
}

// ===== FARMING =====
function toggleFarm() {
    if (isFarming) {
        stopFarming();
    } else {
        startFarming();
    }
}

function startFarming() {
    isFarming = true;
    farmStartTime = Date.now();
    farmBalance = 0;

    const btn = document.getElementById('farm-btn');
    btn.textContent = 'Stop Farming';
    btn.classList.add('farming');
    document.getElementById('farm-status').textContent = 'Farming in progress...';

    farmInterval = setInterval(() => {
        const elapsed = Date.now() - farmStartTime;
        const totalDuration = 4 * 60 * 60 * 1000;
        const progress = Math.min((elapsed / totalDuration) * 100, 100);

        farmBalance = (progress / 100) * 0.001;
        document.getElementById('farm-progress').style.width = progress + '%';
        document.getElementById('farm-amount').textContent = farmBalance.toFixed(4) + ' USDT';

        const remaining = totalDuration - elapsed;
        if (remaining > 0) {
            const h = Math.floor(remaining / 3600000);
            const m = Math.floor((remaining % 3600000) / 60000);
            const s = Math.floor((remaining % 60000) / 1000);
            document.getElementById('farm-timer').textContent =
                String(h).padStart(2, '0') + ':' +
                String(m).padStart(2, '0') + ':' +
                String(s).padStart(2, '0');
        } else {
            stopFarming();
            balance += farmBalance;
            totalEarned += farmBalance;
            farmBalance = 0;
            updateUI();
        }

        updateUI();
    }, 1000);
}

function stopFarming() {
    isFarming = false;
    clearInterval(farmInterval);
    farmInterval = null;
    farmStartTime = null;

    if (farmBalance > 0) {
        balance += farmBalance;
        totalEarned += farmBalance;
        farmBalance = 0;
    }

    const btn = document.getElementById('farm-btn');
    btn.textContent = 'Start Farming';
    btn.classList.remove('farming');
    document.getElementById('farm-status').textContent = 'Not farming';
    document.getElementById('farm-progress').style.width = '0%';
    document.getElementById('farm-timer').textContent = '00:00:00';
    document.getElementById('farm-amount').textContent = '0.0000 USDT';

    updateUI();
}

// ===== WITHDRAW =====
function withdraw() {
    if (balance < 0.01) {
        alert('Minimum withdrawal is 0.01 USDT. Current: ' + balance.toFixed(4));
        return;
    }
    alert('Withdrawal request submitted! Processing within 24 hours.');
}

// ===== MODAL CLOSE ON BACKDROP =====
document.getElementById('ad-modal')?.addEventListener('click', function (e) {
    if (e.target === this && !adTimerInterval) {
        this.classList.add('hidden');
    }
});
