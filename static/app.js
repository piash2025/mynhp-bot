/* eslint-disable no-undef */
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.expand();
    tg.setHeaderColor('#111827');
    tg.setBackgroundColor('#0a0e17');
}

// ===== SESSION MANAGEMENT =====
function generateSessionId() {
    return 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 15);
}

function getOrCreateSessionId() {
    let sid = localStorage.getItem('session_id');
    if (!sid) {
        sid = generateSessionId();
        localStorage.setItem('session_id', sid);
    }
    return sid;
}

let userSessionId = getOrCreateSessionId();

function showSessionExpiredToast() {
    const existing = document.querySelector('.session-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = 'session-toast';
    toast.innerHTML = '<span>&#9888;</span> Logged out - your account was accessed from another device.';
    document.body.appendChild(toast);
    setTimeout(function() { toast.remove(); }, 4000);
}

function forceLogout() {
    showSessionExpiredToast();
    localStorage.removeItem('session_id');
    localStorage.removeItem('tg_user');
    userSessionId = generateSessionId();
    localStorage.setItem('session_id', userSessionId);
    setTimeout(function() { location.reload(); }, 1500);
}

// ===== BAN INTERCEPTOR =====
function showBannedScreen() {
    document.getElementById('banned-overlay')?.classList.remove('hidden');
    document.querySelector('.bottom-nav')?.classList.add('hidden');
    document.querySelector('.header')?.classList.add('hidden');
    document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
}

const _originalFetch = window.fetch;
window.fetch = function(url, opts) {
    if (opts && opts.body && typeof opts.body === 'string' && opts.headers) {
        try {
            const parsed = JSON.parse(opts.body);
            if (parsed.user_id && !parsed.session_id) {
                parsed.session_id = userSessionId;
                opts.body = JSON.stringify(parsed);
            }
        } catch (e) { /* not json */ }
    }

    if (typeof url === 'string' && url.startsWith('/api/') && !url.includes('/api/admin/') && !url.includes('/api/stats') && !url.includes('/api/config') && !url.includes('/api/fraud/log')) {
        const separator = url.includes('?') ? '&' : '?';
        url = url + separator + 'session_id=' + encodeURIComponent(userSessionId);
    }

    return _originalFetch.apply(this, [url, opts]).then(function(resp) {
        if (resp.status === 403) {
            resp.clone().json().then(function(data) {
                if (data.banned) showBannedScreen();
            }).catch(function() {});
        }
        if (resp.status === 401) {
            resp.clone().json().then(function(data) {
                if (data.session_expired) forceLogout();
            }).catch(function() {});
        }
        return resp;
    });
};

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

// ===== CONFIG (fetched from API) =====
let appConfig = {
    ad_rates: {},
    farm_rate: 0.001,
    farm_duration_hours: 4,
    referral_reward: 0.001,
    min_withdraw: 0.01,
};

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
            session_id: userSessionId,
        }),
    }).then(function(resp) {
        if (resp.status === 403) {
            resp.json().then(function(data) {
                if (data.banned) showBannedScreen();
            });
        }
    });

    loadConfig();
    loadStats();
    loadUserData();
}

async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        appConfig = await resp.json();
        updateAdCardsUI();
    } catch (e) { /* ignore */ }
}

function formatUSDT(amount) {
    if (amount === 0) return '0.00';
    if (amount < 0.0001) return amount.toFixed(6);
    if (amount < 0.01) return amount.toFixed(5);
    return amount.toFixed(4);
}

function updateAdCardsUI() {
    const networks = ['adsgream', 'monetag', 'adexium', 'bonus'];
    networks.forEach(function(net) {
        const rateData = appConfig.ad_rates[net];
        if (!rateData) return;
        const rewardEl = document.getElementById('reward-' + net);
        const limitEl = document.getElementById('limit-' + net);
        const cardEl = document.getElementById('task-' + net);
        if (rewardEl) {
            rewardEl.textContent = '+' + formatUSDT(rateData.rate) + ' USDT';
        }
        if (limitEl) {
            limitEl.textContent = 'Daily limit: ' + rateData.daily_limit + '/' + rateData.daily_limit;
        }
        if (cardEl) {
            cardEl.style.display = rateData.enabled ? '' : 'none';
        }
    });
    document.getElementById('farm-rate-text').textContent = formatUSDT(appConfig.farm_rate);
    document.getElementById('farm-duration-text').textContent = appConfig.farm_duration_hours;
}

async function loadStats() {
    try {
        const resp = await fetch('/api/stats');
        const data = await resp.json();
        document.getElementById('stat-users').textContent = data.total_users || 0;
    } catch (e) { /* ignore */ }
}

async function loadUserData() {
    if (!currentUser) return;
    try {
        const resp = await fetch('/api/user/' + currentUser.id);
        if (resp.status === 403) {
            const data = await resp.json();
            if (data.banned) {
                showBannedScreen();
                return;
            }
        }
        const data = await resp.json();
        if (data.banned) {
            showBannedScreen();
            return;
        }
        if (data.balance !== undefined) {
            balance = data.balance;
        }
        const refCount = data.total_referrals || 0;
        const refEarned = data.referral_earned || 0;

        document.getElementById('ref-count').textContent = refCount;
        document.getElementById('ref-earned').textContent = formatUSDT(refEarned);
        document.getElementById('ref-link').textContent =
            'https://t.me/mynhp_bot?start=ref_' + currentUser.id;

        updateUI();
    } catch (e) { /* ignore */ }
}

function copyRefLink() {
    const linkEl = document.getElementById('ref-link');
    const link = linkEl.textContent;
    navigator.clipboard.writeText(link).then(() => {
        const btn = document.querySelector('.ref-copy-btn');
        btn.innerHTML = '<span>&#10003;</span> Copied!';
        setTimeout(() => { btn.innerHTML = '<span>&#128203;</span> Copy Link'; }, 2000);
    }).catch(() => {
        const range = document.createRange();
        range.selectNode(linkEl);
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);
        document.execCommand('copy');
        window.getSelection().removeAllRanges();
        const btn = document.querySelector('.ref-copy-btn');
        btn.innerHTML = '<span>&#10003;</span> Copied!';
        setTimeout(() => { btn.innerHTML = '<span>&#128203;</span> Copy Link'; }, 2000);
    });
    if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('medium');
    }
}

function shareRefLink() {
    const link = document.getElementById('ref-link').textContent;
    if (tg?.shareURL) {
        tg.shareURL(link, 'Join me on mynhp_bot and earn USDT! 🚀');
    } else {
        navigator.share?.({
            title: 'mynhp_bot Referral',
            text: 'Join me on mynhp_bot and earn USDT!',
            url: link,
        }).catch(() => {});
    }
    if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
    }
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
    if (document.getElementById('banned-overlay') && !document.getElementById('banned-overlay').classList.contains('hidden')) {
        return;
    }
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
    const rateData = appConfig.ad_rates[currentAdNetwork];
    const reward = rateData ? rateData.rate : 0.0005;
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
    }).then(function(resp) {
        if (resp.status === 403) {
            resp.json().then(function(data) {
                if (data.banned) showBannedScreen();
            });
        }
    });
}

function updateUI() {
    document.getElementById('balance').textContent = formatUSDT(balance);
    document.getElementById('stat-tasks').textContent = tasksDone;
    document.getElementById('stat-earned').textContent = formatUSDT(totalEarned);
    document.getElementById('stat-today').textContent = formatUSDT(todayEarned);
    document.getElementById('wallet-balance').textContent = formatUSDT(balance);
    document.getElementById('farm-amount').textContent = formatUSDT(farmBalance) + ' USDT';
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

    const totalDuration = appConfig.farm_duration_hours * 60 * 60 * 1000;
    const totalReward = appConfig.farm_rate;

    farmInterval = setInterval(() => {
        const elapsed = Date.now() - farmStartTime;
        const progress = Math.min((elapsed / totalDuration) * 100, 100);

        farmBalance = (progress / 100) * totalReward;
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
    const min = appConfig.min_withdraw || 0.01;
    if (balance < min) {
        alert('Minimum withdrawal is ' + min.toFixed(4) + ' USDT. Current: ' + balance.toFixed(4));
        return;
    }
    fetch('/api/withdraw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_id: currentUser?.id,
            amount: balance,
            payment_method: 'USDT',
            wallet_address: 'pending',
        }),
    }).then(function(resp) {
        if (resp.status === 403) {
            resp.json().then(function(data) {
                if (data.banned) showBannedScreen();
            });
            return;
        }
        return resp.json();
    }).then(function(data) {
        if (data && data.status === 'ok') {
            alert('Withdrawal request submitted! Processing within 24 hours.');
        } else if (data && data.error) {
            alert(data.error);
        }
    }).catch(function() {});
}

// ===== MODAL CLOSE ON BACKDROP =====
document.getElementById('ad-modal')?.addEventListener('click', function (e) {
    if (e.target === this && !adTimerInterval) {
        this.classList.add('hidden');
    }
});
