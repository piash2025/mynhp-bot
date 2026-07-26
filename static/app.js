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

function showToast(message) {
    const existing = document.querySelector('.user-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = 'user-toast';
    toast.innerHTML = '<span>&#9888;</span> ' + message;
    toast.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);background:rgba(239,68,68,0.95);color:#fff;padding:12px 20px;border-radius:10px;font-size:14px;font-weight:500;z-index:99999;box-shadow:0 8px 24px rgba(0,0,0,0.4);display:flex;align-items:center;gap:8px;animation:slideIn 0.3s ease;';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function showRewardToast(amount) {
    const existing = document.querySelector('.reward-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = 'reward-toast';
    toast.innerHTML = '&#127881; +' + formatUSDT(amount) + ' USDT added!';
    toast.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);background:rgba(22,163,74,0.95);color:#fff;padding:12px 20px;border-radius:10px;font-size:14px;font-weight:600;z-index:99999;box-shadow:0 8px 24px rgba(0,0,0,0.4);display:flex;align-items:center;gap:8px;animation:slideIn 0.3s ease;';
    document.body.appendChild(toast);
    setTimeout(function() { toast.remove(); }, 2500);
}

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

// ===== BAN / VPN BLOCK INTERCEPTOR =====
function showBannedScreen() {
    document.getElementById('banned-overlay')?.classList.remove('hidden');
    document.querySelector('.bottom-nav')?.classList.add('hidden');
    document.querySelector('.header')?.classList.add('hidden');
    document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
}

function showVPNWarning(message) {
    var banner = document.getElementById('vpn-warning-banner');
    if (banner) {
        banner.classList.remove('hidden');
        banner.querySelector('.vpn-warning-text').textContent = message || 'VPN/Proxy detected. Please disable VPN to continue earning.';
    }
}

function hideVPNWarning() {
    var banner = document.getElementById('vpn-warning-banner');
    if (banner) banner.classList.add('hidden');
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
let userAdStatus = {};

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

    // Silent Telegram initData verification + IP/GeoIP logging
    fetch('/api/user/track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_id: currentUser.id,
            username: currentUser.username,
            first_name: currentUser.first_name,
            session_id: userSessionId,
            init_data: tg.initData || '',
        }),
    }).then(function(resp) {
        return resp.json();
    }).then(function(data) {
        if (data.banned) {
            showBannedScreen();
        } else if (data.vpn_warning) {
            showVPNWarning(data.message);
        } else {
            hideVPNWarning();
        }
    }).catch(function() {});

    loadConfig();
    loadStats();
    loadUserData();
    checkAdCooldown();
    loadAdStatus();

    // Heartbeat: ping server every 30s to track online status
    setInterval(function() {
        if (currentUser && currentUser.id) {
            fetch('/api/user/heartbeat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: currentUser.id }),
            }).catch(function() {});
        }
    }, 30000);
}

async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        appConfig = await resp.json();
        updateAdCardsUI();
    } catch (e) { /* ignore */ }
}

async function loadAdStatus() {
    if (!currentUser?.id) return;
    try {
        const resp = await fetch('/api/user/ad-status/' + currentUser.id);
        const data = await resp.json();
        if (data.status) {
            userAdStatus = data.status;
            updateTaskCardsUI();
        }
    } catch (e) { /* ignore */ }
}

function updateTaskCardsUI() {
    const networks = ['adsgream', 'monetag', 'adexium', 'bonus'];
    networks.forEach(function(net) {
        const info = userAdStatus[net];
        if (!info) return;
        const progressFill = document.getElementById('progress-' + net);
        const progressText = document.getElementById('progress-text-' + net);
        const limitEl = document.getElementById('limit-' + net);
        const btn = document.getElementById('btn-' + net);
        const pct = info.limit > 0 ? Math.min(100, (info.count / info.limit) * 100) : 0;

        if (progressFill) progressFill.style.width = pct + '%';
        if (progressText) progressText.textContent = info.count + '/' + info.limit;
        if (limitEl) limitEl.textContent = 'Daily limit: ' + info.count + '/' + info.limit;

        if (btn) {
            if (info.completed) {
                btn.disabled = true;
                btn.textContent = 'COMPLETED';
                btn.className = btn.className.replace(/btn-cooldown/g, '') + ' btn-completed';
            } else {
                btn.disabled = false;
                btn.textContent = 'WATCH';
                btn.className = btn.className.replace(/btn-completed/g, '').replace(/btn-cooldown/g, '');
            }
        }
    });
}

function showNoAdsModal(network) {
    var modal = document.getElementById('ad-modal');
    var title = document.getElementById('ad-modal-title');
    var timer = document.getElementById('ad-timer');
    var footer = document.getElementById('ad-modal-footer');
    var body = document.getElementById('ad-modal-body');
    var networkNames = { 'adsgream': 'AdsGram', 'monetag': 'Monetag', 'adexium': 'Adexium', 'bonus': 'Bonus Offer' };

    title.textContent = networkNames[network] || network;
    timer.textContent = '';
    footer.classList.add('hidden');
    body.innerHTML = '<div class="ad-placeholder">' +
        '<span style="font-size:48px;">&#128269;</span>' +
        '<p style="font-size:16px;font-weight:700;margin-top:12px;">No Ads Found</p>' +
        '<p style="color:var(--text-secondary);font-size:13px;margin-top:6px;">No ads available for this platform right now.</p>' +
        '<p style="color:var(--text-muted);font-size:12px;margin-top:10px;">Try again later</p>' +
        '</div>';
    modal.classList.remove('hidden');
    setTimeout(function() {
        modal.classList.add('hidden');
        adLoading[network] = false;
    }, 3000);
}

// ===== AD COOLDOWN (per-platform) =====

async function checkAdCooldown() {
    if (!currentUser?.id) return;
    try {
        const resp = await fetch('/api/user/ad-cooldown/' + currentUser.id);
        const data = await resp.json();
        if (data.platforms) {
            Object.keys(data.platforms).forEach(function(net) {
                var cd = data.platforms[net];
                if (cd.remaining > 0) {
                    startCooldownTimer(net, cd.remaining);
                }
            });
        }
    } catch (e) { /* ignore */ }
}

function startCooldownTimer(network, seconds) {
    var key = 'cd_' + network;
    if (window[key]) clearInterval(window[key]);
    var remaining = seconds;
    function updateButton() {
        var btn = document.getElementById('btn-' + network);
        if (!btn) return;
        var info = userAdStatus[network];
        if (info && info.completed) {
            btn.disabled = true;
            btn.textContent = 'COMPLETED';
            btn.className = btn.className.replace(/btn-cooldown/g, '').replace(/btn-completed/g, '') + ' btn-completed';
            clearInterval(window[key]);
            return;
        }
        if (remaining > 0) {
            btn.disabled = true;
            btn.textContent = remaining + 's';
            btn.className = btn.className.replace(/btn-completed/g, '').replace(/btn-cooldown/g, '') + ' btn-cooldown';
            remaining--;
        } else {
            btn.disabled = false;
            btn.textContent = 'WATCH';
            btn.className = btn.className.replace(/btn-completed/g, '').replace(/btn-cooldown/g, '');
            clearInterval(window[key]);
            window[key] = null;
        }
    }
    updateButton();
    window[key] = setInterval(updateButton, 1000);
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
        const cardEl = document.getElementById('task-' + net);
        if (rewardEl) {
            rewardEl.textContent = '+' + formatUSDT(rateData.rate) + ' USDT';
        }
        if (cardEl) {
            cardEl.style.display = rateData.enabled ? '' : 'none';
        }
    });
    document.getElementById('farm-rate-text').textContent = formatUSDT(appConfig.farm_rate);
    document.getElementById('farm-duration-text').textContent = appConfig.farm_duration_hours;
    loadAdStatus();
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

    if (tabName === 'settings' && currentUser) {
        loadPasswordStatus();
        load2FAStatus();
    }

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
    }
}

// ===== AD WATCHING =====
let currentAdNetwork = null;
let adTimerInterval = null;
let adLoading = {};

async function watchAd(network) {
    if (document.getElementById('banned-overlay') && !document.getElementById('banned-overlay').classList.contains('hidden')) {
        return;
    }
    if (adLoading[network]) {
        showToast('Ad is loading, please wait...');
        return;
    }
    var cdKey = 'cd_' + network;
    if (window[cdKey]) {
        return;
    }
    var netInfo = userAdStatus[network];
    if (netInfo && netInfo.completed) {
        showToast('Daily limit reached for ' + network);
        return;
    }
    if (netInfo && netInfo.cooldown_remaining > 0) {
        startCooldownTimer(network, netInfo.cooldown_remaining);
        return;
    }
    // Check if ads are actually available for this platform
    if (currentUser?.id) {
        try {
            var checkResp = await fetch('/api/user/ad-check/' + currentUser.id + '/' + network);
            var checkData = await checkResp.json();
            if (!checkData.available) {
                showNoAdsModal(network);
                return;
            }
        } catch (e) { /* proceed anyway */ }
    }
    // Server-side cooldown check
    if (currentUser?.id) {
        try {
            const resp = await fetch('/api/user/ad-cooldown/' + currentUser.id);
            const cd = await resp.json();
            if (cd.remaining > 0) {
                startCooldownTimer(cd.remaining);
                return;
            }
        } catch (e) { /* ignore */ }
    }
    currentAdNetwork = network;
    adLoading[network] = true;
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
    }).then(function(resp) {
        return resp.json();
    }).then(function(data) {
        if (data.banned) {
            showBannedScreen();
            document.getElementById('ad-modal').classList.add('hidden');
            clearInterval(adTimerInterval);
            adLoading[currentAdNetwork] = false;
        } else if (data.vpn_warning) {
            showVPNWarning(data.message);
            document.getElementById('ad-modal').classList.add('hidden');
            clearInterval(adTimerInterval);
            adLoading[currentAdNetwork] = false;
        }
    }).catch(function() { adLoading[currentAdNetwork] = false; });
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
    adLoading[currentAdNetwork] = false;

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.notificationOccurred('success');
    }

    fetch('/api/user/balance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_id: currentUser?.id,
            reward: reward,
            platform_name: currentAdNetwork || 'unknown',
        }),
    }).then(function(resp) {
        return resp.json();
    }).then(function(data) {
        if (data.banned) {
            showBannedScreen();
        } else if (data.vpn_warning) {
            showVPNWarning(data.message);
        } else if (data.daily_limit_reached) {
            showToast('Daily limit reached for this platform');
            loadAdStatus();
        } else if (data.time_reject) {
            balance -= reward;
            totalEarned -= reward;
            tasksDone--;
            todayEarned -= reward;
            updateUI();
        } else if (data.cooldown_remaining) {
            showToast('Wait ' + data.cooldown_remaining + 's before next ' + (data.platform || '') + ' ad');
            if (data.platform) startCooldownTimer(data.platform, data.cooldown_remaining);
        } else if (data.status === 'ok') {
            hideVPNWarning();
            if (data.balance !== undefined) balance = data.balance;
            if (data.total_earned !== undefined) totalEarned = data.total_earned;
            if (data.tasks_done !== undefined) tasksDone = data.tasks_done;
            updateUI();
            checkAdCooldown();
            loadAdStatus();
            showRewardToast(reward);
        }
    }).catch(function() {});
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

// ===== PASSWORD & 2FA =====
function changePassword() {
    var current = document.getElementById('pw-current').value;
    var newPw = document.getElementById('pw-new').value;
    var confirm = document.getElementById('pw-confirm').value;
    if (newPw.length < 6) { alert('Password must be at least 6 characters'); return; }
    if (newPw !== confirm) { alert('Passwords do not match'); return; }
    fetch('/api/user/set-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: currentUser.id, password: newPw, session_id: userSessionId }),
    }).then(r => r.json()).then(data => {
        if (data.error) { alert(data.error); return; }
        alert('Password saved!');
        document.getElementById('pw-current').value = '';
        document.getElementById('pw-new').value = '';
        document.getElementById('pw-confirm').value = '';
        loadPasswordStatus();
    }).catch(() => {});
}

function loadPasswordStatus() {
    fetch('/api/user/has-password?user_id=' + currentUser.id).then(r => r.json()).then(data => {
        var el = document.getElementById('password-status');
        if (data.has_password) {
            el.innerHTML = '<span>&#10003;</span><p>Password is set</p>';
        }
    }).catch(() => {});
}

function setup2FA() {
    fetch('/api/user/2fa/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: currentUser.id, session_id: userSessionId }),
    }).then(r => r.json()).then(data => {
        if (data.error) { alert(data.error); return; }
        document.getElementById('2fa-secret').textContent = data.secret;
        document.getElementById('2fa-qr').src = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(data.otpauth_url);
        document.getElementById('2fa-setup-area').classList.remove('hidden');
        document.getElementById('2fa-setup-btn').classList.add('hidden');
    }).catch(() => {});
}

function verify2FA() {
    var code = document.getElementById('2fa-code').value.trim();
    if (code.length !== 6) { alert('Enter 6-digit code'); return; }
    fetch('/api/user/2fa/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: currentUser.id, code: code, session_id: userSessionId }),
    }).then(r => r.json()).then(data => {
        if (data.error) { alert(data.error); return; }
        alert('2FA enabled!');
        document.getElementById('2fa-setup-area').classList.add('hidden');
        load2FAStatus();
    }).catch(() => {});
}

function disable2FA() {
    var pw = prompt('Enter your password to disable 2FA:');
    if (!pw) return;
    fetch('/api/user/2fa/disable', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: currentUser.id, password: pw, session_id: userSessionId }),
    }).then(r => r.json()).then(data => {
        if (data.error) { alert(data.error); return; }
        alert('2FA disabled');
        load2FAStatus();
    }).catch(() => {});
}

function load2FAStatus() {
    fetch('/api/user/2fa/status?user_id=' + currentUser.id + '&session_id=' + userSessionId).then(r => r.json()).then(data => {
        var el = document.getElementById('2fa-status');
        var setupBtn = document.getElementById('2fa-setup-btn');
        var disableBtn = document.getElementById('2fa-disable-btn');
        if (data.enabled) {
            el.innerHTML = '<span>&#10003;</span><p>2FA is enabled</p>';
            setupBtn.classList.add('hidden');
            disableBtn.classList.remove('hidden');
        } else {
            el.innerHTML = '<span>&#128737;</span><p>2FA is not enabled</p>';
            setupBtn.classList.remove('hidden');
            disableBtn.classList.add('hidden');
        }
    }).catch(() => {});
}
