/* ================================================================
   ARBITER — Jarvis HUD Controller
   Orb animation + Voice I/O + Dashboard polling
   ================================================================ */

const REFRESH_INTERVAL = 60_000;
let countdown = REFRESH_INTERVAL / 1000;

// ── API Authentication ──────────────────────────────────────────────
// Wraps native fetch to inject Authorization header when an API key is set.
// Key is stored in localStorage and validated against /api/auth/check.
let _arbiterApiKey = localStorage.getItem('arbiter_api_key') || '';

const _origFetch = window.fetch.bind(window);
window.fetch = function(url, opts = {}) {
    if (_arbiterApiKey && typeof url === 'string' && url.startsWith('/api/')) {
        opts = opts || {};
        opts.headers = opts.headers || {};
        if (opts.headers instanceof Headers) {
            opts.headers.set('Authorization', `Bearer ${_arbiterApiKey}`);
        } else {
            opts.headers['Authorization'] = `Bearer ${_arbiterApiKey}`;
        }
    }
    return _origFetch(url, opts);
};

async function _arbiterCheckAuth() {
    try {
        const resp = await _origFetch('/api/auth/check', {
            headers: _arbiterApiKey ? { 'Authorization': `Bearer ${_arbiterApiKey}` } : {},
        });
        const data = await resp.json();
        if (data.auth_required && !data.valid) {
            _arbiterShowAuthModal();
            return false;
        }
        return true;
    } catch { return true; }
}

function _arbiterShowAuthModal() {
    let modal = document.getElementById('arbiter-auth-modal');
    if (modal) { modal.style.display = 'flex'; return; }
    modal = document.createElement('div');
    modal.id = 'arbiter-auth-modal';
    modal.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.85);backdrop-filter:blur(8px)';
    modal.innerHTML = `
        <div style="background:rgba(6,12,28,0.95);border:1px solid rgba(0,240,255,0.2);border-radius:8px;padding:32px;max-width:380px;width:90%;text-align:center;box-shadow:0 4px 30px rgba(0,0,0,0.5)">
            <div style="font-family:var(--font-mono);font-size:11px;letter-spacing:2px;color:#00e5ff;margin-bottom:16px">🔒 ARBITER AUTH</div>
            <div style="font-family:var(--font-mono);font-size:9px;color:rgba(0,240,255,0.5);margin-bottom:20px">API key required — set ARBITER_API_KEY in .env</div>
            <input id="arbiter-auth-input" type="password" placeholder="Enter API key..."
                style="width:100%;padding:10px 14px;background:rgba(0,0,0,0.4);border:1px solid rgba(0,240,255,0.15);border-radius:4px;color:var(--text-bright);font-family:var(--font-mono);font-size:11px;outline:none;box-sizing:border-box;margin-bottom:12px"
            />
            <div id="arbiter-auth-error" style="font-family:var(--font-mono);font-size:8px;color:#ff5252;margin-bottom:12px;display:none">Invalid API key</div>
            <button id="arbiter-auth-submit"
                style="width:100%;padding:8px;background:rgba(0,240,255,0.1);border:1px solid rgba(0,240,255,0.3);border-radius:4px;color:#00e5ff;font-family:var(--font-mono);font-size:10px;letter-spacing:1px;cursor:pointer"
            >AUTHENTICATE</button>
        </div>
    `;
    document.body.appendChild(modal);
    const input = document.getElementById('arbiter-auth-input');
    const submit = document.getElementById('arbiter-auth-submit');
    const error = document.getElementById('arbiter-auth-error');
    async function tryAuth() {
        const key = input.value.trim();
        if (!key) { input.focus(); return; }
        try {
            const resp = await _origFetch('/api/auth/check', { headers: { 'Authorization': `Bearer ${key}` } });
            const data = await resp.json();
            if (data.valid) {
                _arbiterApiKey = key;
                localStorage.setItem('arbiter_api_key', key);
                modal.style.display = 'none';
                location.reload();
            } else {
                error.style.display = 'block';
                input.style.borderColor = '#ff5252';
            }
        } catch { error.style.display = 'block'; }
    }
    submit.addEventListener('click', tryAuth);
    input.addEventListener('keydown', e => { if (e.key === 'Enter') tryAuth(); });
    input.focus();
}

// Check auth on page load
document.addEventListener('DOMContentLoaded', () => setTimeout(_arbiterCheckAuth, 500));

// ── Mute toggle ──────────────────────────────────────────────────
let _arbiterMuted = localStorage.getItem('arbiter_muted') === '1';
const _MUTE_SVG_ON  = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>`;
const _MUTE_SVG_OFF = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>`;
function _muteSetIcon() {
    const btn = document.getElementById('mc-mute-btn');
    const icon = document.getElementById('mc-mute-icon');
    if (btn) btn.classList.toggle('muted', _arbiterMuted);
    if (icon) icon.innerHTML = _arbiterMuted ? _MUTE_SVG_OFF : _MUTE_SVG_ON;
}
function _toggleMute() {
    _arbiterMuted = !_arbiterMuted;
    localStorage.setItem('arbiter_muted', _arbiterMuted ? '1' : '0');
    _muteSetIcon();
    // Stop any current speech if muting
    if (_arbiterMuted && typeof voice !== 'undefined' && voice.speaking) {
        voice.stopSpeaking();
    }
}
// Initialise mute state on load
document.addEventListener('DOMContentLoaded', _muteSetIcon);

// ── Mic Mute toggle ─────────────────────────────────────────────
let _micMuted = localStorage.getItem('arbiter_mic_muted') === '1';
const _MIC_SVG_ON  = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="1" width="6" height="11" rx="3"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`;
const _MIC_SVG_OFF = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="1" width="6" height="11" rx="3"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;
function _micMuteSetIcon() {
    const btn = document.getElementById('mc-mic-mute-btn');
    const icon = document.getElementById('mc-mic-mute-icon');
    if (btn) btn.classList.toggle('muted', _micMuted);
    if (icon) icon.innerHTML = _micMuted ? _MIC_SVG_OFF : _MIC_SVG_ON;
}
function _toggleMicMute() {
    _micMuted = !_micMuted;
    localStorage.setItem('arbiter_mic_muted', _micMuted ? '1' : '0');
    _micMuteSetIcon();
    if (_micMuted && typeof voice !== 'undefined') {
        // Kill recognition immediately
        try { voice.recognition.stop(); } catch {}
        voice._running = false;
        voice._mode = 'off';
        voice._pendingStart = null;
        voice._stopLevelPump();
        voice.orb.setState('idle');
        logConvo('Microphone muted — wake word disabled', 'system');
    } else if (!_micMuted && typeof voice !== 'undefined') {
        // Restart passive wake-word listening
        logConvo('Microphone unmuted — wake word active', 'system');
        voice._requestStart('passive');
    }
}
document.addEventListener('DOMContentLoaded', _micMuteSetIcon);

// ── Settings Panel ──────────────────────────────────────────────
let _settingsOpen = false;

function _settingsToggle() {
    const overlay = document.getElementById('settings-overlay');
    const btn = document.getElementById('mc-settings-btn');
    if (!overlay) return;
    _settingsOpen = !_settingsOpen;
    overlay.classList.toggle('open', _settingsOpen);
    if (btn) btn.classList.toggle('active', _settingsOpen);
    if (_settingsOpen) _settingsLoad();
}

function _settingsSwitchTab(tab) {
    document.querySelectorAll('.settings-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    document.querySelectorAll('.settings-tab-content').forEach(c => c.classList.toggle('active', c.id === `settings-tab-${tab}`));
    if (tab === 'llm') _settingsLoadLLM();
    if (tab === 'business') _settingsLoadBizTab();
}

async function _settingsLoad() {
    const data = await api('/api/settings');
    if (!data) return;

    // General tab
    const ww = document.getElementById('set-wake-word');
    const lt = document.getElementById('set-lock-timeout');
    const ltv = document.getElementById('set-lock-timeout-val');
    if (ww) ww.checked = data.wake_word !== '0';
    if (lt) {
        lt.value = data.lock_timeout || '15';
        if (ltv) ltv.textContent = (data.lock_timeout || '15') + ' min';
    }
    const tz = document.getElementById('set-timezone');
    if (tz && data.timezone) tz.value = data.timezone;

    // Populate TTS voices
    _settingsLoadVoices(data.tts_voice || 'default');

    // Email tab
    const ea = document.getElementById('set-email-address');
    const ih = document.getElementById('set-imap-host');
    const ip = document.getElementById('set-imap-port');
    const sh = document.getElementById('set-smtp-host');
    const sp = document.getElementById('set-smtp-port');
    if (ea) ea.value = data.email_address || '';
    if (ih) ih.value = data.imap_host || 'imap.gmail.com';
    if (ip) ip.value = data.imap_port || '993';
    if (sh) sh.value = data.smtp_host || 'smtp.gmail.com';
    if (sp) sp.value = data.smtp_port || '587';

    // Password field — show placeholder if configured
    const ep = document.getElementById('set-email-password');
    if (ep) {
        ep.value = '';
        ep.placeholder = data.email_configured ? 'Configured (leave blank to keep)' : 'Enter app password';
    }

    // LLM tab (auto-loads if active)
    if (document.getElementById('settings-tab-llm')?.classList.contains('active')) {
        _settingsLoadLLM();
    }
}

function _settingsLoadVoices(current) {
    const sel = document.getElementById('set-tts-voice');
    if (!sel) return;
    sel.innerHTML = '<option value="default">Default</option>';
    try {
        const voices = speechSynthesis.getVoices();
        voices.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.name;
            opt.textContent = `${v.name} (${v.lang})`;
            if (v.name === current) opt.selected = true;
            sel.appendChild(opt);
        });
    } catch {}
}
// Voices load asynchronously in some browsers
if (typeof speechSynthesis !== 'undefined') {
    speechSynthesis.addEventListener('voiceschanged', () => {
        const cur = document.getElementById('set-tts-voice')?.value || 'default';
        _settingsLoadVoices(cur);
    });
}

async function _settingsLoadLLM() {
    const data = await api('/api/settings');
    const grid = document.getElementById('settings-llm-grid');
    if (!data || !grid) return;

    const providers = [
        { name: 'Claude (Anthropic)', on: data.llm_claude_configured, model: data.llm_provider === 'claude' ? 'Primary' : 'Available' },
        { name: 'OpenRouter', on: data.llm_openrouter_configured, model: 'Agent dispatch & panels' },
        { name: 'Gemini (Google)', on: data.llm_gemini_configured, model: 'Researcher & Analyst' },
        { name: 'Ollama (Local)', on: true, model: `${data.llm_ollama_model || 'phi4'} @ ${data.llm_ollama_url || 'localhost:11434'}` },
    ];

    grid.innerHTML = providers.map(p => `
        <div class="settings-llm-card">
            <span class="llm-indicator ${p.on ? 'on' : 'off'}"></span>
            <span class="llm-name">${p.name}</span>
            <span class="llm-model">${p.on ? p.model : 'Not configured'}</span>
        </div>
    `).join('');
}

async function _settingsSave() {
    const payload = {};

    // General
    const ww = document.getElementById('set-wake-word');
    const lt = document.getElementById('set-lock-timeout');
    const tz = document.getElementById('set-timezone');
    const tv = document.getElementById('set-tts-voice');
    if (ww) payload.wake_word = ww.checked ? '1' : '0';
    if (lt) payload.lock_timeout = lt.value;
    if (tz) payload.timezone = tz.value;
    if (tv) payload.tts_voice = tv.value;

    // Email
    const ea = document.getElementById('set-email-address');
    const ep = document.getElementById('set-email-password');
    const ih = document.getElementById('set-imap-host');
    const ip = document.getElementById('set-imap-port');
    const sh = document.getElementById('set-smtp-host');
    const sp = document.getElementById('set-smtp-port');
    if (ea) payload.email_address = ea.value.trim();
    if (ep && ep.value.trim()) payload.email_password = ep.value.trim();
    if (ih) payload.imap_host = ih.value.trim();
    if (ip) payload.imap_port = ip.value.trim();
    if (sh) payload.smtp_host = sh.value.trim();
    if (sp) payload.smtp_port = sp.value.trim();

    const result = await api('/api/settings', 'PUT', payload);
    if (result?.ok) {
        // Apply local settings immediately
        if (payload.tts_voice && payload.tts_voice !== 'default') {
            localStorage.setItem('arbiter_tts_voice', payload.tts_voice);
        }
        if (payload.lock_timeout) {
            localStorage.setItem('arbiter_lock_timeout', payload.lock_timeout);
        }
        _settingsToggle();
        if (typeof logConvo === 'function') logConvo('Settings saved', 'system');
    } else {
        const tr = document.getElementById('set-email-test-result');
        if (tr) { tr.textContent = 'Save failed'; tr.className = 'settings-test-result fail'; }
    }
}

async function _settingsTestEmail() {
    const tr = document.getElementById('set-email-test-result');
    if (tr) { tr.textContent = 'Testing...'; tr.className = 'settings-test-result busy'; }

    const ea = document.getElementById('set-email-address');
    const ep = document.getElementById('set-email-password');
    const ih = document.getElementById('set-imap-host');
    const ip = document.getElementById('set-imap-port');

    const payload = {
        email_address: ea?.value.trim() || '',
        email_password: ep?.value.trim() || '',
        imap_host: ih?.value.trim() || 'imap.gmail.com',
        imap_port: ip?.value.trim() || '993',
    };

    try {
        const r = await fetch('/api/settings/test-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const d = await r.json();
        if (tr) {
            if (d.ok) {
                tr.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> ' + d.message;
                tr.className = 'settings-test-result ok';
            } else {
                tr.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> ' + (d.error || 'Connection failed');
                tr.className = 'settings-test-result fail';
            }
        }
    } catch (e) {
        if (tr) { tr.textContent = 'Network error'; tr.className = 'settings-test-result fail'; }
    }
}

// Lock timeout slider live update
document.addEventListener('DOMContentLoaded', () => {
    const lt = document.getElementById('set-lock-timeout');
    const ltv = document.getElementById('set-lock-timeout-val');
    if (lt && ltv) {
        lt.addEventListener('input', () => { ltv.textContent = lt.value + ' min'; });
    }
});

// ── Business Profiles Tab (inside Settings) ────────────────
function _settingsLoadBizTab() {
    // Populate active-business selector
    const sel = document.getElementById('set-active-business');
    if (sel) {
        sel.innerHTML = '<option value="">All Businesses (global view)</option>' +
            _businesses.map(b => `<option value="${b.id}"${b.id === _activeBusinessId ? ' selected' : ''}>${b.icon || ''} ${_escHtml(b.name)}</option>`).join('');
    }
    // Render profile cards
    _settingsRenderBizCards();
    // Load prompt versions for active business
    _promptLoadVersions();
}

function _settingsRenderBizCards() {
    const container = document.getElementById('settings-biz-list');
    if (!container) return;
    if (_businesses.length === 0) {
        container.innerHTML = '<div class="settings-biz-empty"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:0.3;margin-bottom:6px"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg><br>No business profiles yet. Add one below.</div>';
        return;
    }
    container.innerHTML = _businesses.map(b => {
        const isActive = b.id === _activeBusinessId;
        const ghRepo = b.github_repo || '';
        const hasContext = !!(b.business_context && b.business_context.trim());
        return `<div class="settings-biz-card${isActive ? ' active-biz' : ''}">
            <div class="settings-biz-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg></div>
            <div class="settings-biz-info">
                <div class="settings-biz-name">${_escHtml(b.name)}</div>
                ${b.description ? `<div class="settings-biz-desc">${_escHtml(b.description)}</div>` : ''}
                <div class="settings-biz-meta">
                    ${isActive ? '<span class="settings-biz-badge active-tag">Active</span>' : ''}
                    ${hasContext ? '<span class="settings-biz-badge context-tag">AI Context</span>' : ''}
                    ${b.active_prompt_mode && b.active_prompt_mode !== 'default' ? `<span class="settings-biz-badge mode-tag">${_escHtml(b.active_prompt_mode)}</span>` : ''}
                    ${ghRepo ? `<span class="settings-biz-badge cicd">${_escHtml(ghRepo)}</span>` : ''}
                </div>
            </div>
            <div class="settings-biz-actions">
                ${!isActive ? `<button title="Set as active" onclick="_settingsSelectBusiness('${b.id}')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg></button>` : ''}
                <button class="biz-del-btn" title="Delete profile" onclick="_settingsDeleteBusiness('${b.id}','${_escHtml(b.name)}')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>
            </div>
        </div>`;
    }).join('');
}

function _settingsSelectBusiness(id) {
    _setActiveBusinessId(id);
    _settingsLoadBizTab();
    if (typeof refreshAll === 'function') refreshAll();
    appendLog(`Business context: ${id ? (_businesses.find(b=>b.id===id)?.name || id) : 'ALL'}`, '');
}

async function _settingsAddBusiness() {
    const name = document.getElementById('set-biz-name')?.value?.trim();
    if (!name) { _bizFormStatus('Name is required', false); return; }
    const desc = document.getElementById('set-biz-desc')?.value?.trim() || '';
    const bizContext = document.getElementById('set-biz-context')?.value?.trim() || '';
    const ghRepo = document.getElementById('set-biz-gh-repo')?.value?.trim() || '';
    const ghToken = document.getElementById('set-biz-gh-token')?.value?.trim() || '';
    // Validate repo format if provided
    if (ghRepo && !/^[a-zA-Z0-9._-]+\/[a-zA-Z0-9._-]+$/.test(ghRepo)) {
        _bizFormStatus('Repo format: owner/repo', false); return;
    }
    _bizFormStatus('Saving...', null);
    try {
        const r = await fetch('/api/businesses', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description: desc, business_context: bizContext, github_repo: ghRepo, github_token: ghToken }),
        });
        const data = await r.json();
        if (data.error) { _bizFormStatus(data.error, false); return; }
        // Clear form
        document.getElementById('set-biz-name').value = '';
        document.getElementById('set-biz-desc').value = '';
        document.getElementById('set-biz-context').value = '';
        document.getElementById('set-biz-gh-repo').value = '';
        document.getElementById('set-biz-gh-token').value = '';
        _bizFormStatus('Profile created', true);
        await _loadBusinesses();
        _settingsLoadBizTab();
        setTimeout(() => _bizFormStatus('', null), 2000);
    } catch (e) { _bizFormStatus('Failed: ' + e.message, false); }
}

async function _settingsDeleteBusiness(id, name) {
    if (!confirm(`Delete "${name}"? Data tagged with this business will remain but won't be filtered.`)) return;
    try {
        await fetch(`/api/businesses/${id}/delete`, { method: 'POST' });
        if (_activeBusinessId === id) {
            _setActiveBusinessId('');
        }
        await _loadBusinesses();
        _settingsLoadBizTab();
    } catch (e) { _bizFormStatus('Delete failed: ' + e.message, false); }
}

function _bizFormStatus(msg, success) {
    const el = document.getElementById('set-biz-status');
    if (!el) return;
    el.textContent = msg;
    el.className = 'settings-biz-form-status' + (success === true ? ' ok' : success === false ? ' fail' : '');
}

// ── Prompt Versioning UI ─────────────────────────────────────────
let _promptData = null;

async function _promptLoadVersions() {
    const panel = document.getElementById('prompt-version-panel');
    if (!panel) return;
    if (!_activeBusinessId) { panel.style.display = 'none'; return; }
    panel.style.display = '';
    try {
        const r = await fetch(`/api/businesses/${_activeBusinessId}/prompts`);
        _promptData = await r.json();
        _promptRenderModes();
        _promptRenderVersions();
    } catch (e) { console.warn('[PROMPT] Failed to load versions:', e); }
}

function _promptRenderModes() {
    const container = document.getElementById('prompt-mode-pills');
    if (!container || !_promptData) return;
    const modes = _promptData.modes || [];
    const active = _promptData.active_mode || 'default';
    if (modes.length === 0) {
        container.innerHTML = '<span class="prompt-mode-pill active">default</span>';
        return;
    }
    container.innerHTML = modes.map(m => {
        const isActive = m.mode === active;
        return `<button class="prompt-mode-pill${isActive ? ' active' : ''}"
            onclick="_promptSwitchMode('${_escHtml(m.mode)}')"
            title="${m.total_versions} version${m.total_versions !== 1 ? 's' : ''}">${_escHtml(m.mode)}${isActive ? ' \u2713' : ''}</button>`;
    }).join('');
}

function _promptRenderVersions() {
    const container = document.getElementById('prompt-version-list');
    if (!container || !_promptData) return;
    const versions = _promptData.versions || [];
    if (versions.length === 0) {
        container.innerHTML = '<div class="prompt-empty">No prompt versions yet. Set business context above or create one via the API.</div>';
        return;
    }
    container.innerHTML = versions.slice(0, 10).map(v => {
        const isLatest = v.version_num === (versions[0]?.version_num);
        const sourceIcon = v.source === 'agent' ? '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#e040fb" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>'
            : v.source === 'pipeline' ? '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#00e5ff" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>'
            : '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#00c853" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
        const ago = _timeAgo(v.created_at);
        const preview = (v.content || '').substring(0, 120).replace(/\n/g, ' ');
        return `<div class="prompt-version-item${isLatest ? ' latest' : ''}">
            <div class="prompt-version-header">
                <span class="prompt-version-num">v${v.version_num}</span>
                <span class="prompt-version-source">${sourceIcon} ${_escHtml(v.source)}</span>
                <span class="prompt-version-time">${ago}</span>
                ${!isLatest ? `<button class="prompt-restore-btn" onclick="_promptRestore('${v.id}')" title="Restore this version">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
                </button>` : '<span class="prompt-version-badge">current</span>'}
            </div>
            ${v.summary ? `<div class="prompt-version-summary">${_escHtml(v.summary)}</div>` : ''}
            <div class="prompt-version-preview">${_escHtml(preview)}${preview.length >= 120 ? '...' : ''}</div>
        </div>`;
    }).join('');
}

function _timeAgo(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr + (dateStr.endsWith('Z') ? '' : 'Z'));
    const diff = Math.floor((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
}

async function _promptSwitchMode(mode) {
    if (!_activeBusinessId) return;
    try {
        const r = await fetch(`/api/businesses/${_activeBusinessId}/prompts/mode`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode }),
        });
        const data = await r.json();
        if (data.error) { alert(data.error); return; }
        await _loadBusinesses();
        await _promptLoadVersions();
        appendLog(`Prompt mode switched to: ${mode}`, '');
    } catch (e) { alert('Failed: ' + e.message); }
}

async function _promptRestore(versionId) {
    if (!_activeBusinessId || !confirm('Restore this version? A new version will be created with the old content.')) return;
    try {
        const r = await fetch(`/api/businesses/${_activeBusinessId}/prompts/${versionId}/restore`, { method: 'POST' });
        const data = await r.json();
        if (data.error) { alert(data.error); return; }
        await _loadBusinesses();
        await _promptLoadVersions();
        appendLog(`Prompt restored to v${data.version_num}`, '');
    } catch (e) { alert('Failed: ' + e.message); }
}

async function _promptAddMode() {
    const mode = prompt('Enter new mode name (e.g. growth, support, launch):');
    if (!mode) return;
    const clean = mode.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-').substring(0, 30);
    if (!clean) { alert('Invalid mode name'); return; }
    const content = prompt('Enter the prompt content for this mode:');
    if (!content || !content.trim()) { alert('Content is required'); return; }
    try {
        const r = await fetch(`/api/businesses/${_activeBusinessId}/prompts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: content.trim(), mode: clean, source: 'user', summary: `Created ${clean} mode` }),
        });
        const data = await r.json();
        if (data.error) { alert(data.error); return; }
        await _promptLoadVersions();
        appendLog(`Created prompt mode: ${clean}`, '');
    } catch (e) { alert('Failed: ' + e.message); }
}

// Close settings on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _settingsOpen) _settingsToggle();
});

// ── SVG Icon Library (replaces emojis) ──────────────────────────
const _SVG = (name, size = 16) => {
    const icons = {
        shield:       `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
        compass:      `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>`,
        box:          `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`,
        'alert-triangle': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
        search:       `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
        megaphone:    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 11l18-5v12L3 13v-2z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/></svg>`,
        'trending-up':`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>`,
        cpu:          `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>`,
        'bar-chart':  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>`,
        camera:       `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>`,
        scale:        `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v18"/><path d="M1 6l5 6 5-6"/><path d="M13 6l5 6 5-6"/></svg>`,
        globe:        `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,
        play:         `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,
        rocket:       `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>`,
        pin:          `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`,
        broadcast:    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.4"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.4"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/></svg>`,
        clipboard:    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/></svg>`,
        droplet:      `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg>`,
        wind:         `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2"/></svg>`,
        sun:          `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`,
        'cloud-sun':  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v2M4.93 4.93l1.41 1.41M20 12h2M17.66 4.93l-1.41 1.41M16 12a4 4 0 0 0-8 0"/><path d="M17.5 21H9a5 5 0 0 1 .5-9.97 7 7 0 0 1 13 3.47A4.5 4.5 0 0 1 17.5 21z"/></svg>`,
        cloud:        `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>`,
        'cloud-rain': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/><line x1="8" y1="21" x2="8" y2="23"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="16" y1="21" x2="16" y2="23"/></svg>`,
        snowflake:    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="2" x2="12" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/><line x1="19.07" y1="4.93" x2="4.93" y2="19.07"/></svg>`,
        'cloud-fog':  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/><line x1="4" y1="22" x2="20" y2="22"/></svg>`,
        zap:          `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
        thermometer:  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/></svg>`,
        bell:         `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>`,
        crown:        `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 20h20l-2-8-4 4-4-8-4 8-4-4z"/><path d="M5 20v2h14v-2"/></svg>`,
        share:        `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>`,
        star:         `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
        eye:          `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
        heart:        `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`,
        book:         `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
        film:         `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/><line x1="17" y1="17" x2="22" y2="17"/></svg>`,
        palette:      `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="13.5" cy="6.5" r="0.5" fill="currentColor"/><circle cx="17.5" cy="10.5" r="0.5" fill="currentColor"/><circle cx="8.5" cy="7.5" r="0.5" fill="currentColor"/><circle cx="6.5" cy="12.5" r="0.5" fill="currentColor"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.93 0 1.5-.67 1.5-1.5 0-.39-.15-.74-.39-1.04-.24-.3-.39-.65-.39-1.04 0-.83.67-1.5 1.5-1.5H16c3.31 0 6-2.69 6-6 0-5.5-4.5-9.92-10-9.92z"/></svg>`,
        smile:        `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>`,
        activity:     `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
        'dollar-sign':`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>`,
        briefcase:    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>`,
        layers:       `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
        'git-branch': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>`,
        'check-circle':`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
        terminal:     `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`,
        lock:         `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`,
        edit:         `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
        tool:         `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`,
        settings:     `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
    };
    return icons[name] || `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>`;
};

// ════════════════════════════════════════════════════════════════
//  ORB — Particle Nebula with orbital rings and compass ticks
// ════════════════════════════════════════════════════════════════
class Orb {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.dpr = window.devicePixelRatio || 1;
        this._resize();
        this.state = 'idle';
        this.time = 0;
        this.ringAngle = 0;

        // Audio reactivity — fed by VoiceEngine
        this.audioLevel = 0;          // 0–1, smoothed mic amplitude
        this._targetAudioLevel = 0;
        this._waveformBands = 64;     // number of frequency-like bands for the waveform
        this._waveData = new Float32Array(this._waveformBands); // simulated frequency data

        // State colours
        this.palette = {
            idle:      { r: 0, g: 200, b: 255 },
            listening: { r: 0, g: 255, b: 136 },
            thinking:  { r: 255, g: 170, b: 0 },
            speaking:  { r: 100, g: 210, b: 255 },
        };

        // Build particles — gaussian distribution from centre
        this.particles = this._buildParticles(1500);

        // Orbital ring definitions (radius fraction, tick count, width)
        this.rings = [
            { r: 0.62, ticks: 72,  w: 1.0, speed:  0.08 },
            { r: 0.78, ticks: 90,  w: 0.7, speed: -0.05 },
            { r: 0.92, ticks: 120, w: 0.5, speed:  0.03 },
        ];

        this._raf = null;
        this.start();
        window.addEventListener('resize', () => this._resize());
    }

    _resize(forceSize) {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        let size = forceSize || Math.min(rect.width, rect.height, 740);
        if (size < 10) size = 200;
        this.canvas.width = size * this.dpr;
        this.canvas.height = size * this.dpr;
        this.canvas.style.width = size + 'px';
        this.canvas.style.height = size + 'px';
        this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
        this.W = size;
        this.H = size;
        this.cx = size / 2;
        this.cy = size / 2;
        this.maxR = size * 0.36;
    }

    _gaussRandom() {
        // Box-Muller transform — bell curve centered on 0
        let u = 0, v = 0;
        while (u === 0) u = Math.random();
        while (v === 0) v = Math.random();
        return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    }

    _buildParticles(n) {
        const arr = [];
        for (let i = 0; i < n; i++) {
            // Distance from centre: gaussian, clamped 0–1
            const rawDist = Math.abs(this._gaussRandom()) * 0.35;
            const dist = Math.min(rawDist, 1.0);
            arr.push({
                angle: Math.random() * Math.PI * 2,
                baseDist: dist,
                dist: dist,
                speed: (0.0005 + Math.random() * 0.002) * (Math.random() < 0.5 ? 1 : -1),
                size: 0.4 + Math.random() * 1.6,
                phase: Math.random() * Math.PI * 2,
                twinkleSpeed: 1.5 + Math.random() * 3,
                brightness: 0.3 + Math.random() * 0.7,
            });
        }
        return arr;
    }

    setState(s) {
        this.state = s;
        const container = document.getElementById('orb-container');
        container.className = 'orb-container ' + (s === 'idle' ? '' : s);
        document.getElementById('orb-state').textContent = {
            idle: 'STANDBY', listening: 'LISTENING', thinking: 'ANALYSING', speaking: 'SPEAKING'
        }[s] || s.toUpperCase();
    }

    setAudioLevel(v) {
        this._targetAudioLevel = Math.max(0, Math.min(1, v));
    }

    start() {
        // Transition blend: 0 = nebula (idle), 1 = ring (voice active)
        this._voiceBlend = 0;

        // Assign each particle a slot on the waveform ring
        const n = this.particles.length;
        this.particles.forEach((p, i) => {
            p.ringAngle = (i / n) * Math.PI * 2;       // evenly spaced on ring
            p.ringBaseDist = 0.28 + (i % 3) * 0.02;    // slight layering
        });

        let last = performance.now();
        const draw = (now) => {
            const dt = (now - last) / 1000;
            last = now;
            this.time += dt;

            // Smooth audio level
            this.audioLevel += (this._targetAudioLevel - this.audioLevel) * 0.15;

            // Update waveform bands
            this._updateWaveData(dt);

            // Smoothly blend toward target state
            const isVoiceActive = this.state === 'listening' || this.state === 'speaking';
            const blendTarget = isVoiceActive ? 1 : 0;
            // Fast collapse in (0.06), slower drift out (0.025)
            const blendSpeed = blendTarget > this._voiceBlend ? 0.06 : 0.025;
            this._voiceBlend += (blendTarget - this._voiceBlend) * blendSpeed;

            this.ctx.clearRect(0, 0, this.W, this.H);
            this._drawGrid();
            this._drawHalo(dt);
            this._drawOuterGlow();
            this._drawParticles(dt);
            this._drawCore();
            // Draw the waveform glow ring when blended in
            if (this._voiceBlend > 0.01) this._drawWaveformRing();
            this._drawRings(dt);
            this._raf = requestAnimationFrame(draw);
        };
        this._raf = requestAnimationFrame(draw);
    }

    _updateWaveData(dt) {
        const level = this.audioLevel;
        for (let i = 0; i < this._waveformBands; i++) {
            const freq = 1.5 + i * 0.3;
            const phase = i * 0.7 + this.time * freq;
            const wave = Math.sin(phase) * 0.3 + Math.sin(phase * 1.7) * 0.2 + Math.sin(phase * 0.5) * 0.15;
            const target = Math.abs(wave) * (0.1 + level * 0.9);
            this._waveData[i] += (target - this._waveData[i]) * 0.2;
        }
    }

    // Glowing waveform ring drawn BEHIND the particles (they sit on it)
    _drawWaveformRing() {
        const ctx = this.ctx;
        const c = this.palette[this.state];
        const bands = this._waveformBands;
        const baseR = this.maxR * 0.28;
        const maxAmp = this.maxR * 0.35;
        const alpha = this._voiceBlend;

        ctx.save();
        ctx.translate(this.cx, this.cy);

        // Glow ring outline
        ctx.beginPath();
        for (let i = 0; i <= bands; i++) {
            const idx = i % bands;
            const angle = (idx / bands) * Math.PI * 2;
            const amp = this._waveData[idx] * maxAmp;
            const r = baseR + amp;
            const x = Math.cos(angle) * r;
            const y = Math.sin(angle) * r;
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.strokeStyle = `rgba(${c.r},${c.g},${c.b},${(0.4 * alpha).toFixed(2)})`;
        ctx.lineWidth = 2;
        ctx.shadowColor = `rgba(${c.r},${c.g},${c.b},${(0.6 * alpha).toFixed(2)})`;
        ctx.shadowBlur = 20;
        ctx.stroke();

        // Inner glow fill
        const grad = ctx.createRadialGradient(0, 0, baseR * 0.3, 0, 0, baseR + maxAmp);
        grad.addColorStop(0, `rgba(${c.r},${c.g},${c.b},${(0.12 * alpha).toFixed(2)})`);
        grad.addColorStop(0.5, `rgba(${c.r},${c.g},${c.b},${(0.04 * alpha).toFixed(2)})`);
        grad.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = grad;
        ctx.shadowBlur = 0;
        ctx.fill();

        // Scan lines radiating from centre
        const scanCount = 24;
        for (let i = 0; i < scanCount; i++) {
            const angle = (i / scanCount) * Math.PI * 2;
            const idx = Math.floor((i / scanCount) * bands);
            const amp = this._waveData[idx] * maxAmp;
            ctx.beginPath();
            ctx.moveTo(Math.cos(angle) * baseR * 0.5, Math.sin(angle) * baseR * 0.5);
            ctx.lineTo(Math.cos(angle) * (baseR + amp * 1.1), Math.sin(angle) * (baseR + amp * 1.1));
            ctx.strokeStyle = `rgba(${c.r},${c.g},${c.b},${(0.12 * alpha + this._waveData[idx] * 0.25 * alpha).toFixed(2)})`;
            ctx.lineWidth = 0.8;
            ctx.shadowBlur = 0;
            ctx.stroke();
        }

        ctx.restore();
    }

    // Subtle background grid
    _drawGrid() {
        const ctx = this.ctx;
        const step = 30;
        ctx.strokeStyle = 'rgba(0,200,255,0.04)';
        ctx.lineWidth = 0.5;
        for (let x = 0; x < this.W; x += step) {
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, this.H); ctx.stroke();
        }
        for (let y = 0; y < this.H; y += step) {
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(this.W, y); ctx.stroke();
        }
    }

    // Outer rotating halo/cog ring — contained within canvas bounds
    _drawHalo(dt) {
        const ctx = this.ctx;
        const c = this.palette[this.state];
        this.ringAngle += dt * 0.15;
        // Keep halo comfortably inside canvas (max 45% of half-size)
        const haloR = this.maxR * 1.28;
        const tickCount = 120;
        const tickLen = 7;
        const bigTickEvery = 10;

        ctx.save();
        ctx.translate(this.cx, this.cy);
        ctx.rotate(this.ringAngle);

        // Outer ring circle — full unbroken ring
        ctx.beginPath();
        ctx.arc(0, 0, haloR, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${c.r},${c.g},${c.b},0.16)`;
        ctx.lineWidth = 1.2;
        ctx.stroke();

        // Inner ring circle
        ctx.beginPath();
        ctx.arc(0, 0, haloR - tickLen - 2, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${c.r},${c.g},${c.b},0.08)`;
        ctx.lineWidth = 0.6;
        ctx.stroke();

        // Tick marks
        for (let i = 0; i < tickCount; i++) {
            const angle = (i / tickCount) * Math.PI * 2;
            const isBig = i % bigTickEvery === 0;
            const tl = isBig ? tickLen + 3 : tickLen;
            const alpha = isBig ? 0.35 : 0.14;
            const lw = isBig ? 1.5 : 0.7;

            const x1 = Math.cos(angle) * haloR;
            const y1 = Math.sin(angle) * haloR;
            const x2 = Math.cos(angle) * (haloR - tl);
            const y2 = Math.sin(angle) * (haloR - tl);

            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.strokeStyle = `rgba(${c.r},${c.g},${c.b},${alpha})`;
            ctx.lineWidth = lw;
            ctx.stroke();
        }

        // Corner notches (cog teeth) — 12 evenly spaced, kept inside canvas
        const cogOuter = Math.min(haloR + 8, this.W * 0.48);
        for (let i = 0; i < 12; i++) {
            const angle = (i / 12) * Math.PI * 2;
            const notchW = 0.04;
            ctx.beginPath();
            ctx.arc(0, 0, haloR + 2, angle - notchW, angle + notchW);
            ctx.lineTo(Math.cos(angle + notchW) * cogOuter, Math.sin(angle + notchW) * cogOuter);
            ctx.arc(0, 0, cogOuter, angle + notchW, angle - notchW, true);
            ctx.closePath();
            ctx.fillStyle = `rgba(${c.r},${c.g},${c.b},0.10)`;
            ctx.fill();
            ctx.strokeStyle = `rgba(${c.r},${c.g},${c.b},0.22)`;
            ctx.lineWidth = 0.8;
            ctx.stroke();
        }

        ctx.restore();
    }

    // Ambient radial glow behind everything — brighter
    _drawOuterGlow() {
        const ctx = this.ctx;
        const c = this.palette[this.state];
        const pulse = 1 + Math.sin(this.time * 1.2) * 0.08;
        const g = ctx.createRadialGradient(this.cx, this.cy, 0, this.cx, this.cy, this.maxR * 1.2 * pulse);
        g.addColorStop(0, `rgba(${c.r},${c.g},${c.b},0.18)`);
        g.addColorStop(0.3, `rgba(${c.r},${c.g},${c.b},0.08)`);
        g.addColorStop(0.6, `rgba(${c.r},${c.g},${c.b},0.03)`);
        g.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, this.W, this.H);
    }

    // Bright white-cyan core
    _drawCore() {
        const ctx = this.ctx;
        const c = this.palette[this.state];
        const pulse = 1 + Math.sin(this.time * 2) * 0.15;
        const coreR = this.maxR * 0.12 * pulse;

        // Outer halo
        const g2 = ctx.createRadialGradient(this.cx, this.cy, 0, this.cx, this.cy, coreR * 4);
        g2.addColorStop(0, `rgba(${c.r},${c.g},${c.b},0.25)`);
        g2.addColorStop(0.5, `rgba(${c.r},${c.g},${c.b},0.05)`);
        g2.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g2;
        ctx.beginPath(); ctx.arc(this.cx, this.cy, coreR * 4, 0, Math.PI * 2); ctx.fill();

        // Inner bright core
        const g = ctx.createRadialGradient(this.cx, this.cy, 0, this.cx, this.cy, coreR);
        g.addColorStop(0, 'rgba(255,255,255,0.95)');
        g.addColorStop(0.3, `rgba(${Math.min(c.r+100,255)},${Math.min(c.g+100,255)},${Math.min(c.b+100,255)},0.7)`);
        g.addColorStop(0.7, `rgba(${c.r},${c.g},${c.b},0.3)`);
        g.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(this.cx, this.cy, coreR, 0, Math.PI * 2); ctx.fill();
    }

    _drawParticles(dt) {
        const ctx = this.ctx;
        const c = this.palette[this.state];
        const speedMult = { idle: 1, listening: 1.8, thinking: 3, speaking: 2.2 }[this.state];
        const vb = this._voiceBlend; // 0 = nebula, 1 = ring
        const bands = this._waveformBands;
        const ringBaseR = 0.28;      // normalised ring radius (fraction of maxR)
        const ringMaxAmp = 0.35;     // max waveform displacement

        this.particles.forEach(p => {
            // ── Nebula position (idle) ───────────────────────
            p.angle += p.speed * speedMult;
            const nebulaDist = p.baseDist * (this.state === 'thinking' ? 0.7 : 1);

            // ── Ring position (voice active) ────────────────
            // Each particle maps to a waveform band
            const bandIdx = Math.floor((p.ringAngle / (Math.PI * 2)) * bands) % bands;
            const waveAmp = this._waveData[bandIdx] * ringMaxAmp;
            const ringDist = p.ringBaseDist + waveAmp;
            const ringAngle = p.ringAngle + this.time * 0.15; // slow rotation

            // ── Blend between nebula and ring ────────────────
            const targetDist = nebulaDist * (1 - vb) + ringDist * vb;
            const targetAngle = vb < 0.5
                ? p.angle                            // mostly nebula — use nebula angle
                : ringAngle;                         // mostly ring — snap to ring slot
            // Smooth angular blending with lerp
            const angleDiff = ((targetAngle - p.angle + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
            const blendedAngle = p.angle + angleDiff * vb * 0.08;
            p.angle = blendedAngle;

            // Smooth dist transition
            p.dist += (targetDist - p.dist) * (0.02 + vb * 0.08);

            const wobble = Math.sin(this.time * 1.5 + p.phase) * 0.02 * (1 - vb);
            const r = (p.dist + wobble) * this.maxR;
            const x = this.cx + Math.cos(p.angle) * r;
            const y = this.cy + Math.sin(p.angle) * r;

            // Twinkling — more steady when on ring
            const twinkle = 0.3 + 0.7 * ((Math.sin(this.time * p.twinkleSpeed + p.phase) + 1) / 2);
            const alpha = p.brightness * (twinkle * (1 - vb * 0.6) + vb * 0.6);

            // Size — slightly larger when on ring for visibility
            const sz = p.size * (1 + vb * 0.8);

            // Colour
            const effDist = p.dist * (1 - vb) + ringDist * vb;
            const blend = Math.min(effDist / 0.6, 1);
            const pr = Math.round(255 - blend * (255 - c.r));
            const pg = Math.round(255 - blend * (255 - c.g));
            const pb = Math.round(255 - blend * (255 - c.b));

            ctx.beginPath();
            ctx.arc(x, y, sz, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${pr},${pg},${pb},${alpha.toFixed(2)})`;
            ctx.fill();
        });
    }

    _drawRings(dt) {
        const ctx = this.ctx;
        const c = this.palette[this.state];

        this.rings.forEach(ring => {
            ring._angle = (ring._angle || 0) + ring.speed * dt;
            const r = ring.r * this.maxR;
            const tickLen = 4 + ring.w * 3;

            ctx.save();
            ctx.translate(this.cx, this.cy);
            ctx.rotate(ring._angle);

            // Ring circle
            ctx.beginPath();
            ctx.arc(0, 0, r, 0, Math.PI * 2);
            ctx.strokeStyle = `rgba(${c.r},${c.g},${c.b},${0.12 * ring.w})`;
            ctx.lineWidth = ring.w;
            ctx.stroke();

            // Compass tick marks
            for (let i = 0; i < ring.ticks; i++) {
                const a = (i / ring.ticks) * Math.PI * 2;
                const isMajor = i % (ring.ticks / 12) === 0;
                const len = isMajor ? tickLen * 1.8 : tickLen;
                const alpha = isMajor ? 0.35 : 0.12;
                const x1 = Math.cos(a) * (r - len / 2);
                const y1 = Math.sin(a) * (r - len / 2);
                const x2 = Math.cos(a) * (r + len / 2);
                const y2 = Math.sin(a) * (r + len / 2);
                ctx.beginPath();
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.strokeStyle = `rgba(${c.r},${c.g},${c.b},${alpha})`;
                ctx.lineWidth = isMajor ? 1.5 : 0.5;
                ctx.stroke();
            }

            ctx.restore();
        });
    }
}


// ════════════════════════════════════════════════════════════════
//  VOICE ENGINE — Wake word + Speech recognition + synthesis
//  Flow: idle → (hear "Arbiter") → listening (green waveform)
//        → 2s silence → thinking (amber) → speaking (waveform)
//        → idle
// ════════════════════════════════════════════════════════════════
class VoiceEngine {
    constructor(orb) {
        this.orb = orb;
        this.history = [];
        this.speaking = false;
        this.synth = window.speechSynthesis;
        this.synth.getVoices();
        if (this.synth.onvoiceschanged !== undefined) {
            this.synth.onvoiceschanged = () => this.synth.getVoices();
        }

        // State: 'passive' (wake word), 'active' (recording), 'off'
        this._mode = 'off';
        this._running = false;        // true while recognition is actually running
        this._pendingStart = null;    // 'passive' | 'active' — queued for onend
        this._silenceTimer = null;
        this._finalTranscript = '';
        this._suppressRestart = false;  // blocks onend from restarting after briefing dismiss

        // Active follow-up options (for voice command selection)
        this._activeFollowups = null;

        // Voice correction — track last query/reply for "I said..." corrections
        this._lastUserQuery = '';
        this._lastSpokenReply = '';

        // Abort controller for in-flight LLM requests
        this._activeAbort = null;

        // Session cache — stores all query/panel pairs for report building
        this._sessionCache = [];
        this._sessionId = Date.now().toString(36);
        this._sessionName = null;
        this._reportCharts = [];  // track charts rendered inside the report

        // Lock mode
        this._locked = false;
        this._lockTimer = null;
        this._lockIdleMs = 5 * 60 * 1000; // 5 minutes
        this._lockCode = '9086';
        this._lockVoiceDigits = [];        // collected spoken digits

        // Mic permission denied — stops retry loops on http://
        this._micDenied = false;

        // Audio analyser for real-time mic level → orb waveform
        this._audioCtx = null;
        this._analyser = null;
        this._micStream = null;
        this._levelRAF = null;

        this._initRecognition();
        this._initUI();
        this._initLock();

        // Auto-restore last session on page load
        this._autoRestoreLastSession();

        // Auto-save session when leaving the page (close tab, refresh, navigate away)
        window.addEventListener('beforeunload', () => this._saveCurrentSession());

        // Also save periodically (every 30s) as a safety net
        setInterval(() => {
            if (this._sessionCache.length > 0) this._saveCurrentSession();
        }, 30_000);

        // Log boot status to conversation log
        const srAvailable = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
        const browserInfo = navigator.userAgent.includes('Chrome') ? 'Chrome' :
                           navigator.userAgent.includes('Edg') ? 'Edge' :
                           navigator.userAgent.includes('Safari') ? 'Safari (NO speech support)' :
                           navigator.userAgent.includes('Firefox') ? 'Firefox (NO speech support)' : 'Unknown';
        // Browser: browserInfo | SR available: srAvailable

        if (this.recognition) {
            logConvo(`Voice engine online [${browserInfo}]. Say "Arbiter", double-clap, or click orb.`, 'system');
        } else {
            logConvo(`Voice engine OFFLINE — ${browserInfo}. Use Chrome or Edge.`, 'system');
        }

        // Auto-start passive wake word listening after a short delay
        setTimeout(() => this._requestStart('passive'), 800);

        // Chrome often blocks recognition.start() until a user gesture.
        // If the auto-start above silently fails, this ensures passive
        // listening starts on the first click/key/touch anywhere on the page.
        const activateOnGesture = () => {
            if (!this._running && this._mode !== 'active') {
                this._requestStart('passive');
            }
            // Init mic analyser early so double-clap detector starts immediately
            this._initAudioAnalyser();
            document.removeEventListener('click', activateOnGesture);
            document.removeEventListener('keydown', activateOnGesture);
            document.removeEventListener('touchstart', activateOnGesture);
        };
        document.addEventListener('click', activateOnGesture, { once: true });
        document.addEventListener('keydown', activateOnGesture, { once: true });
        document.addEventListener('touchstart', activateOnGesture, { once: true });
    }

    // ── Audio analyser for mic level ────────────────────────────
    async _initAudioAnalyser() {
        if (this._analyser) return;
        try {
            this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const source = this._audioCtx.createMediaStreamSource(this._micStream);

            // Main analyser for level metering (small FFT, smoothed)
            this._analyser = this._audioCtx.createAnalyser();
            this._analyser.fftSize = 256;
            this._analyser.smoothingTimeConstant = 0.6;
            source.connect(this._analyser);

            // Separate analyser for clap detection (large buffer, no smoothing)
            this._clapAnalyser = this._audioCtx.createAnalyser();
            this._clapAnalyser.fftSize = 2048;
            this._clapAnalyser.smoothingTimeConstant = 0;
            source.connect(this._clapAnalyser);

            // Start double-clap detector once we have a mic
            this._startClapDetector();
        } catch (err) {
            // audio analyser init failed — non-critical
        }
    }

    // ── Double-clap detector (acoustic fingerprint) ────────────────
    // Claps are broadband transients — energy spread evenly across all
    // frequencies with a very sharp onset and fast decay.
    // Bangs / mic bumps are bass-heavy with slower decay.
    // We require: (1) loud spike, (2) big rise from previous frame,
    // (3) broadband frequency profile, (4) short transient width.
    _startClapDetector() {
        if (this._clapRAF) return;
        const analyser = this._clapAnalyser;
        if (!analyser) return;

        // Resume AudioContext if it got suspended (e.g. tab went idle)
        if (this._audioCtx && this._audioCtx.state === 'suspended') {
            this._audioCtx.resume().catch(() => {});
        }

        const fftSize = analyser.fftSize;           // 2048
        const binCount = analyser.frequencyBinCount; // 1024
        const timeBuf = new Uint8Array(fftSize);
        const freqBuf = new Uint8Array(binCount);
        const sampleRate = this._audioCtx.sampleRate; // typically 48000
        const binHz = sampleRate / fftSize;            // Hz per bin

        // Frequency band boundaries (bin indices)
        const lowEnd  = Math.floor(500 / binHz);       // 0–500 Hz (bass)
        const midStart = Math.floor(1000 / binHz);     // 1–4 kHz
        const midEnd  = Math.floor(4000 / binHz);
        const hiStart = Math.floor(4000 / binHz);      // 4 kHz+ (presence)

        let prevPeak = 0;
        let firstClapTime = 0;
        const CLAP_PEAK  = 0.35;   // absolute peak threshold (raised from 0.20)
        const SPIKE_RISE = 0.25;   // minimum rise from prev frame (raised from 0.15)
        const MIN_GAP    = 150;    // ms between claps (slightly wider)
        const MAX_GAP    = 600;    // ms (tighter window)
        const COOLDOWN   = 3000;
        const BROADBAND_RATIO = 0.25; // high-freq energy must be ≥ 25% of low-freq
        const MAX_TRANSIENT_SAMPLES = 80; // clap spike < ~80 samples wide (~1.7ms @48kHz)
        let lastTrigger = 0;
        let clapDebugCounter = 0;

        const detect = () => {
            this._clapRAF = requestAnimationFrame(detect);

            // Suppress clap detection during speech, chat mode, or active processing
            if (this.speaking || this._chatMode || this._processingQuery) {
                firstClapTime = 0;
                prevPeak = 0;
                return;
            }

            // Resume AudioContext if suspended (browser throttles inactive tabs)
            if (this._audioCtx && this._audioCtx.state === 'suspended') {
                this._audioCtx.resume().catch(() => {});
                return; // skip this frame, data won't be valid yet
            }

            analyser.getByteTimeDomainData(timeBuf);
            let maxPeak = 0;
            for (let i = 0; i < timeBuf.length; i++) {
                const dev = Math.abs(timeBuf[i] - 128) / 128;
                if (dev > maxPeak) maxPeak = dev;
            }

            const now = performance.now();
            const rise = maxPeak - prevPeak;

            // Periodic debug log
            if (++clapDebugCounter % 300 === 0) {
                console.log(`[clap] peak=${maxPeak.toFixed(3)} rise=${rise.toFixed(3)}`);
            }

            // Step 1: amplitude check — must be loud + sharp rise
            if (maxPeak > CLAP_PEAK && rise > SPIKE_RISE && (now - lastTrigger) > COOLDOWN) {

                // Step 2: frequency profile — claps are broadband, bangs are bass-heavy
                analyser.getByteFrequencyData(freqBuf);
                let lowEnergy = 0, midEnergy = 0, hiEnergy = 0;
                for (let b = 0; b < lowEnd; b++) lowEnergy += freqBuf[b];
                for (let b = midStart; b < midEnd; b++) midEnergy += freqBuf[b];
                for (let b = hiStart; b < binCount; b++) hiEnergy += freqBuf[b];

                // Normalise per-band (different widths)
                const lowAvg = lowEnergy / Math.max(lowEnd, 1);
                const midAvg = midEnergy / Math.max(midEnd - midStart, 1);
                const hiAvg  = hiEnergy / Math.max(binCount - hiStart, 1);

                // Clap: mid+hi must be significant relative to bass
                const isBroadband = (midAvg + hiAvg) / 2 >= lowAvg * BROADBAND_RATIO;

                // Step 3: transient sharpness — count consecutive samples above 50% of peak
                // Claps: very few samples at peak. Bumps/bangs: many.
                const halfPeak = maxPeak * 0.5;
                let transientWidth = 0;
                let inSpike = false;
                for (let i = 0; i < timeBuf.length; i++) {
                    const dev = Math.abs(timeBuf[i] - 128) / 128;
                    if (dev >= halfPeak) {
                        if (!inSpike) inSpike = true;
                        transientWidth++;
                    } else if (inSpike) {
                        break; // only measure the first spike
                    }
                }
                const isSharp = transientWidth <= MAX_TRANSIENT_SAMPLES;

                console.log(`[clap] SPIKE peak=${maxPeak.toFixed(3)} rise=${rise.toFixed(3)} ` +
                    `low=${lowAvg.toFixed(1)} mid=${midAvg.toFixed(1)} hi=${hiAvg.toFixed(1)} ` +
                    `broadband=${isBroadband} width=${transientWidth} sharp=${isSharp}`);

                if (isBroadband && isSharp) {
                    if (firstClapTime === 0) {
                        firstClapTime = now;
                        console.log('[clap] First clap registered');
                    } else {
                        const gap = now - firstClapTime;
                        if (gap >= MIN_GAP && gap <= MAX_GAP) {
                            console.log(`[clap] ✓ DOUBLE CLAP gap=${gap.toFixed(0)}ms`);
                            firstClapTime = 0;
                            lastTrigger = now;
                            this._onDoubleClap();
                            prevPeak = 0;
                            return;
                        } else if (gap > MAX_GAP) {
                            firstClapTime = now;
                            console.log('[clap] First clap (reset, too slow)');
                        }
                    }
                } else {
                    console.log(`[clap] REJECTED — ${!isBroadband ? 'not broadband (bang/thump)' : 'too wide (bump/sustained)'}`);
                }
            }

            if (firstClapTime > 0 && (now - firstClapTime) > MAX_GAP) {
                firstClapTime = 0;
            }

            prevPeak = maxPeak;
        };
        this._clapRAF = requestAnimationFrame(detect);
    }

    _onDoubleClap() {
        // Suppress double-clap entirely while in hands-on chat mode
        if (this._chatMode) return;
        // Suppress when mic is muted
        if (_micMuted) return;
        // If processing, cancel it and return to idle instead of blocking
        if (this._processingQuery) {
            this.cancelProcessing();
            logConvo('Processing interrupted by double clap', 'system');
            return;
        }
        // If already actively listening (e.g. follow-up mode), just log it
        if (this._mode === 'active') {
            logConvo('Double clap detected (already listening)', 'system');
            return;
        }
        // Greet and switch to active listening after greeting finishes
        logConvo('Double clap detected', 'system');
        this._speak(this._randomGreeting(), () => {
            this._requestStart('active');
        });
    }

    // Varied greetings so it doesn't repeat "Hello Sir" every time
    _randomGreeting() {
        const greetings = [
            "At your service, Sir.",
            "Online and ready, Sir.",
            "Standing by, Sir.",
            "Go ahead, Sir.",
            "What can I do for you, Sir?",
            "Ready when you are, Sir.",
            "Listening, Sir.",
            "Yes Sir?",
        ];
        // Avoid repeating the last one
        let pick;
        do {
            pick = greetings[Math.floor(Math.random() * greetings.length)];
        } while (pick === this._lastGreeting && greetings.length > 1);
        this._lastGreeting = pick;
        return pick;
    }

    _startLevelPump() {
        if (this._levelRAF) return;
        if (!this._analyser) { this.orb.setAudioLevel(0); return; }
        const buf = new Uint8Array(this._analyser.frequencyBinCount);
        const pump = () => {
            this._analyser.getByteFrequencyData(buf);
            let sum = 0;
            for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
            const rms = Math.sqrt(sum / buf.length) / 255;
            this.orb.setAudioLevel(rms);
            this._levelRAF = requestAnimationFrame(pump);
        };
        this._levelRAF = requestAnimationFrame(pump);
    }

    _stopLevelPump() {
        if (this._levelRAF) { cancelAnimationFrame(this._levelRAF); this._levelRAF = null; }
        this.orb.setAudioLevel(0);
    }

    // ── Core start/stop with onend-driven transitions ───────────
    // Instead of blind setTimeout, we queue what to start next and
    // let onend do the actual start() call when recognition has
    // fully stopped.

    _requestStart(mode) {
        // mode = 'passive' | 'active'
        if (!this.recognition) return;
        // Mic mute guard — block all recognition starts
        if (_micMuted) { this._pendingStart = null; return; }
        // Mic denied guard — browser refused permission, stop retrying
        if (this._micDenied) { this._pendingStart = null; return; }
        if (this._running) {
            // Recognition is still running — stop it and queue the desired mode
            this._pendingStart = mode;
            this._mode = 'off';
            try { this.recognition.stop(); } catch {}
            return;
        }
        // Not running — start immediately
        this._doStart(mode);
    }

    _doStart(mode) {
        if (!this.recognition) return;
        this._pendingStart = null;
        this._lastProcessed = 0; // always reset — new recognition session = fresh results

        if (mode === 'passive') {
            // Allow passive listening even while speaking — enables wake word interruption
            this._mode = 'passive';
            this._finalTranscript = '';
            try {
                this.recognition.start();
                this._running = true;
                console.log('[ARBITER] Passive wake-word listening started');
            } catch (err) {
                console.warn('[ARBITER] Passive start failed:', err.message);
                this._running = false;
                this._mode = 'off';
                // Retry after a delay
                setTimeout(() => this._requestStart('passive'), 2000);
            }
        } else if (mode === 'active') {
            this._mode = 'active';
            this._finalTranscript = '';
            this._latestDisplay = '';
            this._processingQuery = false;  // reset duplicate guard
            this.orb.setState('listening');
            this._initAudioAnalyser().then(() => {
                this._startLevelPump();
            });

            const bl = document.getElementById('btn-listen');
            if (bl) bl.classList.add('active');

            // Start a safety silence timer (in case no onresult fires at all)
            clearTimeout(this._silenceTimer);
            this._silenceTimer = setTimeout(() => this._finaliseSpeech(), 8000);

            try {
                this.recognition.start();
                this._running = true;
            } catch (err) {
                this._running = false;
                this.orb.setState('idle');
                this._stopLevelPump();
                const bl2 = document.getElementById('btn-listen');
                if (bl2) bl2.classList.remove('active');
                setTimeout(() => this._requestStart('passive'), 500);
            }
        }
    }

    // ── Speech recognition setup ────────────────────────────────
    _initRecognition() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {
            this.recognition = null;
            const bl = document.getElementById('btn-listen');
            if (bl) bl.title = 'Speech recognition not supported in this browser';
            // SpeechRecognition API not available
            return;
        }
        this.recognition = new SR();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.maxAlternatives = 5; // more chances to catch "Arbiter"
        this.recognition.lang = 'en-GB';

        this.recognition.onstart = () => {
            this._running = true;
        };

        // Track which result index we've already processed
        this._lastProcessed = 0;

        // Store the best heard text — NEVER overwrite with shorter/empty
        this._latestDisplay = '';

        // ── Fuzzy wake word matching ──────────────────────────────
        // Chrome often mishears "Arbiter" as "arbor", "Albert",
        // "harbor", "arbiter's", "orbit", etc. We match phonetically.
        // Wake word patterns — phonetic fuzzy match for "Arbiter".
        // Chrome frequently mishears as: Albert, harbor, orbit, arbor, etc.
        const WAKE_PATTERNS = [
            /\barbiter\b/i, /\barbitor\b/i,
            /\barbr?it/i,   /\barbeiter\b/i,
            /\balbert\b/i,  /\barbor\b/i,
            /\borbit\w*/i,  /\bharbor\b/i,
            /\barvit/i,     /\barbat/i,
        ];
        // Regex to strip the wake word + trailing punctuation from transcript
        const WAKE_STRIP = /^.*?\b(?:arbiter|arbitor|arbrit\w*|arbeiter|albert|arbor|orbit\w*|harbor|arvit\w*|arbat\w*)\b[,.\s!?']*/i;

        this._matchesWakeWord = (text) => {
            const lower = text.toLowerCase();
            return WAKE_PATTERNS.some(rx => rx.test(lower));
        };

        this.recognition.onresult = (e) => {
            if (this._mode === 'passive') {
                // ── Passive: scan ALL alternatives for wake word (fuzzy) ──
                for (let i = this._lastProcessed; i < e.results.length; i++) {
                    const result = e.results[i];
                    // Check every alternative transcript Chrome provides
                    let matched = false;
                    let bestTranscript = result[0].transcript.trim();
                    for (let a = 0; a < result.length; a++) {
                        const alt = result[a].transcript.trim();
                        if (this._matchesWakeWord(alt)) {
                            matched = true;
                            bestTranscript = alt;
                            break;
                        }
                    }

                    if (matched) {
                        console.log('[ARBITER] Wake word detected in:', bestTranscript);
                        const afterWake = bestTranscript.replace(WAKE_STRIP, '').trim();
                        // DON'T advance _lastProcessed past this result — let the active
                        // handler re-read it when Chrome finalises with the full sentence.
                        // Only advance past *previous* results.
                        this._lastProcessed = i;

                        // ── Interrupt speech or processing if active ──
                        if (this._processingQuery) {
                            console.log('[ARBITER] Interrupting processing — wake word detected');
                            this.cancelProcessing();
                            logConvo('Processing interrupted', 'system');
                        } else if (this.speaking) {
                            console.log('[ARBITER] Interrupting speech — wake word detected');
                            this.stopSpeaking();
                        }

                        // Seamless switch to active
                        this._mode = 'active';
                        this._finalTranscript = afterWake ? ' ' + afterWake : '';
                        this._latestDisplay = afterWake;
                        this.orb.setState('listening');
                        this._initAudioAnalyser().then(() => this._startLevelPump());
                        const bl = document.getElementById('btn-listen');
                        if (bl) bl.classList.add('active');
                        if (afterWake) logConvo(afterWake, 'user-interim');

                        clearTimeout(this._silenceTimer);
                        this._silenceTimer = setTimeout(() => this._finaliseSpeech(), 4000);
                        return;
                    }
                    if (result.isFinal) this._lastProcessed = i + 1;
                }
                return; // passive — nothing more to do
            }

            // ── Active: accumulate everything the user says ──────────
            // Chrome sometimes resets e.results (length drops) — handle gracefully
            if (e.results.length < this._lastProcessed) {
                this._lastProcessed = 0; // Chrome reset — re-scan from start
            }

            for (let i = this._lastProcessed; i < e.results.length; i++) {
                const result = e.results[i];
                const transcript = result[0].transcript.trim();

                if (result.isFinal && transcript) {
                    this._finalTranscript += ' ' + transcript;
                    this._lastProcessed = i + 1;
                }
            }

            // Build display from final + interim text
            let interim = '';
            for (let i = this._lastProcessed; i < e.results.length; i++) {
                if (!e.results[i].isFinal) {
                    interim += e.results[i][0].transcript;
                }
            }
            const display = (this._finalTranscript + ' ' + interim).trim();
            const cleaned = display.replace(/^(?:arbiter|arbitor|arbrit\w*|arbeiter)[,.\s!?']*/i, '').trim();

            // NEVER overwrite _latestDisplay with shorter text (Chrome resets)
            if (cleaned.length > this._latestDisplay.length) {
                this._latestDisplay = cleaned;
            }
            if (this._latestDisplay) logConvo(this._latestDisplay, 'user-interim');

            // User is speaking — cancel greet/follow-up timeouts, reset silence timer
            if (this._awaitingPostGreet) {
                clearTimeout(this._postGreetTimer);
                this._awaitingPostGreet = false;
            }
            if (this._followUpActive) {
                clearTimeout(this._followUpTimer);
                this._followUpActive = false;
            }
            clearTimeout(this._silenceTimer);
            // 1.5s silence after last speech → process (was 3s — too slow)
            this._silenceTimer = setTimeout(() => this._finaliseSpeech(), 1500);
        };

        this.recognition.onerror = (e) => {
            clearTimeout(this._silenceTimer);
            console.warn('[ARBITER] Recognition error:', e.error, 'mode:', this._mode);

            if (e.error === 'not-allowed') {
                if (!this._micDenied) {
                    logConvo('Microphone access denied. Check browser permissions.', 'system');
                }
                this._micDenied = true;
                this._mode = 'off';
                this._running = false;
                this._pendingStart = null;
                this.orb.setState('idle');
                return;
            }
            // no-speech / aborted / network errors — mark not running so onend or
            // a fallback timer can restart. Chrome sometimes fires onerror WITHOUT
            // a subsequent onend, leaving us stuck if we don't handle it here.
            this._running = false;
            if (e.error === 'no-speech' || e.error === 'aborted') {
                // Normal Chrome behaviour — will restart via onend or fallback
                if (this._mode === 'passive') {
                    // Safety: if onend doesn't fire within 1s, force restart
                    setTimeout(() => {
                        if (!this._running && this._mode !== 'active') {
                            this._mode = 'off';
                            this._requestStart('passive');
                        }
                    }, 1000);
                }
            }
        };

        this.recognition.onend = () => {
            this._running = false;
            this._lastProcessed = 0; // reset for next session

            // While speaking, do NOT restart recognition — prevents mic
            // picking up TTS audio and self-triggering on "Arbiter"
            if (this.speaking) {
                this._mode = 'off';
                this._pendingStart = null;
                return;
            }

            // Queued transition
            if (this._pendingStart) {
                const next = this._pendingStart;
                this._pendingStart = null;
                setTimeout(() => this._doStart(next), 50);
                return;
            }

            // Passive mode ended (Chrome stops continuous after ~60s of no speech)
            if (this._mode === 'passive') {
                this._mode = 'off';
                setTimeout(() => this._doStart('passive'), 500);
                return;
            }

            // Active listening ended unexpectedly (Chrome killed recognition)
            if (this._mode === 'active' && this.orb.state === 'listening') {
                // If we're in the post-greet wait, just silently restart active —
                // During post-greet or follow-up wait, let the timer control —
                // just silently restart active listening if Chrome kills the session.
                if (this._awaitingPostGreet || this._followUpActive) {
                    setTimeout(() => this._doStart('active'), 200);
                    return;
                }

                // Guard: if _finaliseSpeech already handled it, don't duplicate
                if (this._processingQuery) return;

                clearTimeout(this._silenceTimer);
                const raw = (this._finalTranscript || '').trim() || (this._latestDisplay || '').trim();
                const text = raw.replace(/^(?:arbiter|arbitor|arbrit\w*|arbeiter)[,.\s!?']*/i, '').trim();

                this._stopLevelPump();
                const bl = document.getElementById('btn-listen');
                if (bl) bl.classList.remove('active');
                if (text) {
                    // Lock mode: route to unlock handler
                    if (this._locked) {
                        this._handleLockVoice(text);
                        setTimeout(() => this._requestStart('passive'), 600);
                        return;
                    }
                    this._processingQuery = true;
                    this._mode = 'off';
                    this._sendMessage(text);
                } else {
                    this._mode = 'off';
                    this.orb.setState('idle');
                    setTimeout(() => this._requestStart('passive'), 500);
                }
                return;
            }

            // Default: restart passive (unless suppressed)
            if (this._mode === 'off' && !this.speaking && !this._suppressRestart) {
                setTimeout(() => this._requestStart('passive'), 1000);
            }
            this._suppressRestart = false;
        };
    }

    _finaliseSpeech() {
        // If we're in the post-greet or follow-up waiting phase, the respective
        // timer controls the timeout — ignore the silence timer entirely.
        if (this._awaitingPostGreet || this._followUpActive) return;

        // Guard: prevent duplicate sends (silence timer + onend can both fire)
        if (this._processingQuery) return;

        // Silence detected — finalise speech
        this._stopLevelPump();
        const bl = document.getElementById('btn-listen');
        if (bl) bl.classList.remove('active');

        // Use final transcript, or latest display (includes interim), whichever has content
        const raw = (this._finalTranscript || '').trim() || (this._latestDisplay || '').trim();
        const text = raw.replace(/^(?:arbiter|arbitor|arbrit\w*|arbeiter|albert|arbor|orbit\w*|harbor|arvit\w*|arbat\w*)[,.\s!?']*/i, '').trim();

        this._mode = 'off';
        this._pendingStart = null;
        clearTimeout(this._silenceTimer);
        try { this.recognition.stop(); } catch {}

        if (text) {
            // ── Lock mode intercept — route voice to unlock handler ──
            if (this._locked) {
                this._handleLockVoice(text);
                setTimeout(() => this._requestStart('passive'), 600);
                return;
            }

            // ── Check for follow-up option selection via voice ──
            // "option 1", "number 2", "continue with option 3", "choose 1", "go with 2"
            const optMatch = text.match(/\b(?:option|number|choose|go\s+with|select|pick)\s*(\d)\b/i)
                          || text.match(/^(\d)$/);
            if (optMatch && this._activeFollowups && this._activeFollowups.length > 0) {
                const optIdx = parseInt(optMatch[1]) - 1;
                if (optIdx >= 0 && optIdx < this._activeFollowups.length) {
                    const fu = this._activeFollowups[optIdx];
                    console.log(`[ARBITER] Voice selected option ${optIdx + 1}: ${fu.text}`);
                    this._processingQuery = true;
                    this.orb.setState('thinking');
                    this.orb.setAudioLevel(0);
                    this._clearDialogueOptions();
                    this._sendMessage(fu.text);
                    return;
                }
            }

            this._processingQuery = true;
            // Set orb to thinking/ANALYSING immediately so user sees state change
            this.orb.setState('thinking');
            this.orb.setAudioLevel(0);
            this._sendMessage(text);
        } else {
            // Said "Arbiter" with no follow-up — silently wait for the real query.
            // NO greeting — avoids talking over the user and greeting loops.
            // The orb is already in 'listening' state which is visual feedback enough.
            this._requestStart('active');

            // Give the user 6s to start speaking before returning to standby
            clearTimeout(this._silenceTimer);
            clearTimeout(this._postGreetTimer);
            this._awaitingPostGreet = true;
            this._postGreetTimer = setTimeout(() => {
                this._awaitingPostGreet = false;
                this._mode = 'off';
                clearTimeout(this._silenceTimer);
                try { this.recognition.stop(); } catch {}
                this._stopLevelPump();
                const bl2 = document.getElementById('btn-listen');
                if (bl2) bl2.classList.remove('active');
                this.orb.setState('idle');
                setTimeout(() => this._requestStart('passive'), 500);
            }, 6000);
        }
    }

    // ── Lock Mode ─────────────────────────────────────────────────
    _initLock() {
        // Inactivity timer — reset on user interaction
        const resetIdle = () => this._resetLockTimer();
        ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll'].forEach(ev =>
            document.addEventListener(ev, resetIdle, { passive: true })
        );
        this._resetLockTimer();

        // Lock screen UI
        const lockInput = document.getElementById('lock-input');
        const lockSubmit = document.getElementById('lock-submit');
        if (lockInput) {
            lockInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') this._tryPasscodeUnlock();
            });
        }
        if (lockSubmit) {
            lockSubmit.addEventListener('click', () => this._tryPasscodeUnlock());
        }
    }

    _resetLockTimer() {
        if (this._locked) return; // don't reset while locked
        clearTimeout(this._lockTimer);
        this._lockTimer = setTimeout(() => this._lock(), this._lockIdleMs);
    }

    _lock() {
        if (this._locked) return;
        this._locked = true;
        this._lockVoiceDigits = [];
        document.body.classList.add('locked');

        // Close anything open
        if (typeof activeDock !== 'undefined' && activeDock) closeExpandPanels();
        this._closeAnalysisWings();
        this._closeReport();
        this._hideSessionDrawer();
        if (this._chatMode) this._exitChatMode();

        // Stop speaking
        if (this.speaking) this.stopSpeaking();

        // Update lock screen UI
        const lockPrompt = document.getElementById('lock-prompt');
        const lockInput = document.getElementById('lock-input');
        if (lockPrompt) lockPrompt.textContent = 'Voice or type passcode to unlock';
        if (lockInput) { lockInput.value = ''; lockInput.classList.remove('error'); }
        this._updateLockDots(0);

        // Keep passive listening for voice unlock
        this.orb.setState('idle');
        setTimeout(() => this._requestStart('passive'), 500);

        console.log('[ARBITER] Locked — idle timeout');
    }

    _unlock() {
        if (!this._locked) return;
        this._locked = false;
        this._lockVoiceDigits = [];
        document.body.classList.remove('locked');
        this._updateLockDots(0);

        // Clear passcode input
        const lockInput = document.getElementById('lock-input');
        if (lockInput) { lockInput.value = ''; lockInput.classList.remove('error'); lockInput.blur(); }

        // Restart idle timer
        this._resetLockTimer();

        // Resume passive listening
        this.orb.setState('idle');
        setTimeout(() => this._requestStart('passive'), 500);

        console.log('[ARBITER] Unlocked');
    }

    _tryPasscodeUnlock() {
        const lockInput = document.getElementById('lock-input');
        if (!lockInput) return;
        const val = lockInput.value.trim();
        if (val === this._lockCode) {
            this._speak('Welcome back, Sir.');
            this._unlock();
        } else {
            lockInput.classList.add('error');
            this._flashLockDotsError();
            setTimeout(() => {
                lockInput.classList.remove('error');
                lockInput.value = '';
                lockInput.focus();
            }, 800);
        }
    }

    // Process a spoken digit during lock mode. Returns true if handled.
    _handleLockVoice(transcript) {
        if (!this._locked) return false;
        const lower = transcript.toLowerCase().trim();

        // Allow "hands on" to show passcode input while locked
        if (/^(hands[\s-]*on|type|keyboard|passcode|type\s*mode|chat\s*mode)/.test(lower)) {
            const lockRow = document.getElementById('lock-passcode-row');
            const lockPrompt = document.getElementById('lock-prompt');
            const lockInput = document.getElementById('lock-input');
            if (lockRow) lockRow.style.display = 'flex';
            if (lockPrompt) lockPrompt.textContent = 'Enter passcode below';
            if (lockInput) { lockInput.value = ''; lockInput.focus(); }
            return true;
        }

        // Map spoken words to digits
        const digitMap = {
            'zero': '0', 'oh': '0', 'o': '0', '0': '0',
            'one': '1', 'won': '1', '1': '1',
            'two': '2', 'to': '2', 'too': '2', '2': '2',
            'three': '3', 'tree': '3', '3': '3',
            'four': '4', 'for': '4', 'fore': '4', '4': '4',
            'five': '5', '5': '5',
            'six': '6', 'sicks': '6', '6': '6',
            'seven': '7', '7': '7',
            'eight': '8', 'ate': '8', '8': '8',
            'nine': '9', 'nein': '9', '9': '9',
        };

        // Also match full number strings like "9086" spoken as one word
        const digitChars = lower.replace(/[^0-9]/g, '');
        if (digitChars.length >= 4) {
            // Fast speech — all digits came at once (e.g. "9086" or "nine zero eight six" as "9086")
            const entered = digitChars.slice(0, 4);
            this._updateLockDots(4);
            if (entered === this._lockCode) {
                this._speak('Access granted. Welcome back, Sir.');
                this._lockVoiceDigits = [];
                setTimeout(() => this._unlock(), 300);
            } else {
                this._flashLockDotsError();
                this._lockVoiceDigits = [];
                setTimeout(() => {
                    this._updateLockDots(0);
                    // Ensure recognition restarts for another attempt
                    if (!this._running) this._requestStart('passive');
                }, 900);
            }
            return true;
        }

        // Extract digits from transcript word by word
        const words = lower.replace(/[.,!?]/g, '').split(/\s+/);
        let newDigits = false;
        for (const w of words) {
            if (digitMap[w] !== undefined) {
                this._lockVoiceDigits.push(digitMap[w]);
                newDigits = true;
            }
        }

        // If no digits found in speech, ignore silently (don't get stuck)
        if (!newDigits && digitChars.length === 0) {
            return true;
        }

        // Update dots
        this._updateLockDots(Math.min(this._lockVoiceDigits.length, 4));

        // Check if we have 4 digits
        if (this._lockVoiceDigits.length >= 4) {
            const entered = this._lockVoiceDigits.slice(0, 4).join('');
            this._lockVoiceDigits = [];
            if (entered === this._lockCode) {
                this._speak('Access granted. Welcome back, Sir.');
                setTimeout(() => this._unlock(), 300);
            } else {
                this._flashLockDotsError();
                setTimeout(() => {
                    this._updateLockDots(0);
                    if (!this._running) this._requestStart('passive');
                }, 900);
            }
        }

        return true; // always consume input while locked
    }

    _updateLockDots(count) {
        for (let i = 0; i < 4; i++) {
            const dot = document.getElementById(`lock-dot-${i}`);
            if (dot) {
                dot.classList.toggle('filled', i < count);
                dot.classList.remove('error');
            }
        }
    }

    _flashLockDotsError() {
        for (let i = 0; i < 4; i++) {
            const dot = document.getElementById(`lock-dot-${i}`);
            if (dot) { dot.classList.add('error'); dot.classList.remove('filled'); }
        }
        setTimeout(() => {
            for (let i = 0; i < 4; i++) {
                const dot = document.getElementById(`lock-dot-${i}`);
                if (dot) dot.classList.remove('error');
            }
        }, 800);
    }

    // ── Navigation command handler (shared by voice + chat) ─────
    // Returns { speak, log } if handled, or null to pass through to LLM.
    _handleNavCommand(lower) {
        // ── Lock commands ──
        const lockPatterns = [
            /^(go\s*to\s*sleep|lock\s*(it|up|off|out|screen|down|arbiter)?|sleep\s*mode|good\s*night)\s*(arbiter)?[.!]?$/,
            /\block\s*(it|off|out|up|down|screen|arbiter)\b/,
            /\bgo\s*to\s*sleep\b/,
            /\bsleep\s*mode\b/,
        ];
        if (lockPatterns.some(p => p.test(lower))) {
            this._lock();
            return { speak: 'Locking down, Sir. Say the code to wake me.', log: 'Locked by command' };
        }

        // ── Go back / close / dismiss — closes whatever is open ──
        const backPatterns = [
            /^(go\s*back|back|return|home|dashboard|main\s*screen)\s*(arbiter)?[.!]?$/,
            /^(dismiss|close|hide|clear)\s*(panel|panels|view|views|that|it|this|all|everything)?\s*(arbiter)?[.!]?$/,
            /^(thank\s*you|thanks|cheers|ta)\s*(arbiter)?[.!]?$/,
            /^that['']?s?\s*(all|enough|it|fine|good)\s*(arbiter)?[.!]?$/,
            /^(go\s*away|never\s*mind|cancel)\s*(arbiter)?[.!]?$/,
            /^(exit|leave|escape)\s*(panel|this|view)?\s*(arbiter)?[.!]?$/,
        ];
        if (backPatterns.some(p => p.test(lower))) {
            // Close everything: panels, analysis wings, report, session drawer
            if (typeof activeDock !== 'undefined' && activeDock) closeExpandPanels();
            this._closeAnalysisWings();
            this._closeReport();
            this._hideSessionDrawer();
            return { speak: 'Understood, Sir.', log: 'Navigation: returned to dashboard' };
        }

        // ── Open specific panels by name ──
        const panelMap = {
            email:     [/\b(email|mail|inbox)\b/],
            revenue:   [/\b(revenue|money|mrr|income|earnings|subscri)\b/],
            content:   [/\b(content|pipeline|posts?)\b/],
            engage:    [/\b(engage|engagement|analytics)\b/],

            deadlines: [/\b(deadline|roadmap|milestone)\b/],
            bulletins: [/\b(bulletin|news|feed)\b/],
            todo:      [/\b(todo|to.do|tasks?|list)\b/],
            cicd:      [/\b(ci\s*cd|deploy|build|pipeline|freya)\b/],
            claude:    [/\b(claude|api\s*usage|token)\b/],
            ceo:       [/\b(agent\s*orchestrat|agents?|orchestrat|workflow|run\s+workflow)\b/],
            org:       [/\b(ceo|org|organis|team|teams|organisation)\b/],
        };
        const openPanelRx = /^(open|show|go\s*to|navigate\s*to|view|pull\s*up|bring\s*up|display|launch)\s+(the\s+)?(.+?)(\s+panel)?(\s+arbiter)?[.!]?$/;
        const openMatch = lower.match(openPanelRx);
        if (openMatch) {
            const target = openMatch[3];
            for (const [key, patterns] of Object.entries(panelMap)) {
                if (patterns.some(p => p.test(target))) {
                    if (typeof openExpandPanels === 'function') openExpandPanels(key);
                    return { speak: `Opening ${DOCK_EXPAND[key]?.title || key}, Sir.`, log: `Panel opened: ${key}` };
                }
            }
        }

        // ── Mode switching — hands-free ↔ hands-on ──
        const chatOnPatterns = [
            /^(hands[\s-]*on|type\s*mode|chat\s*mode|keyboard|text\s*mode|switch\s*to\s*(typing|chat|text|keyboard))\s*(mode)?\s*(arbiter)?[.!]?$/,
            /^(i\s*want\s*to\s*type|let\s*me\s*type)\s*(arbiter)?[.!]?$/,
        ];
        const chatOffPatterns = [
            /^(hands[\s-]*free|voice\s*mode|listen\s*mode|switch\s*to\s*(voice|listening|hands[\s-]*free))\s*(mode)?\s*(arbiter)?[.!]?$/,
            /^(stop\s*typing|close\s*chat|exit\s*chat|leave\s*chat)\s*(mode)?\s*(arbiter)?[.!]?$/,
        ];
        if (chatOnPatterns.some(p => p.test(lower))) {
            this._enterChatMode();
            return { speak: 'Hands-on mode activated, Sir. Type your message below.', log: 'Switched to hands-on mode' };
        }
        if (chatOffPatterns.some(p => p.test(lower))) {
            if (this._chatMode) this._exitChatMode();
            return { speak: 'Voice mode resumed, Sir. Listening.', log: 'Switched to voice mode' };
        }

        // ── Session commands ──
        const sessionPatterns = [
            { rx: /^(new session|start fresh|clear session|reset session|fresh start)\s*(arbiter)?[.!]?$/, action: 'new' },
            { rx: /^(build|generate|show|create)\s*(a\s*)?(report|session report)\s*(arbiter)?[.!]?$/, action: 'report' },
            { rx: /^(show|list|my)\s*(sessions?|previous sessions?|past sessions?)\s*(arbiter)?[.!]?$/, action: 'list' },
            { rx: /^(close|hide|exit)\s*(report|the report)\s*(arbiter)?[.!]?$/, action: 'close_report' },
        ];
        const sessionMatch = sessionPatterns.find(p => p.rx.test(lower));
        if (sessionMatch) {
            switch (sessionMatch.action) {
                case 'new':
                    this._saveCurrentSession();
                    this._sessionCache = [];
                    this._sessionId = Date.now().toString(36);
                    this._sessionName = null;
                    this.history = [];
                    this._updateSessionBadge();
                    this._closeAnalysisWings();
                    return { speak: 'New session started, Sir. Previous data has been archived.', log: 'Session reset' };
                case 'report':
                    this._buildReport();
                    return { speak: 'Session report compiled, Sir.', log: 'Report built' };
                case 'list':
                    this._showSessionDrawer();
                    return { speak: 'Here are your previous sessions, Sir.', log: 'Session drawer opened' };
                case 'close_report':
                    this._closeReport();
                    return { speak: 'Report closed.', log: 'Report closed' };
            }
        }

        // ── Vision commands — toggle camera ──
        const visionOnPatterns = [
            /\b(switch|turn|go)\s*(to|on)\s*(camera|vision|cam)\b/,
            /\b(open|start|activate|enable)\s*(the\s*)?(camera|vision|cam|webcam)\b/,
            /\bwhat\s*(do|can)\s*you\s*see\b/,
            /\bwhat('?s| is)\s*in front of (you|me)\b/,
            /\blook\s*(at|around)\b/,
            /\bshow\s*me\s*(your|the)\s*(eyes|vision|camera|view)\b/,
        ];
        const visionOffPatterns = [
            /\b(close|stop|turn off|deactivate|disable|exit)\s*(the\s*)?(camera|vision|cam|webcam)\b/,
            /\b(camera|vision|cam)\s*(off|close|stop)\b/,
        ];
        if (visionOffPatterns.some(p => p.test(lower))) {
            _camClose();
            return { speak: 'Vision mode disengaged, Sir.', log: 'Camera closed' };
        }
        if (!_cam.active && visionOnPatterns.some(p => p.test(lower))) {
            _camOpen();
            return { speak: 'Remote vision activated, Sir.', log: 'Camera activated' };
        }

        // ── Close current panel ──
        const closePanelRx = /^(close|hide|dismiss|exit)\s+(the\s+)?(panel|current panel|this panel)\s*(arbiter)?[.!]?$/;
        if (closePanelRx.test(lower)) {
            if (typeof activeDock !== 'undefined' && activeDock) closeExpandPanels();
            return { speak: 'Panel closed, Sir.', log: 'Panel closed via voice' };
        }

        // ── Scroll commands ──
        const scrollDownRx = /^(scroll|page)\s+(down|lower|more)\s*(arbiter)?[.!]?$/;
        const scrollUpRx = /^(scroll|page)\s+(up|higher|back)\s*(arbiter)?[.!]?$/;
        const scrollTopRx = /^(scroll\s+to\s+top|go\s+to\s+top|top\s+of\s+page)\s*(arbiter)?[.!]?$/;
        if (scrollDownRx.test(lower)) {
            const vp = document.querySelector('.dock-panel-viewport.active .dock-panel-inner');
            if (vp) vp.scrollBy({ top: 400, behavior: 'smooth' });
            return { speak: 'Scrolling down.', log: 'Scroll down' };
        }
        if (scrollUpRx.test(lower)) {
            const vp = document.querySelector('.dock-panel-viewport.active .dock-panel-inner');
            if (vp) vp.scrollBy({ top: -400, behavior: 'smooth' });
            return { speak: 'Scrolling up.', log: 'Scroll up' };
        }
        if (scrollTopRx.test(lower)) {
            const vp = document.querySelector('.dock-panel-viewport.active .dock-panel-inner');
            if (vp) vp.scrollTo({ top: 0, behavior: 'smooth' });
            return { speak: 'Back to the top.', log: 'Scroll to top' };
        }

        // ── Add todo via voice ──
        const addTodoRx = /^(add|create|new)\s+(a\s+)?(task|todo|to.do|reminder)\s*[:\-—]?\s*(.+)$/;
        const todoMatch = lower.match(addTodoRx);
        if (todoMatch) {
            const text = todoMatch[4].replace(/\s*(arbiter|please|sir)[.!]?\s*$/i, '').trim();
            if (text) {
                const todos = _loadTodos();
                todos.push({
                    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
                    text: text.charAt(0).toUpperCase() + text.slice(1),
                    date: '', time: '', done: false,
                    created: new Date().toISOString()
                });
                _saveTodos(todos);
                _renderTodoList();
                return { speak: `Task added: ${text}`, log: `Todo added: ${text}` };
            }
        }

        // ── Run pipeline via voice ──
        const runPipelineRx = /^(run|start|launch|execute|trigger)\s+(the\s+)?(full|research|content|technical|gtm|strategy)\s*(pipeline|flow|workflow)?\s*(arbiter)?[.!]?$/;
        const pipelineMatch = lower.match(runPipelineRx);
        if (pipelineMatch) {
            const template = pipelineMatch[3];
            // Open CEO panel and trigger pipeline start
            if (typeof openExpandPanels === 'function') openExpandPanels('ceo');
            return { speak: `Opening orchestration for ${template} pipeline, Sir. Enter your directive.`, log: `Pipeline: ${template}` };
        }

        // ── Approve / Reject pipeline gates ──
        const approveRx = /^(approve|accept|confirm|go\s*ahead|proceed|yes|looks?\s*good)\s*(it|this|that|gate|stage)?\s*(arbiter)?[.!]?$/;
        const rejectRx = /^(reject|deny|decline|stop|abort|no|hold|wait)\s*(it|this|that|gate|stage)?\s*(arbiter)?[.!]?$/;
        if (approveRx.test(lower)) {
            const approveBtn = document.querySelector('.pipeline-approve-btn:not([disabled])');
            if (approveBtn) {
                approveBtn.click();
                return { speak: 'Stage approved, Sir. Proceeding.', log: 'Pipeline gate: approved' };
            }
            return { speak: 'No pending approval gates found, Sir.', log: 'No gate to approve' };
        }
        if (rejectRx.test(lower)) {
            const rejectBtn = document.querySelector('.pipeline-reject-btn:not([disabled])');
            if (rejectBtn) {
                rejectBtn.click();
                return { speak: 'Stage rejected, Sir.', log: 'Pipeline gate: rejected' };
            }
            return { speak: 'No pending rejection gates found, Sir.', log: 'No gate to reject' };
        }

        // ── Trigger manual stage (Publisher "RUN") ──
        const triggerRunRx = /^(run|trigger|activate|publish|go)\s+(the\s+)?(publisher|manual\s*stage|next\s*stage)\s*(arbiter)?[.!]?$/;
        if (triggerRunRx.test(lower)) {
            const runBtn = document.querySelector('.wf-node-run-btn.visible');
            if (runBtn) {
                runBtn.click();
                return { speak: 'Manual stage triggered, Sir.', log: 'Manual stage run' };
            }
            return { speak: 'No manual stage is ready to run, Sir.', log: 'No manual stage ready' };
        }

        // ── Stop / Cancel / Nevermind — interrupt processing ──
        const cancelRx = /^(stop|cancel|abort|nevermind|never\s*mind|forget\s*(it|that)|shut\s*up|enough|that'?s\s*enough|hold\s*on)\s*(arbiter)?[.!]?$/;
        if (cancelRx.test(lower)) {
            if (this._processingQuery) {
                this.cancelProcessing();
                return { speak: 'Cancelled, Sir.', log: 'Processing cancelled by voice' };
            }
            if (this.speaking) {
                this.stopSpeaking();
                return { speak: '', log: 'Speech stopped by voice' };
            }
            return { speak: 'Nothing to cancel, Sir.', log: 'Cancel — nothing active' };
        }

        // Not a nav command — let it through to the LLM
        return null;
    }

    // ── Manual toggle (orb click / mic button) ──────────────────
    _initUI() {
        const btnListen = document.getElementById('btn-listen');
        const btnType = document.getElementById('btn-type');
        const inputWrap = document.getElementById('orb-input-wrap');
        const input = document.getElementById('orb-input');

        // Chat mode state
        this._chatMode = false;

        if (btnListen) {
            btnListen.addEventListener('click', () => this._toggleManual());
        }

        const btnStop = document.getElementById('btn-stop');
        if (btnStop) {
            btnStop.addEventListener('click', () => this.stopSpeaking());
        }

        if (btnType && inputWrap && input) {
            btnType.addEventListener('click', () => {
                const shown = inputWrap.style.display !== 'none';
                inputWrap.style.display = shown ? 'none' : 'block';
                if (!shown) input.focus();
            });
        }

        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && input.value.trim()) {
                    this._sendMessage(input.value.trim());
                    input.value = '';
                }
            });
        }

        // Click orb to toggle chat mode — only in dashboard mode (orb centered)
        const orbCanvas = document.getElementById('orb-canvas');
        if (orbCanvas) orbCanvas.addEventListener('click', () => {
            if (_cam.active) return; // no chat mode during vision
            if (activeDock) return;  // no chat mode when orb is docked to the side
            this._toggleChatMode();
        });

        // Chat panel elements
        const chatClose = document.getElementById('chat-panel-close');
        const chatInput = document.getElementById('chat-input');
        const chatSend  = document.getElementById('chat-send');

        if (chatClose) chatClose.addEventListener('click', () => this._exitChatMode());

        if (chatInput) {
            chatInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && chatInput.value.trim()) {
                    const text = chatInput.value.trim();
                    chatInput.value = '';
                    this._chatSend(text);
                }
            });
        }
        if (chatSend && chatInput) {
            chatSend.addEventListener('click', () => {
                if (chatInput.value.trim()) {
                    const text = chatInput.value.trim();
                    chatInput.value = '';
                    this._chatSend(text);
                }
            });
        }

        // Session controls
        const btnReport = document.getElementById('btn-report');
        const btnNewSession = document.getElementById('btn-new-session');
        const btnSessions = document.getElementById('btn-sessions');
        const reportClose = document.getElementById('report-close');
        if (btnReport) btnReport.addEventListener('click', () => this._buildReport());
        if (btnNewSession) btnNewSession.addEventListener('click', () => this._newSession());
        if (btnSessions) btnSessions.addEventListener('click', () => this._showSessionDrawer());
        if (reportClose) reportClose.addEventListener('click', () => this._closeReport());

        // Keyboard shortcuts: press 1-4 to select dialogue options (only when not typing)
        document.addEventListener('keydown', (e) => {
            // Skip if user is typing in an input/textarea
            const tag = (e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea') return;

            const num = parseInt(e.key);
            if (num >= 1 && num <= 4) {
                const opts = document.querySelectorAll('#dialogue-options .dialogue-opt');
                if (opts.length >= num) {
                    opts[num - 1].click();
                }
            }
        });
    }

    // ── Chat Mode Toggle ─────────────────────────────────────────
    _toggleChatMode() {
        if (this._chatMode) {
            this._exitChatMode();
        } else {
            this._enterChatMode();
        }
    }

    _enterChatMode() {
        // Block chat mode while locked
        if (this._locked) return;

        // If speaking, stop first
        if (this.speaking) this.stopSpeaking();

        // Stop voice recognition
        if (this._mode === 'active' || this._mode === 'passive') {
            this._mode = 'off';
            this._pendingStart = null;
            try { this.recognition.stop(); } catch {}
        }
        clearTimeout(this._silenceTimer);
        this._stopLevelPump();

        this._chatMode = true;
        document.body.classList.add('chat-active');
        const panel = document.getElementById('chat-panel');
        const inputRow = document.getElementById('chat-input-row');
        const orbWrap = document.getElementById('orb-container');
        const orbState = document.getElementById('orb-state');

        if (panel) {
            panel.classList.add('active');
            // Align chat panel bottom with business summary box bottom
            this._alignChatPanel();
        }
        if (inputRow) inputRow.style.display = 'flex';
        if (orbWrap) orbWrap.classList.add('chat-mode');
        if (orbState) orbState.textContent = 'HANDS-ON';
        this.orb.setState('idle');

        // Add system message to chat
        this._chatAddMessage('Hands-on mode active. Type your message below.', 'system');

        // Populate chat with recent conversation history
        if (this.history && this.history.length > 0) {
            const recent = this.history.slice(-10);
            for (const msg of recent) {
                this._chatAddMessage(msg.content, msg.role === 'user' ? 'user' : 'assistant', true);
            }
        }

        // Focus input
        const chatInput = document.getElementById('chat-input');
        if (chatInput) setTimeout(() => chatInput.focus(), 100);

        logConvo('Hands-on mode activated', 'system');
    }

    _exitChatMode() {
        this._chatMode = false;
        document.body.classList.remove('chat-active');
        const panel = document.getElementById('chat-panel');
        const inputRow = document.getElementById('chat-input-row');
        const orbWrap = document.getElementById('orb-container');
        const orbState = document.getElementById('orb-state');

        if (panel) panel.classList.remove('active');
        if (inputRow) inputRow.style.display = 'none';
        if (orbWrap) orbWrap.classList.remove('chat-mode');
        if (orbState) orbState.textContent = 'STANDBY';

        // Resume voice mode
        logConvo('Voice mode resumed', 'system');
        setTimeout(() => this._requestStart('passive'), 300);
    }

    _alignChatPanel() {
        // Align chat panel with the orb area
        const panel = document.getElementById('chat-panel');
        if (!panel) return;

        requestAnimationFrame(() => {
            const viewH = window.innerHeight;
            // Bottom: dock bar is ~60px, leave some gap
            const dockEl = document.querySelector('.mc-dock');
            const dockH = dockEl ? dockEl.getBoundingClientRect().height : 60;
            panel.style.bottom = (dockH + 12) + 'px';

            // Also align top with top of orb canvas
            const canvas = document.getElementById('orb-canvas');
            if (canvas) {
                const canvasRect = canvas.getBoundingClientRect();
                panel.style.top = Math.max(canvasRect.top, 16) + 'px';
            }
        });
    }

    _chatAddMessage(text, role, isHistory = false) {
        const container = document.getElementById('chat-messages');
        if (!container) return;

        const msg = document.createElement('div');

        if (role === 'system') {
            msg.className = 'chat-msg system-msg';
            msg.textContent = text;
        } else {
            msg.className = 'chat-msg ' + (role === 'user' ? 'user' : 'assistant');
            const sender = document.createElement('span');
            sender.className = 'chat-msg-sender';
            sender.textContent = role === 'user' ? 'YOU' : 'ARBITER';
            msg.appendChild(sender);

            const body = document.createElement('span');
            body.innerHTML = mdToHtml(text);
            msg.appendChild(body);

            const time = document.createElement('span');
            time.className = 'chat-msg-time';
            time.textContent = isHistory ? '' : new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
            msg.appendChild(time);
        }

        container.appendChild(msg);
        // Keep max 100 messages
        while (container.children.length > 100) container.removeChild(container.firstChild);
        container.scrollTop = container.scrollHeight;
    }

    async _chatSend(text) {
        // Block chat while locked — only passcode input should work
        if (this._locked) {
            this._chatAddMessage('System is locked. Enter passcode to unlock.', 'system');
            return;
        }

        // Cancel any in-flight request + stop speech when user sends a new message
        if (this._processingQuery || this._activeAbort) {
            this.cancelProcessing();
            logConvo('Previous request cancelled', 'system');
        }
        if (this.speaking) this.stopSpeaking();

        this._clearDialogueOptions();
        // Add user message to chat panel
        this._chatAddMessage(text, 'user');

        // ── Local nav intercept — no API call needed ──
        const lower = text.toLowerCase().trim();
        const navResult = this._handleNavCommand(lower);
        if (navResult) {
            logConvo(text, 'user');
            logConvo(navResult.log, 'system');
            if (navResult.speak) this._chatAddMessage(navResult.speak, 'assistant');
            this.orb.setState('idle');
            return;
        }

        // Show thinking indicator
        const thinkEl = document.createElement('div');
        thinkEl.className = 'chat-msg thinking';
        thinkEl.id = 'chat-thinking';
        thinkEl.textContent = 'Analysing';
        const container = document.getElementById('chat-messages');
        if (container) { container.appendChild(thinkEl); container.scrollTop = container.scrollHeight; }

        // Also send through the normal pipeline (updates history, panels, etc.)
        this.orb.setState('thinking');
        this._processingQuery = true;
        this.history.push({ role: 'user', content: text });
        logConvo(text, 'user');
        const _jtChatId = _jobAdd('chat', text.substring(0, 50));

        // Create abort controller for this request
        if (this._activeAbort) this._activeAbort.abort();
        const abort = new AbortController();
        this._activeAbort = abort;

        try {
            // If camera is active, route through vision endpoint
            let r, d;
            if (_cam.active && _cam.stream) {
                const frameB64 = _camCaptureFrame();
                if (frameB64) {
                    this._chatAddMessage('[FRAME CAPTURED]', 'system');
                    _camScanStart();
                    r = await fetch('/api/jarvis/vision', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ query: text, image: frameB64 }),
                        signal: abort.signal,
                    });
                    d = await r.json();
                    _camScanStop();
                } else {
                    const _chatHeaders = { 'Content-Type': 'application/json' };
                    if (_activeBusinessId) _chatHeaders['X-Business-Id'] = _activeBusinessId;
                    r = await fetch('/api/jarvis/chat', {
                        method: 'POST',
                        headers: _chatHeaders,
                        body: JSON.stringify({ message: text, history: this.history }),
                        signal: abort.signal,
                    });
                    d = await r.json();
                }
            } else {
                const _chatHeaders2 = { 'Content-Type': 'application/json' };
                if (_activeBusinessId) _chatHeaders2['X-Business-Id'] = _activeBusinessId;
                r = await fetch('/api/jarvis/chat', {
                    method: 'POST',
                    headers: _chatHeaders2,
                    body: JSON.stringify({ message: text, history: this.history }),
                    signal: abort.signal,
                });
                d = await r.json();
            }
            this._activeAbort = null;
            const rawReply = d.reply || 'No response.';

            // Remove thinking indicator
            const think = document.getElementById('chat-thinking');
            if (think) think.remove();

            if (d.error) {
                this._chatAddMessage(rawReply, 'system');
                logConvo(rawReply, 'system');
                this.orb.setState('idle');
                this._processingQuery = false;
                _jobComplete(_jtChatId, true);
                return;
            }

            const { spokenText, actions } = this._parseAction(rawReply);
            this.history.push({ role: 'assistant', content: spokenText });
            if (this.history.length > 20) this.history = this.history.slice(-20);

            // Execute actions (panels, desktop automation, etc.)
            for (const act of actions) this._executeAction(act);
            if (d.actions && Array.isArray(d.actions)) {
                for (const act of d.actions) this._executeAction(act);
            }
            if (d.panel) this._renderAnalysisPanel(d.panel);

            // Cache this exchange for session report
            this._cacheExchange(text, spokenText, d.panel || null);

            // Render vision panels if camera is active
            if (_cam.active && spokenText) {
                _camRenderVisionPanels(spokenText, text);
            }

            // Add response to chat panel (no speech in hands-on mode)
            this._lastSpokenReply = spokenText;
            this._chatAddMessage(spokenText, 'assistant');
            logConvo(spokenText, 'arbiter');
            this.orb.setState('idle');
            this._processingQuery = false;
            _jobComplete(_jtChatId);

            // Show dialogue follow-up options (chat panel only in hands-on mode)
            console.log('[ARBITER] followups:', d.followups);
            if (d.followups && Array.isArray(d.followups) && d.followups.length > 0) {
                // In hands-on mode, only show in chat panel — NOT in background #dialogue-options
                this._chatRenderFollowups(d.followups);
            }
        } catch (e) {
            this._activeAbort = null;
            if (e.name === 'AbortError') {
                console.log('[ARBITER] Chat request aborted');
                _jobComplete(_jtChatId, true);
                return; // cancelProcessing() already reset state
            }
            console.error('[ARBITER] Chat error:', e);
            _camScanStop();
            this._processingQuery = false;
            const think = document.getElementById('chat-thinking');
            if (think) think.remove();
            this._chatAddMessage('Connection error. Backend may be offline.', 'system');
            logConvo('Connection error. Backend may be offline.', 'system');
            this.orb.setState('idle');
            _jobComplete(_jtChatId, true);
        }
    }

    _toggleManual() {
        // If in chat mode, ignore voice toggle
        if (this._chatMode) return;

        // If speaking, stop immediately
        if (this.speaking) {
            this.stopSpeaking();
            return;
        }

        if (this._mode === 'active') {
            // Stop active listening
            clearTimeout(this._silenceTimer);
            this._stopLevelPump();
            this.orb.setState('idle');
            const bl = document.getElementById('btn-listen');
            if (bl) bl.classList.remove('active');
            // Stop and go back to passive
            this._mode = 'off';
            this._pendingStart = null;
            try { this.recognition.stop(); } catch {}
            // onend will fire → default case will restart passive
        } else {
            // Force active listening (skip wake word)
            if (this.speaking) { this.synth.cancel(); this.speaking = false; }
            this._requestStart('active');
        }
    }

    // ── Dialogue Options (RPG-style follow-ups — hands-free only) ──
    _renderDialogueOptions(followups) {
        // Only show in hands-free mode — hands-on uses _chatRenderFollowups instead
        if (this._chatMode) return;

        const container = document.getElementById('dialogue-options');
        if (!container) return;

        // Store followups for voice command selection ("option 1", "option 2")
        this._activeFollowups = followups;

        // Clear previous options
        container.innerHTML = '';
        container.classList.remove('picked');

        const hintLabels = { deeper: `${_SVG('search',12)} DEEPER`, compare: `${_SVG('scale',12)} COMPARE`, action: `${_SVG('play',12)} ACTION`, broader: `${_SVG('globe',12)} BROADER` };

        followups.forEach((fu, i) => {
            const btn = document.createElement('button');
            btn.className = 'dialogue-opt';
            const hint = (fu.hint || '').toLowerCase();
            const hintLabel = hintLabels[hint] || hint.toUpperCase() || '';
            btn.innerHTML = `
                <span class="dialogue-opt-num">${i + 1}</span>
                <span class="dialogue-opt-text">
                    ${fu.text}
                    ${hintLabel ? `<span class="dialogue-opt-hint">${hintLabel}</span>` : ''}
                </span>
            `;
            btn.addEventListener('click', () => {
                // Stop any current speech immediately
                if (this.speaking) this.stopSpeaking();
                container.classList.add('picked');
                btn.classList.add('chosen');
                setTimeout(() => {
                    container.innerHTML = '';
                    this._sendMessage(fu.text);
                }, 400);
            });
            container.appendChild(btn);
        });

        // Reset to default positioning for voice mode (below orb)
        container.style.position = '';
        container.style.left = '';
        container.style.top = '';
        container.style.width = '';
        container.style.margin = '';
        container.style.zIndex = '';
    }

    _clearDialogueOptions() {
        this._activeFollowups = null;
        const container = document.getElementById('dialogue-options');
        if (container) {
            container.innerHTML = '';
            container.style.position = '';
            container.style.left = '';
            container.style.top = '';
            container.style.width = '';
            container.style.margin = '';
            container.style.zIndex = '';
        }
    }

    _chatRenderFollowups(followups) {
        const container = document.getElementById('chat-messages');
        if (!container) return;

        const wrap = document.createElement('div');
        wrap.className = 'chat-followups';

        followups.forEach((fu, i) => {
            const btn = document.createElement('button');
            btn.className = 'chat-followup-btn';
            btn.textContent = fu.text;
            btn.addEventListener('click', () => {
                if (this.speaking) this.stopSpeaking();
                wrap.remove();
                this._chatSend(fu.text);
            });
            wrap.appendChild(btn);
        });

        container.appendChild(wrap);
        container.scrollTop = container.scrollHeight;
    }

    // ── Send message to LLM ─────────────────────────────────────
    async _sendMessage(text) {
        // Reset idle lock timer on every interaction
        this._resetLockTimer();

        // Stop any current speech immediately when a new query comes in
        if (this.speaking) this.stopSpeaking();

        // ── Briefing prompt intercept — catch "yes/no" before hitting LLM ──
        if (window._briefingPromptActive) {
            const lower = text.toLowerCase().trim();
            const yesPatterns = /^(yes|yeah|yep|go ahead|sure|please|do it|run it|affirmative|briefing|daily briefing)\b/;
            const noPatterns = /^(no|nah|nope|skip|decline|not now|negative|pass)\b/;
            if (yesPatterns.test(lower)) {
                window._briefingPromptActive = false;
                _dismissBriefingPrompt();
                logConvo(text, 'user');
                this.orb.setState('idle');
                this._processingQuery = false;
                _runMorningBriefing();
                setTimeout(() => this._requestStart('passive'), 500);
                return;
            }
            if (noPatterns.test(lower)) {
                window._briefingPromptActive = false;
                _dismissBriefingPrompt();
                this._clearDialogueOptions();
                logConvo(text, 'user');
                logConvo('Briefing declined', 'system');
                this._processingQuery = false;
                // Stop any current speech (greeting may still be playing)
                if (this.speaking) this.stopSpeaking();
                // Kill recognition and prevent onend from restarting it
                this._suppressRestart = true;
                this._pendingStart = null;
                this._mode = 'off';
                if (this.recognition) {
                    try { this.recognition.abort(); } catch {}
                }
                this.orb.setState('idle');
                // Brief silence then passive standby — no spoken reply
                setTimeout(() => this._requestStart('passive'), 3000);
                return;
            }
            // Anything else (including mic picking up TTS audio) — ignore it entirely.
            // Do NOT forward to the LLM while briefing prompt is active.
            this.orb.setState('idle');
            this._processingQuery = false;
            return;
        }

        // ── Voice intercepts — handle UI commands locally (no LLM cost) ──
        const lower = text.toLowerCase().trim();

        // ── Voice correction: "I said / I meant / correct that to ..." ──
        const correctionRx = /^(?:no[,.]?\s*)?(?:i\s+(?:said|meant|actually\s+said)|correct(?:ion)?\s+(?:that\s+)?to|what\s+i\s+(?:said|meant)\s+was|i\s+actually\s+meant|that(?:'s| is)\s+wrong[,.]?\s*(?:i\s+said)?)\s+(.+)/i;
        const corrMatch = lower.match(correctionRx);
        if (corrMatch) {
            const corrected = text.slice(text.length - corrMatch[1].length); // preserve original casing
            logConvo(text, 'user');
            logConvo(`Correction: "${corrected}"`, 'system');
            // Remove last user entry from history so correction replaces it
            const lastUserIdx = this.history.findLastIndex(h => h.role === 'user');
            if (lastUserIdx >= 0) {
                this.history.splice(lastUserIdx, this.history.length - lastUserIdx);
            }
            this._speak(`Understood. Processing: ${corrected.slice(0, 60)}.`, () => {
                this._sendMessage(corrected);
            });
            return;
        }

        // ── Repeat last reply ──
        const repeatRx = /^(?:repeat\s+(?:that|yourself|last|it)|say\s+(?:that|it)\s+again|what\s+did\s+you\s+say|come\s+again|pardon)\s*(arbiter)?[.!?]?$/;
        if (repeatRx.test(lower)) {
            logConvo(text, 'user');
            if (this._lastSpokenReply) {
                logConvo('Repeating last response.', 'system');
                this.orb.setState('idle');
                this._processingQuery = false;
                this._speak(this._lastSpokenReply);
            } else {
                this.orb.setState('idle');
                this._processingQuery = false;
                this._speak("I haven't said anything yet, Sir.");
            }
            return;
        }

        const navResult = this._handleNavCommand(lower);
        if (navResult) {
            logConvo(text, 'user');
            logConvo(navResult.log, 'system');
            this.orb.setState('idle');
            this._processingQuery = false;
            this._speak(navResult.speak, () => {
                setTimeout(() => this._requestStart('passive'), 500);
            });
            return;
        }

        this._clearDialogueOptions();
        this.orb.setState('thinking');
        this.orb.setAudioLevel(0);
        this._lastUserQuery = text;
        this.history.push({ role: 'user', content: text });
        logConvo(text, 'user');
        logConvo('Processing...', 'system');
        const _jtVoiceId = _jobAdd('voice', text.substring(0, 50));

        // Create abort controller for this request
        if (this._activeAbort) this._activeAbort.abort();
        const abort = new AbortController();
        this._activeAbort = abort;

        try {
            // If camera is active, route through vision endpoint with captured frame
            let r, d;
            if (_cam.active && _cam.stream) {
                const frameB64 = _camCaptureFrame();
                if (frameB64) {
                    logConvo('[Camera frame captured for visual analysis]', 'system');
                    _camScanStart();
                    r = await fetch('/api/jarvis/vision', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ query: text, image: frameB64 }),
                        signal: abort.signal,
                    });
                    d = await r.json();
                    _camScanStop();
                } else {
                    const _vHeaders = { 'Content-Type': 'application/json' };
                    if (_activeBusinessId) _vHeaders['X-Business-Id'] = _activeBusinessId;
                    r = await fetch('/api/jarvis/chat', {
                        method: 'POST',
                        headers: _vHeaders,
                        body: JSON.stringify({ message: text, history: this.history }),
                        signal: abort.signal,
                    });
                    d = await r.json();
                }
            } else {
                const _vHeaders2 = { 'Content-Type': 'application/json' };
                if (_activeBusinessId) _vHeaders2['X-Business-Id'] = _activeBusinessId;
                r = await fetch('/api/jarvis/chat', {
                    method: 'POST',
                    headers: _vHeaders2,
                    body: JSON.stringify({ message: text, history: this.history }),
                    signal: abort.signal,
                });
                d = await r.json();
            }
            this._activeAbort = null;

            const rawReply = d.reply || 'No response.';

            // If the backend flagged an error, show it and return to idle
            if (d.error) {
                logConvo(rawReply, 'system');
                this.orb.setState('idle');
                _jobComplete(_jtVoiceId, true);
                setTimeout(() => this._requestStart('passive'), 500);
                return;
            }

            const { spokenText, actions } = this._parseAction(rawReply);

            this.history.push({ role: 'assistant', content: spokenText });
            if (this.history.length > 20) this.history = this.history.slice(-20);

            // Execute any actions parsed from LLM text
            for (const act of actions) this._executeAction(act);

            // Execute server-side actions (desktop automation, browser opens)
            if (d.actions && Array.isArray(d.actions)) {
                for (const act of d.actions) this._executeAction(act);
            }

            // Show server-side panel if provided (more reliable than LLM-generated JSON)
            if (d.panel) {
                this._renderAnalysisPanel(d.panel);
            }

            // Cache this exchange for session report
            this._cacheExchange(text, spokenText, d.panel || null);

            // Render vision panels if camera is active
            if (_cam.active && spokenText) {
                _camRenderVisionPanels(spokenText, text);
            }

            this._lastSpokenReply = spokenText;
            logConvo(spokenText, 'arbiter');
            this._speak(spokenText);
            _jobComplete(_jtVoiceId);

            // Show dialogue follow-up options
            console.log('[ARBITER] followups (voice):', d.followups);
            if (d.followups && Array.isArray(d.followups) && d.followups.length > 0) {
                this._renderDialogueOptions(d.followups);
            }
        } catch (e) {
            this._activeAbort = null;
            if (e.name === 'AbortError') {
                console.log('[ARBITER] Request aborted');
                _jobComplete(_jtVoiceId, true);
                return; // cancelProcessing() already reset state
            }
            console.error('[ARBITER] Chat error:', e);
            _camScanStop();
            this.orb.setState('idle');
            this._processingQuery = false;
            logConvo('Connection error. Backend may be offline.', 'system');
            _jobComplete(_jtVoiceId, true);
            setTimeout(() => this._requestStart('passive'), 500);
        }
    }

    _parseAction(reply) {
        // Strip markdown code fences the LLM sometimes wraps JSON in
        let cleaned = reply.replace(/```(?:json)?\s*/gi, '').replace(/```/g, '');

        // Strip inline JSON arrays/objects the LLM leaks into speech text
        // e.g. [{"action":"show_panel","panel":{...}}] embedded mid-sentence
        cleaned = cleaned.replace(/\[?\{["\s]*action["\s]*:[\s\S]*$/i, '');  // trailing JSON blob
        cleaned = cleaned.replace(/\[?\{"action"[\s\S]*?\}\]?/g, '');       // inline JSON blob

        // Strip leaked [show_panel fragments the LLM sometimes emits as raw text
        cleaned = cleaned.replace(/\[show_panel\b[^\]]*\]?/gi, '').trim();

        // Strip [FOLLOWUPS] blocks (handled server-side, should never reach client)
        cleaned = cleaned.replace(/\[FOLLOWUPS\]\s*\[.*$/si, '').trim();

        const lines = cleaned.trim().split('\n');
        const actions = [];
        const spokenLines = [];
        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
                try {
                    const parsed = JSON.parse(trimmed);
                    if (parsed.action) { actions.push(parsed); continue; }
                } catch {}
            }
            // Skip lines that are just leftover JSON fragments
            if (/^\s*[\[{\]},]/.test(trimmed) && /"/.test(trimmed)) continue;
            spokenLines.push(line);
        }
        const spokenText = spokenLines.join('\n').trim();
        return { spokenText: spokenText || reply, action: actions.length ? actions[0] : null, actions };
    }

    _executeAction(action) {
        switch (action.action) {
            case 'open_browser':
                if (action.url) { console.log('[ARBITER] Opening:', action.url); window.open(action.url, '_blank'); }
                break;
            case 'refresh_dashboard':
                refreshAll();
                break;
            case 'focus_panel':
                const panel = document.getElementById(action.panel_id);
                if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
                break;
            case 'show_panel':
                if (action.panel) this._renderAnalysisPanel(action.panel);
                break;
            case 'camera_on':
                _camOpen();
                break;
            case 'camera_off':
                _camClose();
                break;
            default:
                console.log('[ARBITER] Unknown action:', action.action);
        }
    }

    // ── Analysis Wing Panel Renderer (dual inline panels) ───────
    _renderAnalysisPanel(panel, _bypassQueue = false) {
        // ── Overlap guard: if busy, show notification banner instead of overlaying ──
        const _wouldOverlap = () => {
            if (typeof activeDock !== 'undefined' && activeDock) return true;
            const wL = document.getElementById('analysis-wing-left');
            return wL && wL.classList.contains('active');
        };
        if (!_bypassQueue && _wouldOverlap()) {
            _showPanelNotif(panel, this);
            return;
        }
        const wingL = document.getElementById('analysis-wing-left');
        const wingR = document.getElementById('analysis-wing-right');
        const bodyL = document.getElementById('analysis-body-left');
        const bodyR = document.getElementById('analysis-body-right');
        const titleL = document.getElementById('analysis-title-left');
        const titleR = document.getElementById('analysis-title-right');
        if (!wingL || !wingR || !bodyL || !bodyR) return;

        // Clean up previous charts (no sidebar restore — avoids blackout flash)
        if (this._analysisCharts) { this._analysisCharts.forEach(c => { try { c.destroy(); } catch {} }); }
        this._analysisCharts = [];
        if (this._analysisChart) { try { this._analysisChart.destroy(); } catch {} this._analysisChart = null; }

        // Clear body content (in-place swap if already visible — no flicker)
        bodyL.innerHTML = '';
        bodyR.innerHTML = '';

        // Split content: left wing = charts/tables/images, right wing = stats/summary/hero/status_grid
        const sections = panel.sections || [panel];

        // Collect left-side and right-side content from all sections
        const leftData = { chart: null, table: null, image_url: null, comparison_matrix: null,
            heatmap: null, quadrant: null, calendar_heatmap: null, title: panel.title || 'ANALYSIS' };
        const rightData = { stats: [], hero: null, status_grid: null, summary: null,
            insights: [], recommendations: [], scorecard: null, trend_indicators: null,
            pros_cons: null, swot: null, risk_matrix: null, timeline: null, key_metrics: [],
            gauges: null, funnel: null, title: 'INSIGHTS' };

        for (const section of sections) {
            if (section.chart && !leftData.chart) leftData.chart = section.chart;
            if (section.table && !leftData.table) leftData.table = section.table;
            if (section.image_url && !leftData.image_url) leftData.image_url = section.image_url;
            if (section.comparison_matrix && !leftData.comparison_matrix) leftData.comparison_matrix = section.comparison_matrix;
            if (section.heatmap && !leftData.heatmap) leftData.heatmap = section.heatmap;
            if (section.quadrant && !leftData.quadrant) leftData.quadrant = section.quadrant;
            if (section.calendar_heatmap && !leftData.calendar_heatmap) leftData.calendar_heatmap = section.calendar_heatmap;
            if (section.hero && !rightData.hero) rightData.hero = section.hero;
            if (section.status_grid) rightData.status_grid = section.status_grid;
            if (section.stats && section.stats.length) rightData.stats = rightData.stats.concat(section.stats);
            if (section.key_metrics && section.key_metrics.length) rightData.key_metrics = rightData.key_metrics.concat(section.key_metrics);
            if (section.summary) rightData.summary = section.summary;
            if (section.insights && section.insights.length) rightData.insights = rightData.insights.concat(section.insights);
            if (section.recommendations && section.recommendations.length) rightData.recommendations = rightData.recommendations.concat(section.recommendations);
            if (section.scorecard && !rightData.scorecard) rightData.scorecard = section.scorecard;
            if (section.trend_indicators && !rightData.trend_indicators) rightData.trend_indicators = section.trend_indicators;
            if (section.pros_cons && !rightData.pros_cons) rightData.pros_cons = section.pros_cons;
            if (section.swot && !rightData.swot) rightData.swot = section.swot;
            if (section.risk_matrix && !rightData.risk_matrix) rightData.risk_matrix = section.risk_matrix;
            if (section.timeline && !rightData.timeline) rightData.timeline = section.timeline;
            if (section.gauges && !rightData.gauges) rightData.gauges = section.gauges;
            if (section.funnel && !rightData.funnel) rightData.funnel = section.funnel;
        }

        // If there's a section title from the panel, use it
        if (panel.title) {
            leftData.title = panel.title;
            rightData.title = panel.title + ' — INSIGHTS';
        }

        titleL.textContent = leftData.title;
        titleR.textContent = rightData.title;

        // Determine what goes where
        const hasLeft = leftData.chart || leftData.table || leftData.image_url || leftData.comparison_matrix
            || leftData.heatmap || leftData.quadrant || leftData.calendar_heatmap;
        const hasRight = rightData.stats.length || rightData.hero || rightData.status_grid || rightData.summary
            || rightData.insights.length || rightData.recommendations.length || rightData.scorecard
            || rightData.trend_indicators || rightData.pros_cons || rightData.swot
            || rightData.risk_matrix || rightData.timeline || rightData.gauges || rightData.funnel
            || rightData.key_metrics.length;

        if (hasLeft) {
            this._renderSection(bodyL, {
                chart: leftData.chart,
                table: leftData.table,
                image_url: leftData.image_url,
                comparison_matrix: leftData.comparison_matrix,
                heatmap: leftData.heatmap,
                quadrant: leftData.quadrant,
                calendar_heatmap: leftData.calendar_heatmap,
            });
        } else {
            // No chart/table — put stats on left, keep right for analysis
            const halfStats = rightData.stats.splice(0, Math.ceil(rightData.stats.length / 2));
            this._renderSection(bodyL, { stats: halfStats, hero: rightData.hero, status_grid: rightData.status_grid,
                trend_indicators: rightData.trend_indicators, gauges: rightData.gauges,
                pros_cons: rightData.pros_cons, swot: rightData.swot });
            rightData.hero = null;
            rightData.status_grid = null;
            rightData.trend_indicators = null;
            rightData.gauges = null;
            rightData.pros_cons = null;
            rightData.swot = null;
        }

        if (hasRight || rightData.stats.length || rightData.summary) {
            this._renderSection(bodyR, {
                hero: rightData.hero,
                status_grid: rightData.status_grid,
                stats: rightData.stats,
                key_metrics: rightData.key_metrics,
                trend_indicators: rightData.trend_indicators,
                gauges: rightData.gauges,
                scorecard: rightData.scorecard,
                funnel: rightData.funnel,
                insights: rightData.insights,
                recommendations: rightData.recommendations,
                pros_cons: rightData.pros_cons,
                swot: rightData.swot,
                risk_matrix: rightData.risk_matrix,
                timeline: rightData.timeline,
                summary: rightData.summary,
            });
        } else {
            for (const section of sections) {
                this._renderSection(bodyR, section);
            }
        }

        // Only animate sidebars out on fresh open (not on content swap)
        if (!alreadyOpen) {
            document.body.classList.add('panel-focus');
            const floatL = document.getElementById('float-left');
            const floatR = document.getElementById('float-right');
            if (floatL) floatL.classList.add('hidden');
            if (floatR) floatR.classList.add('hidden');
        }

        // Show both wings (no-op if already active — smooth content swap)
        wingL.classList.add('active');
        wingR.classList.add('active');

        // Scroll wing bodies to top for new content
        bodyL.scrollTop = 0;
        bodyR.scrollTop = 0;

        // Close handlers
        const closeWings = () => { this._closeAnalysisWings(); };
        document.getElementById('analysis-close-left').onclick = closeWings;
        document.getElementById('analysis-close-right').onclick = closeWings;
    }

    // ── Close analysis wings ──────────────────────────────────────
    _closeAnalysisWings() {
        const wingL = document.getElementById('analysis-wing-left');
        const wingR = document.getElementById('analysis-wing-right');
        if (wingL) wingL.classList.remove('active');
        if (wingR) wingR.classList.remove('active');
        if (this._analysisCharts) { this._analysisCharts.forEach(c => c.destroy()); this._analysisCharts = []; }
        if (this._analysisChart) { this._analysisChart.destroy(); this._analysisChart = null; }

        // Restore sidebars
        document.body.classList.remove('panel-focus');
        const floatL = document.getElementById('float-left');
        const floatR = document.getElementById('float-right');
        if (floatL) floatL.classList.remove('hidden');
        if (floatR) floatR.classList.remove('hidden');
    }

    // ── Session Cache & Report ──────────────────────────────────
    _cacheExchange(query, reply, panel) {
        this._sessionCache.push({
            id: Date.now().toString(36),
            ts: new Date().toISOString(),
            query,
            reply,
            panel: panel ? JSON.parse(JSON.stringify(panel)) : null, // deep clone
        });
        this._updateSessionBadge();
        // Auto-save to localStorage every 3 exchanges
        if (this._sessionCache.length % 3 === 0) this._saveCurrentSession();
        console.log(`[SESSION] Cached exchange #${this._sessionCache.length}: "${query.slice(0,40)}…"`);
    }

    _updateSessionBadge() {
        const badge = document.getElementById('session-badge');
        if (badge) {
            badge.textContent = this._sessionCache.length;
            badge.style.display = this._sessionCache.length > 0 ? 'inline-flex' : 'none';
        }
    }

    _newSession() {
        if (this._sessionCache.length > 0 &&
            !confirm(`Clear ${this._sessionCache.length} cached queries and start a new session?`)) return;
        this._saveCurrentSession();
        this._sessionCache = [];
        this._sessionId = Date.now().toString(36);
        this._sessionName = null;
        this.history = [];
        this._updateSessionBadge();
        this._closeAnalysisWings();
        // Clear chat messages
        const msgs = document.getElementById('chat-messages');
        if (msgs) msgs.innerHTML = '';
        this._chatAddMessage('New session started. Previous context cleared.', 'system');
        logConvo('Session reset', 'system');
    }

    // ── Session Persistence (localStorage) ──────────────────────

    _autoRestoreLastSession() {
        try {
            const sessions = this._loadAllSessions();
            if (sessions.length === 0) return;
            // Restore the most recent session (first in the array)
            const last = sessions[0];
            if (!last || !last.cache || last.cache.length === 0) return;
            this._sessionCache = last.cache;
            this._sessionId = last.id;
            this._sessionName = last.name;
            this.history = last.history || [];
            this._updateSessionBadge();
            // Replay last few exchanges into chat view
            const msgs = document.getElementById('chat-messages');
            if (msgs) {
                for (const entry of this._sessionCache.slice(-5)) {
                    this._chatAddMessage(entry.query, 'user', true);
                    if (entry.reply) this._chatAddMessage(entry.reply, 'assistant', true);
                }
            }
            console.log(`[SESSION] Auto-restored: "${last.name}" (${last.count} queries, ${(this.history || []).length} history turns)`);
        } catch (e) {
            console.warn('[SESSION] Auto-restore failed:', e);
        }
    }

    _saveCurrentSession() {
        if (this._sessionCache.length === 0) return;
        try {
            const sessions = this._loadAllSessions();
            // Auto-generate session name from first query
            const name = this._sessionName ||
                this._sessionCache[0].query.slice(0, 50) +
                (this._sessionCache[0].query.length > 50 ? '…' : '');
            const entry = {
                id: this._sessionId,
                name,
                ts: new Date().toISOString(),
                count: this._sessionCache.length,
                cache: this._sessionCache,
                history: this.history.slice(-10),
            };
            // Replace existing or append
            const idx = sessions.findIndex(s => s.id === this._sessionId);
            if (idx >= 0) sessions[idx] = entry;
            else sessions.unshift(entry);
            // Keep max 20 sessions
            if (sessions.length > 20) sessions.length = 20;
            localStorage.setItem('arbiter_sessions', JSON.stringify(sessions));
            console.log(`[SESSION] Saved session "${name}" (${entry.count} queries)`);
        } catch (e) {
            console.warn('[SESSION] localStorage save failed:', e);
        }
    }

    _loadAllSessions() {
        try {
            return JSON.parse(localStorage.getItem('arbiter_sessions') || '[]');
        } catch { return []; }
    }

    _restoreSession(sessionId) {
        const sessions = this._loadAllSessions();
        const session = sessions.find(s => s.id === sessionId);
        if (!session) return;
        // Save current session first
        this._saveCurrentSession();
        // Restore
        this._sessionCache = session.cache || [];
        this._sessionId = session.id;
        this._sessionName = session.name;
        this.history = session.history || [];
        this._updateSessionBadge();
        this._closeAnalysisWings();
        this._closeReport();
        // Clear and populate chat
        const msgs = document.getElementById('chat-messages');
        if (msgs) msgs.innerHTML = '';
        this._chatAddMessage(`Session restored: "${session.name}" (${session.count} queries)`, 'system');
        // Replay last few exchanges into chat view
        for (const entry of this._sessionCache.slice(-5)) {
            this._chatAddMessage(entry.query, 'user', true);
            if (entry.reply) this._chatAddMessage(entry.reply, 'assistant', true);
        }
        logConvo(`Session restored: ${session.name}`, 'system');
        this._hideSessionDrawer();
    }

    _deleteSession(sessionId) {
        const sessions = this._loadAllSessions().filter(s => s.id !== sessionId);
        localStorage.setItem('arbiter_sessions', JSON.stringify(sessions));
        // Refresh drawer if open
        const drawer = document.getElementById('session-drawer');
        if (drawer && drawer.classList.contains('active')) this._showSessionDrawer();
    }

    _showSessionDrawer() {
        let drawer = document.getElementById('session-drawer');
        if (!drawer) {
            drawer = document.createElement('div');
            drawer.id = 'session-drawer';
            drawer.className = 'session-drawer';
            document.body.appendChild(drawer);
        }
        // Auto-save current session so it appears in the list
        this._saveCurrentSession();
        const sessions = this._loadAllSessions();
        drawer.innerHTML = `
            <div class="session-drawer-header">
                <span class="session-drawer-title">SESSIONS</span>
                <button class="session-drawer-close" id="session-drawer-close">✕</button>
            </div>
            <div class="session-drawer-list" id="session-drawer-list">
                ${sessions.length === 0 ? '<div class="session-drawer-empty">No saved sessions</div>' :
                sessions.map(s => `
                    <div class="session-drawer-item ${s.id === this._sessionId ? 'active' : ''}" data-sid="${s.id}">
                        <div class="session-drawer-item-name">${this._escHtml(s.name)}</div>
                        <div class="session-drawer-item-meta">
                            ${s.count} queries · ${new Date(s.ts).toLocaleDateString()} ${new Date(s.ts).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}
                        </div>
                        <button class="session-drawer-item-del" data-del="${s.id}" title="Delete session">✕</button>
                    </div>
                `).join('')}
            </div>`;
        drawer.classList.add('active');
        // Event listeners
        drawer.querySelector('#session-drawer-close').onclick = () => this._hideSessionDrawer();
        drawer.querySelectorAll('.session-drawer-item').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.classList.contains('session-drawer-item-del')) return;
                this._restoreSession(el.dataset.sid);
            });
        });
        drawer.querySelectorAll('.session-drawer-item-del').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this._deleteSession(btn.dataset.del);
            });
        });
    }

    _hideSessionDrawer() {
        const drawer = document.getElementById('session-drawer');
        if (drawer) drawer.classList.remove('active');
    }

    _buildReport() {
        if (this._sessionCache.length === 0) {
            this._chatAddMessage('No data cached this session. Run some queries first.', 'system');
            return;
        }

        // Destroy any previous report charts
        if (this._reportCharts) { this._reportCharts.forEach(c => c.destroy()); }
        this._reportCharts = [];

        const overlay = document.getElementById('report-overlay');
        const body = document.getElementById('report-body');
        const meta = document.getElementById('report-meta');
        if (!overlay || !body) return;

        body.innerHTML = '';
        const count = this._sessionCache.length;
        const first = new Date(this._sessionCache[0].ts);
        const last = new Date(this._sessionCache[count - 1].ts);
        meta.textContent = `${count} queries · ${first.toLocaleTimeString()} – ${last.toLocaleTimeString()} · ${first.toLocaleDateString()}`;

        // ── HIGH-LEVEL OVERVIEW CARD ──────────────────────────────────
        // Aggregate all stats, key metrics, and summaries across the session
        const allStats = [];
        const allKeyMetrics = [];
        const allInsights = [];
        const allRecommendations = [];
        const allSummaries = [];
        const topicSet = new Set();

        for (const entry of this._sessionCache) {
            if (!entry.panel) continue;
            const sections = entry.panel.sections || [entry.panel];
            for (const s of sections) {
                if (s.title) topicSet.add(s.title);
                if (s.stats && Array.isArray(s.stats)) allStats.push(...s.stats);
                if (s.key_metrics && Array.isArray(s.key_metrics)) allKeyMetrics.push(...s.key_metrics);
                if (s.insights && Array.isArray(s.insights)) allInsights.push(...s.insights);
                if (s.recommendations && Array.isArray(s.recommendations)) allRecommendations.push(...s.recommendations);
                if (s.summary) allSummaries.push(s.summary);
            }
            if (entry.panel.title) topicSet.add(entry.panel.title);
            if (entry.panel.summary) allSummaries.push(entry.panel.summary);
        }

        // Overview section — session stats at a glance
        const overviewSection = document.createElement('div');
        overviewSection.className = 'report-section';

        const overviewHeader = document.createElement('div');
        overviewHeader.className = 'report-section-header';
        overviewHeader.innerHTML = `
            <span class="report-section-num">◆</span>
            <span class="report-section-query">SESSION OVERVIEW</span>
            <span class="report-section-time">${first.toLocaleDateString()}</span>`;
        overviewSection.appendChild(overviewHeader);

        // Summary stats grid
        const overviewStats = [
            { label: 'QUERIES', value: `${count}`, status: null },
            { label: 'DURATION', value: this._formatDuration(last - first), status: null },
            { label: 'TOPICS', value: `${topicSet.size}`, status: null },
            { label: 'DATA POINTS', value: `${allStats.length}`, status: null },
        ];

        const overviewViz = document.createElement('div');
        overviewViz.className = 'report-viz-container';
        this._renderSection(overviewViz, { stats: overviewStats });
        overviewSection.appendChild(overviewViz);

        // Topic list
        if (topicSet.size > 0) {
            const topicEl = document.createElement('div');
            topicEl.className = 'report-topic-list';
            topicEl.innerHTML = Array.from(topicSet)
                .map(t => `<span class="report-topic-tag">${this._escHtml(t)}</span>`).join('');
            overviewSection.appendChild(topicEl);
        }

        // Aggregated summaries
        if (allSummaries.length > 0) {
            const summaryEl = document.createElement('div');
            summaryEl.className = 'report-summary-block';
            // Deduplicate and limit
            const unique = [...new Set(allSummaries)].slice(0, 6);
            summaryEl.innerHTML = unique.map(s => `<p class="report-summary-line">▸ ${this._escHtml(s)}</p>`).join('');
            overviewSection.appendChild(summaryEl);
        }

        body.appendChild(overviewSection);

        // ── KEY INSIGHTS & RECOMMENDATIONS (aggregated) ───────────────
        if (allInsights.length > 0 || allRecommendations.length > 0) {
            const stratSection = document.createElement('div');
            stratSection.className = 'report-section';

            const stratHeader = document.createElement('div');
            stratHeader.className = 'report-section-header';
            stratHeader.innerHTML = `
                <span class="report-section-num">◇</span>
                <span class="report-section-query">KEY INSIGHTS & RECOMMENDATIONS</span>`;
            stratSection.appendChild(stratHeader);

            const stratViz = document.createElement('div');
            stratViz.className = 'report-viz-container';

            // Deduplicate insights by text
            const seenInsights = new Set();
            const uniqueInsights = allInsights.filter(i => {
                if (seenInsights.has(i.text)) return false;
                seenInsights.add(i.text); return true;
            }).slice(0, 8);

            const seenRecs = new Set();
            const uniqueRecs = allRecommendations.filter(r => {
                if (seenRecs.has(r.text)) return false;
                seenRecs.add(r.text); return true;
            }).slice(0, 6);

            if (uniqueInsights.length > 0) {
                this._renderSection(stratViz, { insights: uniqueInsights });
            }
            if (uniqueRecs.length > 0) {
                this._renderSection(stratViz, { recommendations: uniqueRecs });
            }
            stratSection.appendChild(stratViz);
            body.appendChild(stratSection);
        }

        // ── DETAILED RESULTS — one section per exchange (data only) ───
        for (let i = 0; i < count; i++) {
            const entry = this._sessionCache[i];
            // Skip entries with no panel data and no meaningful reply
            if (!entry.panel && (!entry.reply || entry.reply.length < 20)) continue;

            const section = document.createElement('div');
            section.className = 'report-section';

            // Header — use panel title if available, otherwise truncated query
            const panelTitle = entry.panel?.title ||
                (entry.panel?.sections?.[0]?.title) ||
                entry.query.slice(0, 80);
            const header = document.createElement('div');
            header.className = 'report-section-header';
            header.innerHTML = `<span class="report-section-num">${i + 1}</span>
                <span class="report-section-query">${this._escHtml(panelTitle)}</span>
                <span class="report-section-time">${new Date(entry.ts).toLocaleTimeString()}</span>`;
            section.appendChild(header);

            // ARBITER's analysis (the reply) — condensed
            if (entry.reply) {
                const replyEl = document.createElement('div');
                replyEl.className = 'report-reply';
                replyEl.textContent = entry.reply;
                section.appendChild(replyEl);
            }

            // Visualizations — re-render all panel data
            if (entry.panel) {
                const vizContainer = document.createElement('div');
                vizContainer.className = 'report-viz-container';
                section.appendChild(vizContainer);
                this._renderReportPanel(vizContainer, entry.panel);
            }

            body.appendChild(section);
        }

        overlay.classList.add('active');
        document.body.classList.add('report-active');
    }

    _formatDuration(ms) {
        const s = Math.floor(ms / 1000);
        if (s < 60) return `${s}s`;
        const m = Math.floor(s / 60);
        if (m < 60) return `${m}m ${s % 60}s`;
        const h = Math.floor(m / 60);
        return `${h}h ${m % 60}m`;
    }

    _renderReportPanel(container, panel) {
        const sections = panel.sections || [panel];

        // Collect left-side and right-side data exactly like _renderAnalysisPanel
        const leftData = { chart: null, table: null, image_url: null, comparison_matrix: null,
            heatmap: null, quadrant: null, calendar_heatmap: null };
        const rightData = { hero: null, status_grid: null, stats: [], key_metrics: [],
            trend_indicators: null, gauges: null, scorecard: null, funnel: null,
            insights: null, recommendations: null, pros_cons: null, swot: null,
            risk_matrix: null, timeline: null, summary: null };

        for (const s of sections) {
            if (s.chart) leftData.chart = s.chart;
            if (s.table) leftData.table = s.table;
            if (s.image_url) leftData.image_url = s.image_url;
            if (s.comparison_matrix) leftData.comparison_matrix = s.comparison_matrix;
            if (s.heatmap) leftData.heatmap = s.heatmap;
            if (s.quadrant) leftData.quadrant = s.quadrant;
            if (s.calendar_heatmap) leftData.calendar_heatmap = s.calendar_heatmap;
            if (s.hero) rightData.hero = s.hero;
            if (s.status_grid) rightData.status_grid = s.status_grid;
            if (s.stats && Array.isArray(s.stats)) rightData.stats.push(...s.stats);
            if (s.key_metrics && Array.isArray(s.key_metrics)) rightData.key_metrics.push(...s.key_metrics);
            if (s.trend_indicators) rightData.trend_indicators = s.trend_indicators;
            if (s.gauges) rightData.gauges = s.gauges;
            if (s.scorecard) rightData.scorecard = s.scorecard;
            if (s.funnel) rightData.funnel = s.funnel;
            if (s.insights) rightData.insights = s.insights;
            if (s.recommendations) rightData.recommendations = s.recommendations;
            if (s.pros_cons) rightData.pros_cons = s.pros_cons;
            if (s.swot) rightData.swot = s.swot;
            if (s.risk_matrix) rightData.risk_matrix = s.risk_matrix;
            if (s.timeline) rightData.timeline = s.timeline;
            if (s.summary) rightData.summary = s.summary;
        }

        const hasLeft = leftData.chart || leftData.table || leftData.image_url ||
            leftData.comparison_matrix || leftData.heatmap || leftData.quadrant || leftData.calendar_heatmap;

        // Create a two-column layout inside the report section
        const row = document.createElement('div');
        row.className = 'report-viz-row';
        container.appendChild(row);

        if (hasLeft) {
            const leftCol = document.createElement('div');
            leftCol.className = 'report-viz-col report-viz-left';
            row.appendChild(leftCol);
            this._renderSection(leftCol, leftData);
        }

        const hasRight = rightData.hero || rightData.status_grid || rightData.stats.length ||
            rightData.key_metrics.length || rightData.trend_indicators || rightData.gauges ||
            rightData.scorecard || rightData.funnel || rightData.insights ||
            rightData.recommendations || rightData.pros_cons || rightData.swot ||
            rightData.risk_matrix || rightData.timeline || rightData.summary;

        if (hasRight) {
            const rightCol = document.createElement('div');
            rightCol.className = 'report-viz-col report-viz-right';
            row.appendChild(rightCol);
            this._renderSection(rightCol, rightData);
        }

        // If neither side had data, render raw sections
        if (!hasLeft && !hasRight) {
            for (const s of sections) {
                this._renderSection(container, s);
            }
        }
    }

    _closeReport() {
        const overlay = document.getElementById('report-overlay');
        if (overlay) overlay.classList.remove('active');
        document.body.classList.remove('report-active');
        // Destroy charts rendered inside the report (they share _analysisCharts)
        if (this._analysisCharts) { this._analysisCharts.forEach(c => { try { c.destroy(); } catch {} }); this._analysisCharts = []; }
        if (this._analysisChart) { try { this._analysisChart.destroy(); } catch {} this._analysisChart = null; }
    }

    _escHtml(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    // ── Render a single table cell ──────────────────────────────
    _renderTableCell(tr, cell) {
        const td = document.createElement('td');
        const str = String(cell ?? '');
        if (str.startsWith('+') || str.includes('↑')) td.className = 'at-positive';
        else if (str.startsWith('-') || str.includes('↓')) td.className = 'at-negative';
        if (/https?:\/\/\S+/.test(str)) {
            td.innerHTML = str.replace(
                /(https?:\/\/[^\s<]+)/g,
                '<a href="$1" target="_blank" rel="noopener" class="at-link">$1</a>'
            );
        } else {
            td.textContent = str;
        }
        tr.appendChild(td);
    }

    // ── Render a single panel section ────────────────────────────
    _renderSection(container, section) {
        const colors = [
            'rgba(0,200,255,0.8)', 'rgba(0,255,136,0.8)', 'rgba(255,170,0,0.8)',
            'rgba(255,51,85,0.8)', 'rgba(160,120,255,0.8)', 'rgba(255,200,0,0.8)',
            'rgba(0,180,220,0.8)', 'rgba(80,255,200,0.8)'
        ];
        const bgColors = colors.map(c => c.replace('0.8)', '0.15)'));

        // ── Hero stat (large featured number) ──
        if (section.hero) {
            const h = section.hero;
            const heroEl = document.createElement('div');
            heroEl.className = 'analysis-hero';
            const deltaCls = h.delta_status === 'good' ? 'nominal' : h.delta_status === 'bad' ? 'alert' : '';
            heroEl.innerHTML = `
                <div class="analysis-hero-val">${h.value}</div>
                <div class="analysis-hero-lbl">${h.label}</div>
                ${h.delta ? `<div class="analysis-hero-delta ${deltaCls}">${h.delta}</div>` : ''}
            `;
            container.appendChild(heroEl);
        }

        // ── Status grid (colored dots for service health) ──
        if (section.status_grid && section.status_grid.length) {
            const grid = document.createElement('div');
            grid.className = 'analysis-status-grid';
            for (const item of section.status_grid) {
                const cell = document.createElement('div');
                cell.className = 'status-grid-item';
                const dotCls = item.status === 'good' ? 'sg-good' : item.status === 'warn' ? 'sg-warn' : item.status === 'bad' ? 'sg-bad' : 'sg-unknown';
                cell.innerHTML = `
                    <span class="sg-dot ${dotCls}"></span>
                    <span class="sg-label">${item.label}</span>
                    <span class="sg-value ${dotCls}">${item.value}</span>
                `;
                grid.appendChild(cell);
            }
            container.appendChild(grid);
        }

        // ── Stat cards ──
        if (section.stats && section.stats.length) {
            const grid = document.createElement('div');
            grid.className = 'analysis-stats';
            for (const s of section.stats) {
                const card = document.createElement('div');
                card.className = 'analysis-stat';
                const cls = s.status === 'good' ? 'nominal' : s.status === 'warn' ? 'caution' : s.status === 'bad' ? 'alert' : '';
                card.innerHTML = `<div class="analysis-stat-val ${cls}">${s.value}</div><div class="analysis-stat-lbl">${s.label}</div>`;
                grid.appendChild(card);
            }
            container.appendChild(grid);
        }

        // ── Chart (bar, hbar, line, area, doughnut, pie, radar, polarArea, scatter, bubble, stacked) ──
        if (section.chart) {
            const c = section.chart;
            const wrap = document.createElement('div');
            wrap.className = 'analysis-chart';
            container.appendChild(wrap);

            // ── Candlestick — custom canvas renderer (no Chart.js plugin needed) ──
            if (c.type === 'candlestick') {
                wrap.style.height = '260px';
                const canvas = document.createElement('canvas');
                wrap.appendChild(canvas);
                requestAnimationFrame(() => {
                    const data = c.data || [];
                    if (!data.length) return;
                    const dpr = window.devicePixelRatio || 1;
                    const rect = wrap.getBoundingClientRect();
                    const W = rect.width || 380, H = rect.height || 260;
                    canvas.width = W * dpr; canvas.height = H * dpr;
                    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
                    const ctx = canvas.getContext('2d');
                    ctx.scale(dpr, dpr);
                    const PAD = { top: 16, right: 16, bottom: 28, left: 54 };
                    const cW = W - PAD.left - PAD.right, cH = H - PAD.top - PAD.bottom;
                    const allV = data.flatMap(d => [d.o, d.h, d.l, d.c]);
                    const mn = Math.min(...allV), mx = Math.max(...allV);
                    const rng = (mx - mn) || 1;
                    const yMin = mn - rng * 0.08, yMax = mx + rng * 0.08;
                    const toY = v => PAD.top + cH - ((v - yMin) / (yMax - yMin)) * cH;
                    const colW = cW / data.length, bodyW = Math.max(colW * 0.55, 2);
                    // Y gridlines
                    ctx.font = `9px 'Courier New'`; ctx.textAlign = 'right';
                    for (let i = 0; i <= 5; i++) {
                        const v = yMin + (i / 5) * (yMax - yMin), y = toY(v);
                        ctx.strokeStyle = 'rgba(60,220,255,0.1)'; ctx.lineWidth = 1;
                        ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(W - PAD.right, y); ctx.stroke();
                        ctx.fillStyle = '#a0c4d8'; ctx.fillText(v.toFixed(2), PAD.left - 4, y + 3);
                    }
                    // Candles + x-labels
                    const step = Math.max(1, Math.floor(data.length / 8));
                    ctx.textAlign = 'center';
                    data.forEach((d, i) => {
                        const x = PAD.left + i * colW + colW / 2;
                        const col = d.c >= d.o ? 'rgba(0,255,136,0.9)' : 'rgba(255,51,85,0.9)';
                        ctx.strokeStyle = col; ctx.lineWidth = 1;
                        ctx.beginPath(); ctx.moveTo(x, toY(d.h)); ctx.lineTo(x, toY(d.l)); ctx.stroke();
                        const bTop = toY(Math.max(d.o, d.c)), bBot = toY(Math.min(d.o, d.c));
                        ctx.fillStyle = col;
                        ctx.fillRect(x - bodyW / 2, bTop, bodyW, Math.max(bBot - bTop, 1));
                        if (d.date && i % step === 0) {
                            ctx.fillStyle = '#a0c4d8'; ctx.font = `8px 'Courier New'`;
                            ctx.fillText(d.date, x, H - PAD.bottom + 13);
                        }
                    });
                    // Series label
                    if (c.label) {
                        ctx.fillStyle = 'rgba(160,196,216,0.7)'; ctx.font = `10px 'Courier New'`;
                        ctx.textAlign = 'left';
                        ctx.fillText(c.label, PAD.left + 4, PAD.top + 12);
                    }
                });

            } else {
                // ── Chart.js renderers (bar / line / doughnut / radar / waterfall / scatter / …) ──
                const canvas = document.createElement('canvas');
                wrap.appendChild(canvas);

                const isHbar     = c.type === 'hbar';
                const isArea     = c.type === 'area';
                const isStacked  = c.type === 'stacked' || c.type === 'stacked_bar';
                const isWaterfall= c.type === 'waterfall';
                const isRadar    = c.type === 'radar';
                const isPolar    = c.type === 'polarArea';
                const isScatter  = c.type === 'scatter';
                const isBubble   = c.type === 'bubble';
                if (isRadar || isPolar) wrap.style.height = '290px';
                let chartType = c.type || 'bar';
                if (isHbar || isStacked || isWaterfall) chartType = 'bar';
                else if (isArea) chartType = 'line';

                const _tickColor = '#a0c4d8';
                const _gridColor = 'rgba(60,220,255,0.07)';
                const _tickFont  = { size: 11, family: "'Courier New'" };

                let datasets;
                if (isWaterfall) {
                    // Stacked-bar trick: transparent spacer dataset + coloured delta dataset
                    const wfData = c.data || [];
                    const spacer = [], bars = [], barColors = [];
                    let running = 0;
                    for (const d of wfData) {
                        const v = Number(d.value) || 0;
                        if (d.type === 'total') {
                            spacer.push(0); bars.push(v);
                            barColors.push('rgba(0,200,255,0.85)'); running = v;
                        } else if (d.type === 'neg' || v < 0) {
                            spacer.push(running + v); bars.push(Math.abs(v));
                            barColors.push('rgba(255,51,85,0.8)'); running += v;
                        } else {
                            spacer.push(running); bars.push(v);
                            barColors.push('rgba(0,255,136,0.8)'); running += v;
                        }
                    }
                    if (!c.labels) c.labels = wfData.map(d => d.label || '');
                    datasets = [
                        { label: '_spacer', data: spacer, backgroundColor: 'transparent', borderWidth: 0, stack: 'wf' },
                        { label: c.label || 'Change', data: bars, backgroundColor: barColors, borderWidth: 0, stack: 'wf' },
                    ];
                } else if (c.datasets) {
                    datasets = c.datasets.map((ds, i) => {
                        const base = {
                            label: ds.label || '',
                            data: ds.data || [],
                            borderColor: colors[i % colors.length],
                            borderWidth: (chartType === 'line' || isRadar) ? 2 : (isScatter || isBubble) ? 1 : 0,
                            tension: 0.4,
                            yAxisID: ds.yAxisID || undefined,
                        };
                        if (isRadar || isPolar) {
                            base.backgroundColor = bgColors[i % bgColors.length];
                            base.pointBackgroundColor = colors[i % colors.length];
                            base.pointRadius = 4; base.fill = true;
                        } else if (chartType === 'line' || isArea) {
                            base.backgroundColor = bgColors[i % bgColors.length];
                            base.pointRadius = 3; base.fill = true;
                        } else if (isScatter || isBubble) {
                            base.backgroundColor = colors[i % colors.length];
                            base.pointRadius = isBubble ? undefined : 6;
                        } else {
                            base.backgroundColor = colors[i % colors.length];
                            base.borderWidth = 0;
                        }
                        return base;
                    });
                } else {
                    const barColors = isHbar
                        ? (c.values || []).map(v => v >= 0 ? 'rgba(0,255,136,0.75)' : 'rgba(255,51,85,0.75)')
                        : (c.values || []).map((_, i) => colors[i % colors.length]);
                    datasets = [{
                        label: c.label || '',
                        data: c.values || [],
                        backgroundColor: (isRadar || isPolar) ? bgColors[0] : barColors,
                        borderColor: (isRadar || isPolar) ? colors[0] : undefined,
                        borderWidth: (isRadar || isPolar) ? 2 : 0,
                        pointBackgroundColor: (isRadar || isPolar) ? colors[0] : undefined,
                        pointRadius: (isRadar || isPolar) ? 4 : undefined,
                        fill: (isRadar || isPolar),
                    }];
                }

                const opts = {
                    responsive: true, maintainAspectRatio: false,
                    indexAxis: isHbar ? 'y' : 'x',
                    animation: { duration: 600 },
                    plugins: {
                        legend: {
                            display: (!isWaterfall && !!(c.datasets && c.datasets.length > 1)) || isScatter,
                            labels: {
                                color: _tickColor, font: { size: 11, family: "'Courier New'" }, padding: 12,
                                filter: isWaterfall ? (item) => item.text !== '_spacer' : undefined,
                            },
                        },
                        tooltip: isWaterfall ? {
                            callbacks: {
                                label: (ctx) => {
                                    if (ctx.datasetIndex === 0) return null; // hide spacer rows
                                    const orig = (c.data || [])[ctx.dataIndex];
                                    if (!orig) return null;
                                    const sign = orig.type === 'total' ? '' :
                                        (orig.type === 'neg' || Number(orig.value) < 0) ? '−' : '+';
                                    return ` ${sign}${orig.display || Math.abs(orig.value)}`;
                                },
                            },
                        } : undefined,
                    },
                };

                if (chartType === 'doughnut' || chartType === 'pie' || chartType === 'polarArea') {
                    opts.scales = {};
                } else if (chartType === 'radar') {
                    opts.scales = {
                        r: {
                            angleLines: { color: 'rgba(60,220,255,0.15)' },
                            grid: { color: _gridColor },
                            pointLabels: { color: _tickColor, font: { size: 12, family: "'Courier New'" }, padding: 6 },
                            ticks: { color: _tickColor, backdropColor: 'rgba(8,14,28,0.7)', font: { size: 10 }, maxTicksLimit: 5 },
                            suggestedMin: 0,
                        },
                    };
                } else {
                    opts.scales = {
                        x: {
                            ticks: { color: _tickColor, font: _tickFont, maxRotation: 35 },
                            grid: { color: _gridColor },
                            stacked: (isStacked || isWaterfall) || undefined,
                            title: c.xLabel ? { display: true, text: c.xLabel, color: _tickColor, font: _tickFont } : undefined,
                        },
                        y: {
                            ticks: { color: _tickColor, font: _tickFont },
                            grid: { color: _gridColor },
                            stacked: (isStacked || isWaterfall) || undefined,
                            title: c.yLabel ? { display: true, text: c.yLabel, color: _tickColor, font: _tickFont } : undefined,
                        },
                    };
                    if (c.datasets && c.datasets.some(ds => ds.yAxisID === 'y1')) {
                        opts.scales.y1 = {
                            position: 'right', grid: { drawOnChartArea: false },
                            ticks: { color: _tickColor, font: _tickFont },
                        };
                    }
                }

                const chart = new Chart(canvas, { type: chartType, data: { labels: c.labels || [], datasets }, options: opts });
                this._analysisCharts.push(chart);
                this._analysisChart = chart;
            }
        }

        // ── Image display (for ComfyUI output) ──
        if (section.image_url) {
            const imgWrap = document.createElement('div');
            imgWrap.className = 'analysis-image';
            imgWrap.innerHTML = `<img src="${section.image_url}" alt="Generated image" loading="lazy" />`;
            container.appendChild(imgWrap);
        }

        // ── Table ──
        if (section.table) {
            const t = section.table;
            const colCount = (t.headers || []).length;

            // If table has many columns, split into stacked tables.
            // Keep column 0 (label/name) as the key in both halves.
            if (colCount > 5 && t.headers && t.rows) {
                const mid = Math.ceil(colCount / 2);
                const slices = [
                    { headers: t.headers.slice(0, mid), colStart: 0, colEnd: mid },
                    { headers: [t.headers[0], ...t.headers.slice(mid)], colStart: mid, colEnd: colCount, includeKey: true },
                ];
                for (const slice of slices) {
                    const wrap = document.createElement('div');
                    wrap.className = 'analysis-table-wrap';
                    const tbl = document.createElement('table');
                    tbl.className = 'analysis-table';
                    const thead = document.createElement('thead');
                    const htr = document.createElement('tr');
                    for (const h of slice.headers) {
                        const th = document.createElement('th');
                        th.textContent = h;
                        htr.appendChild(th);
                    }
                    thead.appendChild(htr);
                    tbl.appendChild(thead);
                    const tbody = document.createElement('tbody');
                    for (const row of t.rows) {
                        const tr = document.createElement('tr');
                        if (slice.includeKey) {
                            // Include key column (col 0) + slice columns
                            this._renderTableCell(tr, row[0]);
                            for (let c = slice.colStart; c < slice.colEnd; c++) {
                                this._renderTableCell(tr, row[c]);
                            }
                        } else {
                            for (let c = slice.colStart; c < slice.colEnd; c++) {
                                this._renderTableCell(tr, row[c]);
                            }
                        }
                        tbody.appendChild(tr);
                    }
                    tbl.appendChild(tbody);
                    wrap.appendChild(tbl);
                    container.appendChild(wrap);
                }
            } else {
                // Normal table — fits in container
                const tableWrap = document.createElement('div');
                tableWrap.className = 'analysis-table-wrap';
                const table = document.createElement('table');
                table.className = 'analysis-table';
                if (t.headers) {
                    const thead = document.createElement('thead');
                    const tr = document.createElement('tr');
                    for (const h of t.headers) {
                        const th = document.createElement('th');
                        th.textContent = h;
                        tr.appendChild(th);
                    }
                    thead.appendChild(tr);
                    table.appendChild(thead);
                }
                if (t.rows) {
                    const tbody = document.createElement('tbody');
                    for (const row of t.rows) {
                        const tr = document.createElement('tr');
                        for (const cell of row) {
                            this._renderTableCell(tr, cell);
                        }
                        tbody.appendChild(tr);
                    }
                    table.appendChild(tbody);
                }
                tableWrap.appendChild(table);
                container.appendChild(tableWrap);
            }
        }

        // ── Insights list (strategic observations) ──
        if (section.insights && section.insights.length) {
            const wrap = document.createElement('div');
            wrap.className = 'analysis-insights';
            wrap.innerHTML = '<div class="analysis-insights-title">KEY INSIGHTS</div>';
            for (const ins of section.insights) {
                const type = ins.type || 'info'; // risk | opportunity | warning | info
                const icons = { risk: '⚠', opportunity: '◆', warning: '▲', info: '●' };
                const item = document.createElement('div');
                item.className = `insight-item insight-${type}`;
                item.innerHTML = `<span class="insight-icon">${icons[type] || '●'}</span><span class="insight-text">${ins.text}</span>`;
                wrap.appendChild(item);
            }
            container.appendChild(wrap);
        }

        // ── Recommendations (actionable next steps) ──
        if (section.recommendations && section.recommendations.length) {
            const wrap = document.createElement('div');
            wrap.className = 'analysis-recommendations';
            wrap.innerHTML = '<div class="analysis-recommendations-title">RECOMMENDATIONS</div>';
            for (const rec of section.recommendations) {
                const priority = rec.priority || 'medium'; // high | medium | low
                const item = document.createElement('div');
                item.className = 'recommendation-item';
                item.innerHTML = `<span class="rec-priority rec-${priority}">${priority}</span><span class="rec-text">${rec.text}</span>`;
                wrap.appendChild(item);
            }
            container.appendChild(wrap);
        }

        // ── Comparison matrix ──
        if (section.comparison_matrix) {
            const cm = section.comparison_matrix;
            const wrap = document.createElement('div');
            wrap.className = 'analysis-comparison';
            const cols = cm.columns || []; // ['', 'Apple', 'Tesla']
            const colCount = cols.length;
            const gridTpl = `grid-template-columns: 120px repeat(${colCount - 1}, 1fr)`;
            // Header
            const header = document.createElement('div');
            header.className = 'comparison-header';
            header.style.cssText = gridTpl;
            for (const col of cols) {
                const cell = document.createElement('div');
                cell.className = 'comparison-cell';
                cell.textContent = col;
                header.appendChild(cell);
            }
            wrap.appendChild(header);
            // Rows
            for (const row of (cm.rows || [])) {
                const rowEl = document.createElement('div');
                rowEl.className = 'comparison-row';
                rowEl.style.cssText = gridTpl;
                row.forEach((val, i) => {
                    const cell = document.createElement('div');
                    cell.className = 'comparison-cell' + (i === 0 ? ' comp-label' : '');
                    // Highlight best/worst if flagged
                    if (row._best === i) cell.classList.add('comp-best');
                    if (row._worst === i) cell.classList.add('comp-worst');
                    cell.textContent = String(val);
                    rowEl.appendChild(cell);
                });
                wrap.appendChild(rowEl);
            }
            container.appendChild(wrap);
        }

        // ── Scorecard (rated attributes with gauge bars) ──
        if (section.scorecard && section.scorecard.length) {
            const wrap = document.createElement('div');
            wrap.className = 'analysis-scorecard';
            wrap.innerHTML = '<div class="analysis-scorecard-title">SCORECARD</div>';
            for (const sc of section.scorecard) {
                const pct = Math.min(100, Math.max(0, sc.score || 0));
                const cls = pct >= 70 ? 'sc-good' : pct >= 40 ? 'sc-warn' : pct < 40 ? 'sc-bad' : 'sc-neutral';
                const item = document.createElement('div');
                item.className = 'scorecard-item';
                item.innerHTML = `
                    <span class="scorecard-label">${sc.label}</span>
                    <div class="scorecard-bar-track">
                        <div class="scorecard-bar-fill ${cls}" style="width:${pct}%"></div>
                    </div>
                    <span class="scorecard-value">${sc.value || pct + '/100'}</span>
                `;
                wrap.appendChild(item);
            }
            container.appendChild(wrap);
        }

        // ── Trend indicators (compact directional) ──
        if (section.trend_indicators && section.trend_indicators.length) {
            const wrap = document.createElement('div');
            wrap.className = 'analysis-trends';
            for (const t of section.trend_indicators) {
                const dir = t.direction || 'flat'; // up | down | flat
                const arrows = { up: '↑', down: '↓', flat: '→' };
                const item = document.createElement('div');
                item.className = 'trend-item';
                item.innerHTML = `
                    <span class="trend-arrow trend-${dir}">${arrows[dir] || '→'}</span>
                    <div>
                        <div class="trend-value">${t.value || ''}</div>
                        <div class="trend-label">${t.label || ''}</div>
                        ${t.context ? `<div class="trend-context">${t.context}</div>` : ''}
                    </div>
                `;
                wrap.appendChild(item);
            }
            container.appendChild(wrap);
        }

        // ── Pros / Cons list ──
        if (section.pros_cons) {
            const pc = section.pros_cons;
            const wrap = document.createElement('div');
            wrap.className = 'analysis-pros-cons';
            if (pc.pros && pc.pros.length) {
                const pDiv = document.createElement('div');
                pDiv.className = 'pc-column pc-pros';
                pDiv.innerHTML = '<div class="pc-title">▲ PROS</div>';
                for (const p of pc.pros) {
                    const item = document.createElement('div');
                    item.className = 'pc-item'; item.textContent = p;
                    pDiv.appendChild(item);
                }
                wrap.appendChild(pDiv);
            }
            if (pc.cons && pc.cons.length) {
                const cDiv = document.createElement('div');
                cDiv.className = 'pc-column pc-cons';
                cDiv.innerHTML = '<div class="pc-title">▼ CONS</div>';
                for (const c of pc.cons) {
                    const item = document.createElement('div');
                    item.className = 'pc-item'; item.textContent = c;
                    cDiv.appendChild(item);
                }
                wrap.appendChild(cDiv);
            }
            container.appendChild(wrap);
        }

        // ── SWOT matrix ──
        if (section.swot) {
            const sw = section.swot;
            const wrap = document.createElement('div');
            wrap.className = 'analysis-swot';
            wrap.innerHTML = '<div class="analysis-swot-title">SWOT ANALYSIS</div>';
            const grid = document.createElement('div');
            grid.className = 'swot-grid';
            for (const quad of ['strengths', 'weaknesses', 'opportunities', 'threats']) {
                const cell = document.createElement('div');
                cell.className = `swot-cell swot-${quad}`;
                const labels = { strengths: 'STRENGTHS', weaknesses: 'WEAKNESSES', opportunities: 'OPPORTUNITIES', threats: 'THREATS' };
                const icons = { strengths: '◆', weaknesses: '▼', opportunities: '▲', threats: '⚠' };
                cell.innerHTML = `<div class="swot-label">${icons[quad]} ${labels[quad]}</div>`;
                for (const item of (sw[quad] || [])) {
                    const li = document.createElement('div');
                    li.className = 'swot-item'; li.textContent = item;
                    cell.appendChild(li);
                }
                grid.appendChild(cell);
            }
            wrap.appendChild(grid);
            container.appendChild(wrap);
        }

        // ── Risk matrix (severity × likelihood) ──
        if (section.risk_matrix && section.risk_matrix.length) {
            const wrap = document.createElement('div');
            wrap.className = 'analysis-risk-matrix';
            wrap.innerHTML = '<div class="analysis-risk-title">RISK ASSESSMENT</div>';
            for (const risk of section.risk_matrix) {
                const sev = risk.severity || 'medium'; // low | medium | high | critical
                const item = document.createElement('div');
                item.className = `risk-item risk-${sev}`;
                item.innerHTML = `
                    <span class="risk-severity">${sev.toUpperCase()}</span>
                    <span class="risk-desc">${risk.risk || ''}</span>
                    ${risk.mitigation ? `<span class="risk-mitigation">↳ ${risk.mitigation}</span>` : ''}
                `;
                wrap.appendChild(item);
            }
            container.appendChild(wrap);
        }

        // ── Key metrics grid (compact numbers grid) ──
        if (section.key_metrics && section.key_metrics.length) {
            const wrap = document.createElement('div');
            wrap.className = 'analysis-key-metrics';
            wrap.innerHTML = '<div class="analysis-km-title">KEY METRICS</div>';
            const grid = document.createElement('div');
            grid.className = 'km-grid';
            for (const m of section.key_metrics) {
                const cell = document.createElement('div');
                cell.className = 'km-cell';
                const cls = m.status === 'good' ? 'nominal' : m.status === 'warn' ? 'caution' : m.status === 'bad' ? 'alert' : '';
                cell.innerHTML = `
                    <div class="km-val ${cls}">${m.value}</div>
                    <div class="km-label">${m.label}</div>
                    ${m.context ? `<div class="km-ctx">${m.context}</div>` : ''}
                `;
                grid.appendChild(cell);
            }
            wrap.appendChild(grid);
            container.appendChild(wrap);
        }

        // ── Timeline (chronological events) ──
        if (section.timeline && section.timeline.length) {
            const wrap = document.createElement('div');
            wrap.className = 'analysis-timeline';
            wrap.innerHTML = '<div class="analysis-tl-title">TIMELINE</div>';
            for (const ev of section.timeline) {
                const item = document.createElement('div');
                item.className = 'tl-item';
                const statusCls = ev.status === 'done' ? 'tl-done' : ev.status === 'active' ? 'tl-active' : 'tl-pending';
                item.innerHTML = `
                    <div class="tl-marker ${statusCls}"></div>
                    <div class="tl-body">
                        <div class="tl-date">${ev.date || ''}</div>
                        <div class="tl-event">${ev.event || ''}</div>
                        ${ev.detail ? `<div class="tl-detail">${ev.detail}</div>` : ''}
                    </div>
                `;
                wrap.appendChild(item);
            }
            container.appendChild(wrap);
        }

        // ── Heatmap (color-coded grid) ──
        if (section.heatmap) {
            const hm = section.heatmap;
            const wrap = document.createElement('div');
            wrap.className = 'analysis-heatmap';
            wrap.innerHTML = `<div class="analysis-heatmap-title">${hm.title || 'HEATMAP'}</div>`;
            const cols = hm.columns || [];
            const rows = hm.rows || [];
            const grid = document.createElement('div');
            grid.className = 'heatmap-grid';
            grid.style.gridTemplateColumns = `120px repeat(${cols.length}, 1fr)`;
            // Header row
            grid.innerHTML = '<div class="heatmap-header"></div>' +
                cols.map(c => `<div class="heatmap-header">${c}</div>`).join('');
            // Data rows
            for (const row of rows) {
                grid.innerHTML += `<div class="heatmap-row-label">${row.label || ''}</div>`;
                for (const val of (row.values || [])) {
                    // Normalize intensity 0-5 from value (assume 0-100 scale or use raw)
                    const num = typeof val === 'object' ? (val.score || 0) : (parseFloat(val) || 0);
                    const displayVal = typeof val === 'object' ? (val.display || num) : val;
                    const intensity = Math.min(5, Math.max(0, Math.round(num / 20)));
                    grid.innerHTML += `<div class="heatmap-cell" data-intensity="${intensity}">${displayVal}</div>`;
                }
            }
            wrap.appendChild(grid);
            container.appendChild(wrap);
        }

        // ── Gauge / Meter ──
        if (section.gauges && section.gauges.length) {
            const wrap = document.createElement('div');
            wrap.className = 'analysis-gauges';
            for (const g of section.gauges) {
                const pct = Math.min(100, Math.max(0, g.value || 0));
                const cls = pct >= 70 ? 'g-good' : pct >= 40 ? 'g-warn' : 'g-bad';
                const item = document.createElement('div');
                item.className = 'gauge-item';
                item.innerHTML = `
                    <div class="gauge-ring">
                        <div class="gauge-fill ${cls}" style="--pct:${pct}%"></div>
                    </div>
                    <div class="gauge-val">${g.display || pct + '%'}</div>
                    <div class="gauge-label">${g.label || ''}</div>
                    ${g.context ? `<div class="gauge-sub">${g.context}</div>` : ''}
                `;
                wrap.appendChild(item);
            }
            container.appendChild(wrap);
        }

        // ── Funnel ──
        if (section.funnel && section.funnel.length) {
            const wrap = document.createElement('div');
            wrap.className = 'analysis-funnel';
            wrap.innerHTML = '<div class="analysis-funnel-title">FUNNEL</div>';
            const maxVal = Math.max(...section.funnel.map(f => f.value || 0), 1);
            const funnelColors = ['rgba(0,240,255,0.8)', 'rgba(0,200,255,0.7)', 'rgba(0,255,136,0.65)',
                'rgba(255,170,0,0.65)', 'rgba(255,51,85,0.6)', 'rgba(170,0,255,0.6)'];
            section.funnel.forEach((stage, i) => {
                const widthPct = Math.max(15, ((stage.value || 0) / maxVal) * 100);
                const row = document.createElement('div');
                row.className = 'funnel-stage';
                row.innerHTML = `
                    <div class="funnel-label">${stage.label || ''}</div>
                    <div class="funnel-bar" style="width:${widthPct}%;background:${funnelColors[i % funnelColors.length]}">${stage.display || stage.value || ''}</div>
                    ${stage.pct ? `<div class="funnel-pct">${stage.pct}</div>` : ''}
                `;
                wrap.appendChild(row);
            });
            container.appendChild(wrap);
        }

        // ── Quadrant / Positioning Map ──
        if (section.quadrant) {
            const q = section.quadrant;
            const wrap = document.createElement('div');
            wrap.className = 'analysis-quadrant';
            wrap.innerHTML = `<div class="analysis-quadrant-title">${q.title || 'POSITIONING MAP'}</div>`;
            const canvas = document.createElement('div');
            canvas.className = 'quadrant-canvas';
            // Crosshairs
            canvas.innerHTML = `
                <div class="quadrant-crosshair-h"></div>
                <div class="quadrant-crosshair-v"></div>
                <div class="quadrant-axis-x">${q.x_axis || ''}</div>
                <div class="quadrant-axis-y">${q.y_axis || ''}</div>
                ${q.quadrant_labels ? `
                    <div class="quadrant-label ql-tl">${q.quadrant_labels[0] || ''}</div>
                    <div class="quadrant-label ql-tr">${q.quadrant_labels[1] || ''}</div>
                    <div class="quadrant-label ql-bl">${q.quadrant_labels[2] || ''}</div>
                    <div class="quadrant-label ql-br">${q.quadrant_labels[3] || ''}</div>
                ` : ''}
            `;
            // Plot points
            const dotColors = ['#00f0ff', '#00ff88', '#ffaa00', '#ff00aa', '#ff2255', '#aa55ff'];
            for (let i = 0; i < (q.points || []).length; i++) {
                const pt = q.points[i];
                const x = Math.min(95, Math.max(5, pt.x || 50));
                const y = Math.min(95, Math.max(5, 100 - (pt.y || 50))); // invert Y
                const dot = document.createElement('div');
                dot.className = 'quadrant-dot';
                dot.style.cssText = `left:${x}%;top:${y}%;background:${dotColors[i % dotColors.length]};border-color:${dotColors[i % dotColors.length]}`;
                if (pt.size) dot.style.width = dot.style.height = Math.max(8, Math.min(24, pt.size)) + 'px';
                const lbl = document.createElement('div');
                lbl.className = 'quadrant-dot-label';
                lbl.textContent = pt.label || '';
                dot.appendChild(lbl);
                canvas.appendChild(dot);
            }
            wrap.appendChild(canvas);
            container.appendChild(wrap);
        }

        // ── Calendar Heatmap ──────────────────────────────────────
        if (section.calendar_heatmap) {
            const cal = section.calendar_heatmap;
            const data = cal.data || [];
            const calWrap = document.createElement('div');
            calWrap.className = 'cal-heatmap';
            if (cal.title) {
                const t = document.createElement('div');
                t.className = 'cal-heatmap-title';
                t.textContent = cal.title;
                calWrap.appendChild(t);
            }
            if (data.length) {
                const vals = data.map(d => Number(d.value) || 0);
                const minV = Math.min(...vals), maxV = Math.max(...vals);
                const rng = (maxV - minV) || 1;
                const dateMap = {};
                for (const d of data) dateMap[d.date] = d;
                const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));
                const start = new Date(sorted[0].date);
                const end   = new Date(sorted[sorted.length - 1].date);
                // Rewind to nearest Monday
                start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
                const grid = document.createElement('div');
                grid.className = 'cal-heatmap-grid';
                // Day-of-week labels column
                const lblCol = document.createElement('div');
                lblCol.className = 'cal-day-labels';
                for (const d of ['M','T','W','T','F','S','S']) {
                    const l = document.createElement('div');
                    l.className = 'cal-day-label'; l.textContent = d;
                    lblCol.appendChild(l);
                }
                grid.appendChild(lblCol);
                // Week columns
                const cur = new Date(start);
                while (cur <= end) {
                    const col = document.createElement('div');
                    col.className = 'cal-week-col';
                    for (let dow = 0; dow < 7; dow++) {
                        const cell = document.createElement('div');
                        cell.className = 'cal-cell';
                        const ds = cur.toISOString().split('T')[0];
                        const entry = dateMap[ds];
                        if (entry) {
                            const intensity = (Number(entry.value) - minV) / rng;
                            cell.style.background = `rgba(0,200,255,${(0.08 + intensity * 0.82).toFixed(2)})`;
                            cell.title = `${ds}: ${entry.label || entry.value}`;
                            cell.classList.add('cal-cell-active');
                        } else {
                            cell.style.background = 'rgba(0,200,255,0.04)';
                        }
                        col.appendChild(cell);
                        cur.setDate(cur.getDate() + 1);
                    }
                    grid.appendChild(col);
                }
                calWrap.appendChild(grid);
                // Legend
                const leg = document.createElement('div');
                leg.className = 'cal-legend';
                leg.innerHTML = `<span class="cal-legend-label">Less</span>
                    <div class="cal-legend-scale"></div>
                    <span class="cal-legend-label">More</span>`;
                calWrap.appendChild(leg);
            }
            container.appendChild(calWrap);
        }

        // ── Summary text ──
        if (section.summary) {
            const div = document.createElement('div');
            div.className = 'analysis-summary';
            div.textContent = section.summary;
            container.appendChild(div);
        }
    }

    // ── Follow-up listening (5s active after response, no wake word needed) ──
    _startFollowUpListen() {
        this._followUpActive = true;

        // Small delay before starting mic — avoids picking up TTS audio tail / echo
        setTimeout(() => this._requestStart('active'), 400);

        // Kill the default silence timer — use our own 5s window
        clearTimeout(this._silenceTimer);
        clearTimeout(this._followUpTimer);
        this._followUpTimer = setTimeout(() => {
            // No follow-up within 5s — return to passive standby
            if (!this._followUpActive) return; // already handled
            this._followUpActive = false;
            this._mode = 'off';
            clearTimeout(this._silenceTimer);
            try { this.recognition.stop(); } catch {}
            this._stopLevelPump();
            const bl = document.getElementById('btn-listen');
            if (bl) bl.classList.remove('active');
            this.orb.setState('idle');
            setTimeout(() => this._requestStart('passive'), 300);
        }, 5000);
    }

    // ── Stop speaking (interrupt) ──────────────────────────────────
    stopSpeaking() {
        if (!this.speaking) return;
        if (this._currentAudio) {
            try { this._currentAudio.pause(); this._currentAudio.src = ''; } catch (_) {}
            this._currentAudio = null;
        }
        // Cancel Web Speech API fallback
        if (this.synth && this.synth.speaking) {
            this.synth.cancel();
        }
        // cleanup will be called by onended/onerror, but force it in case
        if (this._speakCleanup) this._speakCleanup();
    }

    // ── Cancel in-flight LLM processing ────────────────────────
    cancelProcessing() {
        if (this._activeAbort) {
            this._activeAbort.abort();
            this._activeAbort = null;
        }
        if (this.speaking) this.stopSpeaking();
        this._processingQuery = false;
        this.orb.setState('idle');
        this.orb.setAudioLevel(0);
        // Remove thinking indicator from chat
        const think = document.getElementById('chat-thinking');
        if (think) think.remove();
        _camScanStop();
        console.log('[ARBITER] Processing cancelled by user');
    }

    // Strip markdown/formatting for TTS — the voice shouldn't read asterisks, hashes, etc.
    _cleanForTTS(text) {
        return text
            // Strip any residual JSON blobs
            .replace(/\[?\{["\s]*action["\s]*:[\s\S]*$/i, '')
            .replace(/\[?\{"action"[\s\S]*?\}\]?/g, '')
            // Markdown formatting
            .replace(/\*\*(.+?)\*\*/g, '$1')       // **bold**
            .replace(/\*(.+?)\*/g, '$1')            // *italic*
            .replace(/__(.+?)__/g, '$1')            // __bold__
            .replace(/_(.+?)_/g, '$1')              // _italic_
            .replace(/~~(.+?)~~/g, '$1')            // ~~strikethrough~~
            .replace(/`(.+?)`/g, '$1')              // `code`
            .replace(/^#{1,6}\s+/gm, '')            // ### headings
            .replace(/^\s*[-*•]\s+/gm, '')          // bullet points
            .replace(/^\s*\d+\.\s+/gm, '')          // numbered lists
            .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // [links](url)
            .replace(/[<>]/g, '')                    // stray HTML angle brackets
            // Punctuation that TTS reads aloud
            .replace(/:\s*/g, ', ')                 // colons → comma pause
            .replace(/;\s*/g, ', ')                 // semicolons → comma pause
            .replace(/\//g, ' ')                    // slashes → space
            .replace(/[{}[\]"]/g, '')               // stray JSON chars
            .replace(/\s{2,}/g, ' ')                // collapse multiple spaces
            .replace(/\n{2,}/g, '. ')               // double newlines → pause
            .replace(/\n/g, ' ')                    // single newlines → space
            .trim();
    }

    // ── Speak response using edge-tts (neural voice) ──────────────
    // onDone: optional callback after speech finishes (overrides default passive restart)
    async _speak(text, onDone) {
        // ── Mute guard: skip audio but run onDone callback ──
        if (_arbiterMuted) {
            this.orb.setState('idle');
            this._processingQuery = false;
            if (onDone) { onDone(); }
            else { setTimeout(() => this._requestStart('passive'), 500); }
            return;
        }

        // Cancel any current speech first — prevents overlapping audio
        if (this.speaking) {
            this.stopSpeaking();
            // Brief pause so previous audio fully stops
            await new Promise(r => setTimeout(r, 80));
        }

        text = this._cleanForTTS(text);             // strip formatting before TTS
        this.orb.setState('speaking');
        this.speaking = true;
        this._currentAudio = null;

        // Show stop button
        const stopBtn = document.getElementById('btn-stop');
        if (stopBtn) stopBtn.style.display = '';

        // ── Stop mic during speech to prevent self-triggering ──
        // The TTS output contains "Arbiter" which the mic picks up and
        // triggers the wake word. Kill recognition while speaking.
        this._stopLevelPump();
        this._mode = 'off';
        this._pendingStart = null;
        try { this.recognition.stop(); } catch {}
        this._running = false;

        let speakPump = null;
        let cleanedUp = false;
        const cleanup = () => {
            if (cleanedUp) return;
            cleanedUp = true;
            if (speakPump) cancelAnimationFrame(speakPump);
            speakPump = null;
            this.speaking = false;
            this._currentAudio = null;
            this._speakCleanup = null;
            this._processingQuery = false;  // allow next query
            this.orb.setAudioLevel(0);
            this.orb.setState('idle');
            // Hide stop button
            const sb = document.getElementById('btn-stop');
            if (sb) sb.style.display = 'none';
            if (onDone) {
                onDone();
            } else {
                // After answering, listen for 5s follow-up without wake word
                this._startFollowUpListen();
            }
        };
        this._speakCleanup = cleanup;

        try {
            // Fetch neural TTS audio — stream it for instant playback
            const resp = await fetch('/api/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text }),
            });
            if (!resp.ok) throw new Error('TTS request failed');

            // ── Streaming playback via MediaSource ──────────────────
            const audio = new Audio();
            this._currentAudio = audio;
            const mediaSource = new MediaSource();
            audio.src = URL.createObjectURL(mediaSource);

            // Set up audio analyser for orb waveform
            if (!this._playbackCtx) {
                this._playbackCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            const ctx = this._playbackCtx;

            // Track if we've already connected this audio element
            let sourceNode = null;
            let analyser = null;
            const dataArr = new Uint8Array(128);

            const pump = () => {
                if (analyser) {
                    analyser.getByteFrequencyData(dataArr);
                    let sum = 0;
                    for (let i = 0; i < dataArr.length; i++) sum += dataArr[i];
                    const avg = sum / dataArr.length / 255;
                    this.orb.setAudioLevel(avg * 1.8);
                }
                speakPump = requestAnimationFrame(pump);
            };

            audio.onplay = () => {
                // Connect analyser on first play
                if (!sourceNode) {
                    try {
                        sourceNode = ctx.createMediaElementSource(audio);
                        analyser = ctx.createAnalyser();
                        analyser.fftSize = 256;
                        sourceNode.connect(analyser);
                        analyser.connect(ctx.destination);
                    } catch (_) { /* already connected */ }
                }
                speakPump = requestAnimationFrame(pump);
            };
            audio.onended = () => { cleanup(); };
            audio.onerror = () => { cleanup(); };

            // Stream chunks into MediaSource as they arrive
            await new Promise((resolve, reject) => {
                mediaSource.addEventListener('sourceopen', async () => {
                    let sourceBuffer;
                    try {
                        sourceBuffer = mediaSource.addSourceBuffer('audio/mpeg');
                    } catch (_) {
                        // Browser doesn't support audio/mpeg in MSE — fall back to blob
                        reject(new Error('MSE_UNSUPPORTED'));
                        return;
                    }

                    const reader = resp.body.getReader();
                    let playStarted = false;
                    const queue = [];
                    let appending = false;
                    let done = false;

                    const appendNext = () => {
                        if (appending || queue.length === 0) return;
                        if (mediaSource.readyState !== 'open') return;
                        appending = true;
                        const chunk = queue.shift();
                        try { sourceBuffer.appendBuffer(chunk); } catch(_) { appending = false; }
                    };

                    sourceBuffer.addEventListener('updateend', () => {
                        appending = false;
                        // Start playback as soon as we have some data buffered
                        if (!playStarted && sourceBuffer.buffered.length > 0) {
                            playStarted = true;
                            audio.play().catch(() => {});
                        }
                        if (queue.length > 0) {
                            appendNext();
                        } else if (done && mediaSource.readyState === 'open') {
                            try { mediaSource.endOfStream(); } catch(_) {}
                            resolve();
                        }
                    });

                    // Read stream
                    try {
                        while (true) {
                            const { value, done: readerDone } = await reader.read();
                            if (readerDone) {
                                done = true;
                                if (!appending && queue.length === 0 && mediaSource.readyState === 'open') {
                                    try { mediaSource.endOfStream(); } catch(_) {}
                                    resolve();
                                }
                                break;
                            }
                            queue.push(value);
                            appendNext();
                        }
                    } catch (e) {
                        reject(e);
                    }
                }, { once: true });
            });
        } catch (e) {
            // Fallback: if MSE not supported or streaming failed, use blob approach
            if (e.message !== 'MSE_UNSUPPORTED') {
                // Try simple blob fallback
            }
            try {
                const resp2 = await fetch('/api/tts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text }),
                });
                if (resp2.ok) {
                    const blob = await resp2.blob();
                    const url = URL.createObjectURL(blob);
                    const audio2 = new Audio(url);
                    this._currentAudio = audio2;
                    audio2.onended = () => { URL.revokeObjectURL(url); cleanup(); };
                    audio2.onerror = () => { URL.revokeObjectURL(url); cleanup(); };
                    // Simulated pump for orb
                    const simPump = () => {
                        const t = performance.now() / 1000;
                        const level = 0.3 + Math.abs(Math.sin(t * 3.5)) * 0.3
                                    + Math.abs(Math.sin(t * 7.1)) * 0.15;
                        this.orb.setAudioLevel(Math.min(level, 1));
                        speakPump = requestAnimationFrame(simPump);
                    };
                    audio2.onplay = () => { speakPump = requestAnimationFrame(simPump); };
                    await audio2.play();
                    return;
                }
            } catch (_) {}

            // Final fallback: browser speechSynthesis
            const utter = new SpeechSynthesisUtterance(text);
            utter.lang = 'en-GB';
            utter.rate = 0.92;
            utter.pitch = 0.85;

            const simPump = () => {
                const t = performance.now() / 1000;
                const level = 0.3 + Math.abs(Math.sin(t * 3.5)) * 0.3
                            + Math.abs(Math.sin(t * 7.1)) * 0.15;
                this.orb.setAudioLevel(Math.min(level, 1));
                speakPump = requestAnimationFrame(simPump);
            };
            utter.onstart = () => { speakPump = requestAnimationFrame(simPump); };
            utter.onend = cleanup;
            utter.onerror = cleanup;
            this.synth.speak(utter);
        }
    }
}

// ── Conversation Console Logger ─────────────────────────────────
function logConvo(text, role) {
    const log = document.getElementById('convo-log');
    if (!log) return;

    const LABELS = {
        'user': '► YOU',
        'user-interim': '► MIC',
        'arbiter': '◄ ARBITER',
        'system': '● SYSTEM',
    };

    // For interim speech results, update in-place instead of adding new lines
    if (role === 'user-interim') {
        let interim = log.querySelector('.convo-line.user-interim');
        if (!interim) {
            interim = document.createElement('div');
            interim.className = 'convo-line user user-interim';
            log.appendChild(interim);
        }
        interim.innerHTML = '<span class="convo-label">' + LABELS[role] + '</span> ' + escapeHtml(text);
        log.scrollTop = log.scrollHeight;
        return;
    }

    // Remove interim line when we get a final result
    const oldInterim = log.querySelector('.convo-line.user-interim');
    if (oldInterim) oldInterim.remove();

    const line = document.createElement('div');
    line.className = 'convo-line ' + role;
    const label = LABELS[role] || role.toUpperCase();
    line.innerHTML = '<span class="convo-label">' + label + '</span> ' + mdToHtml(text);
    log.appendChild(line);
    // Keep max 50 lines
    while (log.children.length > 50) log.removeChild(log.firstChild);
    log.scrollTop = log.scrollHeight;
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Convert basic markdown (bold, italic, bullet lists) to HTML for chat display. */
function mdToHtml(str) {
    let s = escapeHtml(str);
    // **bold** or __bold__
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/__(.+?)__/g, '<strong>$1</strong>');
    // *italic* or _italic_  (but not inside words like file_name)
    s = s.replace(/(?<!\w)\*(.+?)\*(?!\w)/g, '<em>$1</em>');
    s = s.replace(/(?<!\w)_(.+?)_(?!\w)/g, '<em>$1</em>');
    // Bullet lists: lines starting with - or •
    s = s.replace(/^[\-•]\s+(.+)/gm, '<span class="chat-bullet">• $1</span>');
    return s;
}

// ── Floating Log Appender (max 10 visible lines) ────────────────
function appendLog(msg, level = '') {
    const el = document.getElementById('floating-logs');
    if (!el) return;
    const now = new Date();
    const ts = now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const line = document.createElement('div');
    line.className = 'log-line ' + level;
    line.innerHTML = `<span class="log-ts">${ts}</span> ${msg}`;
    el.appendChild(line);
    while (el.children.length > 10) el.removeChild(el.firstChild);
    el.scrollTop = el.scrollHeight;
}


// ════════════════════════════════════════════════════════════════
//  DASHBOARD — Polling and panel updates (unchanged logic)
// ════════════════════════════════════════════════════════════════

// ── Clock ────────────────────────────────────────────────────────
function updateClock() {
    const now = new Date();
    document.getElementById('clock-time').textContent =
        now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    document.getElementById('clock-date').textContent =
        now.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).toUpperCase();
    // Orb clock (large, below orb)
    const orbTime = document.getElementById('orb-clock-time');
    const orbDate = document.getElementById('orb-clock-date');
    if (orbTime) orbTime.textContent = now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    if (orbDate) orbDate.textContent = now.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }).toUpperCase();
}

// ── Business Profile State ────────────────────────────────────────
let _activeBusinessId = localStorage.getItem('arbiter_active_business') || '';
let _businesses = [];

function _getActiveBusinessId() { return _activeBusinessId; }

function _setActiveBusinessId(id) {
    _activeBusinessId = id || '';
    if (id) localStorage.setItem('arbiter_active_business', id);
    else localStorage.removeItem('arbiter_active_business');
}

async function _loadBusinesses() {
    try {
        const r = await fetch('/api/businesses');
        if (!r.ok) return;
        const data = await r.json();
        _businesses = data.businesses || [];
        // If active business no longer exists, reset to all
        if (_activeBusinessId && !_businesses.find(b => b.id === _activeBusinessId)) {
            _setActiveBusinessId('');
        }
    } catch (e) { console.warn('[BIZ] Failed to load businesses:', e); }
}

// ── API helper ───────────────────────────────────────────────────
async function api(path, method, body) {
    try {
        const opts = { method: method || 'GET', headers: {} };
        // Inject active business context
        if (_activeBusinessId) opts.headers['X-Business-Id'] = _activeBusinessId;
        if (body) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = typeof body === 'string' ? body : JSON.stringify(body);
        }
        const r = await fetch(path, opts);
        if (!r.ok) return null;
        return await r.json();
    } catch { return null; }
}

// ── System Status ────────────────────────────────────────────────
let firstStatusCheck = true;
async function refreshStatus() {
    // ── ComfyUI (RTX 3080) status check ──
    let comfyOnline = false;
    try {
        const comfyUrl = window._COMFYUI_URL || 'http://127.0.0.1:8188';
        const cr = await fetch(comfyUrl + '/system_stats', { signal: AbortSignal.timeout(3000) });
        comfyOnline = cr.ok;
    } catch { /* offline */ }
    setDot('s-comfyui', comfyOnline ? 'online' : 'offline');

    // ── OpenRouter status check ──
    let orOnline = false;
    try {
        const orData = await api('/api/openrouter-usage');
        orOnline = orData && orData.configured && orData.circuit_breaker !== 'open';
    } catch { /* offline */ }
    setDot('s-openrouter', orOnline ? 'online' : 'offline');

    // ── Overall badge ──
    const badge = document.getElementById('system-badge');
    const allOnline = comfyOnline && orOnline;
    const allOffline = !comfyOnline && !orOnline;
    badge.textContent = allOnline ? '● ALL SYSTEMS NOMINAL' : allOffline ? '● SYSTEMS OFFLINE' : '● DEGRADED';
    badge.className = 'system-status ' + (allOnline ? 'online' : allOffline ? 'offline' : 'degraded');

    if (firstStatusCheck) {
        firstStatusCheck = false;
    }
}

function setDot(id, status) {
    const el = document.getElementById(id);
    if (!el) return;
    const dot = el.querySelector('.ind-dot');
    if (!dot) return;
    const on = status === 'online';
    const noData = status === 'no data';
    dot.className = 'ind-dot ' + (on ? 'online' : noData ? 'no-data' : 'offline');
}

// ── LLM Status ──────────────────────────────────────────────────
async function refreshLLMStatus() {
    try {
        // Try Ollama first
        const r = await fetch('/api/status');
        const d = r.ok ? await r.json() : null;
        const llmOnline = d && d.llm_status === 'online';
        setDot('s-llm', llmOnline ? 'online' : 'offline');
        const indicator = document.getElementById('s-llm');
        if (indicator) {
            const provider = d && d.llm_provider ? d.llm_provider.toUpperCase() : 'LLM';
            indicator.setAttribute('data-label', provider);
        }
    } catch { setDot('s-llm', 'offline'); }
}

// ── System Info (CPU / MEM / Disk / Net) + History for Graphs ────
const SYS_HISTORY_MAX = 30; // 30 data points
const sysHistory = { cpu: [], mem: [] };
let sysCpuChart = null, sysMemChart = null;

async function refreshSystemInfo() {
    const d = await api('/api/system-info');
    if (!d) return;
    const set = (id, pct) => {
        const fill = document.getElementById(id);
        const val = document.getElementById(id + '-val');
        if (fill) {
            fill.style.width = pct + '%';
            fill.className = 'sys-fill' + (pct > 85 ? ' warn' : '');
        }
        if (val) val.textContent = pct + '%';
    };
    set('sys-cpu', d.cpu || 0);
    set('sys-mem', d.memory || 0);
    set('sys-disk', d.disk || 0);
    set('sys-net', d.network || 0);

    // Track history for graphs
    sysHistory.cpu.push(d.cpu || 0);
    sysHistory.mem.push(d.memory || 0);
    if (sysHistory.cpu.length > SYS_HISTORY_MAX) sysHistory.cpu.shift();
    if (sysHistory.mem.length > SYS_HISTORY_MAX) sysHistory.mem.shift();
    updateSysGraphs();
}

function updateSysGraphs() {
    if (typeof Chart === 'undefined') return;
    const labels = sysHistory.cpu.map((_, i) => '');
    const chartOpts = (label, color) => ({
        type: 'line',
        data: {
            labels,
            datasets: [{
                label, data: [...(label === 'CPU %' ? sysHistory.cpu : sysHistory.mem)],
                borderColor: color, backgroundColor: color.replace('1)', '0.1)'),
                borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.4,
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            animation: { duration: 300 },
            plugins: { legend: { display: true, labels: { color: '#7a9aaa', font: { size: 11, family: "'Courier New'" } } } },
            scales: {
                x: { display: false },
                y: { min: 0, max: 100, ticks: { color: '#5a7a8a', font: { size: 10 }, stepSize: 25 }, grid: { color: 'rgba(60,220,255,0.06)' } }
            }
        }
    });
    const cpuCtx = document.getElementById('sys-cpu-chart');
    const memCtx = document.getElementById('sys-mem-chart');
    if (cpuCtx) {
        if (sysCpuChart) { sysCpuChart.data.labels = labels; sysCpuChart.data.datasets[0].data = [...sysHistory.cpu]; sysCpuChart.update('none'); }
        else { sysCpuChart = new Chart(cpuCtx, chartOpts('CPU %', 'rgba(64,212,255,1)')); }
    }
    if (memCtx) {
        if (sysMemChart) { sysMemChart.data.labels = labels; sysMemChart.data.datasets[0].data = [...sysHistory.mem]; sysMemChart.update('none'); }
        else { sysMemChart = new Chart(memCtx, chartOpts('MEM %', 'rgba(42,255,153,1)')); }
    }
}

// System panel click → toggle graphs
document.addEventListener('DOMContentLoaded', () => {
    const sysPanel = document.getElementById('sys-info-panel');
    const graphsPanel = document.getElementById('sys-graphs-panel');
    if (sysPanel && graphsPanel) {
        sysPanel.addEventListener('click', () => {
            graphsPanel.classList.toggle('active');
        });
    }
});

// ── GCP Pod Metrics ─────────────────────────────────────────────
async function refreshGCPPods() {
    const d = await api('/api/gcp/pods');
    const el = document.getElementById('gcp-pods');
    if (!el) return;
    if (!d || !d.pods || d.pods.length === 0) {
        el.innerHTML = '<div class="feed-empty">NO PODS DATA</div>';
        return;
    }
    // Summary row
    const total = d.pods.length;
    const healthy = d.pods.filter(p => p.status === 'Running').length;
    let html = `<div class="gcp-pod-summary">
        <span><span class="ps-val">${healthy}</span>/${total} HEALTHY</span>
        <span>REPLICAS: <span class="ps-val">${d.replicas || total}</span></span>
        ${d.alerts ? `<span style="color:var(--red)">ALERTS: <span class="ps-val">${d.alerts}</span></span>` : ''}
    </div>`;
    // Pod rows
    d.pods.forEach(pod => {
        const dotCls = pod.status === 'Running' ? 'healthy' : pod.status === 'Pending' ? 'pending' : 'unhealthy';
        const cpuCls = (pod.cpu || 0) > 80 ? 'alert' : (pod.cpu || 0) > 60 ? 'warn' : '';
        const memCls = (pod.memory || 0) > 80 ? 'alert' : (pod.memory || 0) > 60 ? 'warn' : '';
        html += `<div class="gcp-pod-row">
            <span class="gcp-pod-dot ${dotCls}"></span>
            <span class="gcp-pod-name">${pod.name || 'pod'}</span>
            <span class="gcp-pod-metric ${cpuCls}">CPU ${pod.cpu || 0}%</span>
            <span class="gcp-pod-metric ${memCls}">MEM ${pod.memory || 0}%</span>
        </div>`;
    });
    el.innerHTML = html;
}

// ── Startup Guide ───────────────────────────────────────────────
function showStartupGuide(systems) {
    const overlay = document.getElementById('startup-overlay');
    const depsEl = document.getElementById('startup-deps');
    const instrEl = document.getElementById('startup-instructions');
    if (!overlay || !depsEl) return;

    const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
    const platform = isMac ? 'macOS' : 'Windows';

    // Build dependency list
    const deps = [
        { name: 'ComfyUI · RTX 3080', status: systems.comfyui || 'offline', hint: 'ComfyUI image generation server' },
        { name: 'OpenRouter', status: systems.openrouter || 'offline', hint: 'OpenRouter LLM API' },
    ];

    let depsHtml = '';
    deps.forEach(dep => {
        const on = dep.status === 'online';
        const cls = on ? 'online' : dep.status === 'no data' ? 'no-data' : 'offline';
        depsHtml += `<div class="startup-dep">
            <span class="ind-dot ${cls}">●</span>
            <span class="startup-dep-name">${dep.name}</span>
            <span class="startup-dep-hint">${on ? '✓ Online' : dep.hint + ' — ' + dep.status.toUpperCase()}</span>
        </div>`;
    });
    depsEl.innerHTML = depsHtml;

    // Platform-specific instructions
    let instr = `<p style="margin-top:16px; color: var(--cyan); font-family: var(--font-mono); font-size: 13px; letter-spacing: 2px;">${platform} SETUP</p>`;
    if ((systems.comfyui || 'offline') !== 'online') {
        instr += `<p>ComfyUI: Start your ComfyUI server (default: <code>http://127.0.0.1:8188</code>).</p>`;
    }
    if ((systems.openrouter || 'offline') !== 'online') {
        instr += `<p>OpenRouter: Set <code>OPENROUTER_API_KEY</code> in your .env file.</p>`;
    }
    instrEl.innerHTML = instr;

    overlay.classList.add('active');

    document.getElementById('startup-dismiss').addEventListener('click', () => {
        overlay.classList.remove('active');
    });
}

// ── CI/CD — Dynamic per-business ────────────────────────────────
async function refreshCICD() {
    const data = await api('/api/cicd');
    const grid = document.getElementById('cicd-grid');
    if (!grid) return;

    if (!data || Object.keys(data).length === 0) {
        grid.innerHTML = '<div class="feed-empty">NO CI/CD JOBS CONFIGURED</div>';
        const dockPass = document.getElementById('dock-cicd-pass');
        const dockFail = document.getElementById('dock-cicd-fail');
        if (dockPass) dockPass.textContent = '0';
        if (dockFail) dockFail.textContent = '0';
        return;
    }

    let passCount = 0, failCount = 0;
    let html = '';
    // Group by business if showing all
    let lastBiz = null;
    for (const [key, job] of Object.entries(data)) {
        const status = job.status || 'unknown';
        const time = job.time || '';
        const url = job.url || '#';
        const name = job.name || key;
        const bizName = job.business_name || '';
        if (status === 'success') passCount++;
        if (status === 'failure') failCount++;
        // Show business label when showing all
        if (!_activeBusinessId && bizName && bizName !== lastBiz) {
            html += `<div class="cicd-biz-label">${_escHtml(bizName)}</div>`;
            lastBiz = bizName;
        }
        html += `<div class="cicd-job">
            <span class="cicd-status ${status}"></span>
            <span class="cicd-name">${_escHtml(name)}</span>
            ${time ? `<span class="cicd-time">${time}</span>` : ''}
            ${url !== '#' ? `<a class="cicd-link" href="${url}" target="_blank">VIEW</a>` : `<span class="cicd-time">NO BUILD</span>`}
        </div>`;
    }
    grid.innerHTML = html;

    const dockPass = document.getElementById('dock-cicd-pass');
    const dockFail = document.getElementById('dock-cicd-fail');
    if (dockPass) dockPass.textContent = passCount;
    if (dockFail) dockFail.textContent = failCount;
}

// ── Claude Token Usage ──────────────────────────────────────────
let _lastClaudeCost = 0;
let _lastOrCost = 0;

async function refreshClaudeUsage() {
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

    // ── Claude ──
    const d = await api('/api/claude-usage');
    if (d) {
        console.debug('[LLM] Claude usage:', JSON.stringify({cost: d.daily_cost_usd, budget: d.daily_budget_usd, reqs: d.session_requests, blocked: d.blocked, circuit: d.circuit_breaker}));
        set('cl-model', d.model ? d.model.toUpperCase() : '—');
        set('cl-cost', d.daily_cost_usd != null ? `$${Number(d.daily_cost_usd).toFixed(4)}` : '—');
        set('cl-budget', d.daily_budget_usd != null ? `$${Number(d.daily_budget_usd).toFixed(2)}` : '—');
        set('cl-input-tok', d.daily_input_tokens != null ? Number(d.daily_input_tokens).toLocaleString() : '—');
        set('cl-output-tok', d.daily_output_tokens != null ? Number(d.daily_output_tokens).toLocaleString() : '—');
        set('cl-reqs', d.session_requests != null ? `${d.session_requests} / ${d.session_limit || '—'}` : '—');
        set('cl-rpm', d.rpm_limit || '—');
        set('cl-circuit', d.circuit_breaker === 'open' ? 'OPEN ⚠' : 'CLOSED ✓');
        const pct = d.daily_budget_usd > 0 ? Math.min(100, (d.daily_cost_usd / d.daily_budget_usd) * 100) : 0;
        const fill = document.getElementById('cl-budget-fill');
        if (fill) {
            fill.style.width = pct + '%';
            fill.style.background = pct > 80 ? 'var(--red)' : pct > 50 ? 'var(--amber)' : 'var(--cyan)';
        }
        set('cl-budget-pct', pct.toFixed(1) + '%');
        const blocked = d.blocked;
        const blockedEl = document.getElementById('cl-blocked-status');
        if (blockedEl) {
            blockedEl.textContent = blocked ? 'BLOCKED: ' + blocked : 'OPERATIONAL';
            blockedEl.style.color = blocked ? 'var(--red)' : 'var(--green)';
        }
        _lastClaudeCost = d.daily_cost_usd || 0;
        // Dock stat + status dot
        const dockCost = document.getElementById('dock-claude-cost');
        if (dockCost) {
            dockCost.textContent = d.daily_cost_usd != null ? `$${Number(d.daily_cost_usd).toFixed(3)}` : '—';
            dockCost.className = 'dp-val' + (pct > 80 ? ' alert' : pct > 50 ? ' caution' : ' nominal');
        }
        const claudeDot = document.getElementById('dock-claude-dot');
        if (claudeDot) {
            claudeDot.className = 'dp-status-dot' + (blocked ? ' err' : d.circuit_breaker === 'open' ? ' warn' : d.configured ? ' ok' : '');
        }
    }

    // ── OpenRouter ──
    const o = await api('/api/openrouter-usage');
    if (!o) {
        console.warn('[LLM] OpenRouter usage fetch returned null — endpoint may be down or returning non-200');
    }
    if (o) {
        console.debug('[LLM] OpenRouter usage:', JSON.stringify({configured: o.configured, cost: o.daily_cost_usd, budget: o.daily_budget_usd, balance: o.account_balance_usd, model: o.agent_model, reqs: o.session_requests, blocked: o.blocked, circuit: o.circuit_breaker}));
        const modelName = o.agent_model ? o.agent_model.split('/').pop().toUpperCase() : '—';
        set('or-model', modelName);
        set('or-cost', o.daily_cost_usd != null ? `$${Number(o.daily_cost_usd).toFixed(4)}` : '—');
        // Account balance / usage from OpenRouter API
        const balEl = document.getElementById('or-balance');
        const balLabel = balEl?.closest('.readout-cell')?.querySelector('.rl');
        if (balEl) {
            if (o.account_balance_usd != null) {
                // Key has a credit cap — show remaining balance
                balEl.textContent = `$${Number(o.account_balance_usd).toFixed(2)}`;
                balEl.style.color = o.account_balance_usd < 1 ? 'var(--red)' : o.account_balance_usd < 5 ? 'var(--amber)' : 'var(--green)';
                if (balLabel) balLabel.textContent = '$ REMAINING';
            } else if (o.account_usage_usd != null) {
                // Pay-as-you-go — show total spend
                balEl.textContent = `$${Number(o.account_usage_usd).toFixed(2)}`;
                balEl.style.color = 'var(--cyan)';
                if (balLabel) balLabel.textContent = '$ TOTAL SPEND';
            } else {
                balEl.textContent = o.configured ? '—' : '—';
                balEl.style.color = 'var(--text-dim)';
            }
        }
        set('or-budget', o.daily_budget_usd != null ? `$${Number(o.daily_budget_usd).toFixed(2)}` : '—');
        set('or-input-tok', o.daily_input_tokens != null ? Number(o.daily_input_tokens).toLocaleString() : '—');
        set('or-output-tok', o.daily_output_tokens != null ? Number(o.daily_output_tokens).toLocaleString() : '—');
        set('or-reqs', o.session_requests != null ? `${o.session_requests} / ${o.session_limit || '—'}` : '—');
        set('or-rpm', o.rpm_limit || '—');
        set('or-circuit', o.circuit_breaker === 'open' ? 'OPEN ⚠' : 'CLOSED ✓');
        const orPct = o.daily_budget_usd > 0 ? Math.min(100, (o.daily_cost_usd / o.daily_budget_usd) * 100) : 0;
        const orFill = document.getElementById('or-budget-fill');
        if (orFill) {
            orFill.style.width = orPct + '%';
            orFill.style.background = orPct > 80 ? 'var(--red)' : orPct > 50 ? 'var(--amber)' : 'var(--green)';
        }
        set('or-budget-pct', orPct.toFixed(1) + '%');
        const orBlocked = o.blocked;
        const orBlockedEl = document.getElementById('or-blocked-status');
        if (orBlockedEl) {
            orBlockedEl.textContent = orBlocked ? 'BLOCKED: ' + orBlocked : (o.configured ? 'OPERATIONAL' : 'NOT CONFIGURED');
            orBlockedEl.style.color = orBlocked ? 'var(--red)' : (o.configured ? 'var(--green)' : 'var(--amber)');
        }
        _lastOrCost = o.daily_cost_usd || 0;
        // Dock stat + status dot — show balance (capped) or daily spend (pay-as-you-go)
        const dockOrCost = document.getElementById('dock-or-cost');
        if (dockOrCost) {
            if (o.account_balance_usd != null) {
                dockOrCost.textContent = `$${Number(o.account_balance_usd).toFixed(2)}`;
                dockOrCost.className = 'dp-val' + (o.account_balance_usd < 1 ? ' alert' : o.account_balance_usd < 5 ? ' caution' : ' nominal');
            } else if (o.account_usage_daily_usd != null) {
                dockOrCost.textContent = `$${Number(o.account_usage_daily_usd).toFixed(3)}`;
                dockOrCost.className = 'dp-val nominal';
            } else {
                dockOrCost.textContent = o.daily_cost_usd != null ? `$${Number(o.daily_cost_usd).toFixed(3)}` : '—';
                dockOrCost.className = 'dp-val' + (orPct > 80 ? ' alert' : orPct > 50 ? ' caution' : ' nominal');
            }
        }
        const orDot = document.getElementById('dock-or-dot');
        if (orDot) {
            orDot.className = 'dp-status-dot' + (orBlocked ? ' err' : o.circuit_breaker === 'open' ? ' warn' : o.configured ? ' ok' : '');
        }
    }

    // ── Gemini ──
    const g = await api('/api/gemini-usage');
    if (g) {
        console.debug('[LLM] Gemini usage:', JSON.stringify({configured: g.configured, calls: g.daily_calls, cap: g.daily_call_cap, tokens_in: g.daily_input_tokens, tokens_out: g.daily_output_tokens, blocked: g.blocked, circuit: g.circuit_breaker}));
        set('gem-model', g.model ? g.model.toUpperCase() : '—');
        set('gem-calls', g.daily_calls != null ? `${g.daily_calls}` : '—');
        set('gem-cap', g.daily_call_cap != null ? `${g.daily_call_cap}` : '—');
        set('gem-session', g.session_calls != null ? `${g.session_calls}` : '—');
        set('gem-input-tok', g.daily_input_tokens != null ? Number(g.daily_input_tokens).toLocaleString() : '—');
        set('gem-output-tok', g.daily_output_tokens != null ? Number(g.daily_output_tokens).toLocaleString() : '—');
        set('gem-circuit', g.circuit_breaker === 'open' ? 'OPEN ⚠' : 'CLOSED ✓');
        set('gem-cost-label', '$0.00 (free tier)');
        const gemPct = g.daily_call_cap > 0 ? Math.min(100, (g.daily_calls / g.daily_call_cap) * 100) : 0;
        const gemFill = document.getElementById('gem-budget-fill');
        if (gemFill) {
            gemFill.style.width = gemPct + '%';
            gemFill.style.background = gemPct > 80 ? 'var(--red)' : gemPct > 60 ? 'var(--amber)' : 'var(--purple, #b388ff)';
        }
        set('gem-budget-pct', gemPct.toFixed(1) + '%');
        const gemBlockedEl = document.getElementById('gem-blocked-status');
        if (gemBlockedEl) {
            gemBlockedEl.textContent = g.blocked ? 'BLOCKED: ' + g.blocked : (g.configured ? 'OPERATIONAL' : 'NOT CONFIGURED');
            gemBlockedEl.style.color = g.blocked ? 'var(--red)' : (g.configured ? 'var(--green)' : 'var(--amber)');
        }
        // Dock stat
        const dockGemCalls = document.getElementById('dock-gem-calls');
        if (dockGemCalls) {
            dockGemCalls.textContent = g.daily_calls != null ? `${g.daily_calls}/${g.daily_call_cap}` : '—';
            dockGemCalls.className = 'dp-val' + (gemPct > 80 ? ' alert' : gemPct > 60 ? ' caution' : ' nominal');
        }
        const gemDot = document.getElementById('dock-gem-dot');
        if (gemDot) {
            gemDot.className = 'dp-status-dot' + (g.blocked ? ' err' : g.circuit_breaker === 'open' ? ' warn' : g.configured ? ' ok' : '');
        }
    }

    // ── Combined total ──
    const totalCost = _lastClaudeCost + _lastOrCost;
    set('llm-total-cost', `$${totalCost.toFixed(4)}`);
}

// ── Email Intelligence ───────────────────────────────────────────
let emailBarChart = null;
let emailDonutChart = null;

async function refreshEmail() {
    const d = await api('/api/email/summary');
    if (!d) return;
    document.getElementById('em-total').textContent = d.total;
    document.getElementById('em-unread').textContent = d.unread;
    document.getElementById('em-replied').textContent = d.replied;
    document.getElementById('em-urgent').textContent = d.urgent;

    // Bar chart
    const barCtx = document.getElementById('email-chart');
    if (barCtx && typeof Chart !== 'undefined') {
        const labels = ['Received', 'Unread', 'Replied', 'Urgent'];
        const values = [d.total, d.unread, d.replied, d.urgent];
        const colors = ['rgba(0,200,255,0.6)', 'rgba(255,170,0,0.6)', 'rgba(0,255,136,0.6)', 'rgba(255,51,85,0.6)'];
        if (emailBarChart) {
            emailBarChart.data.datasets[0].data = values;
            emailBarChart.update('none');
        } else {
            emailBarChart = new Chart(barCtx, {
                type: 'bar',
                data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#6b8899', font: { size: 10, family: 'Courier New' } }, grid: { color: 'rgba(0,200,255,0.06)' } },
                        y: { ticks: { color: '#6b8899', font: { size: 10 } }, grid: { color: 'rgba(0,200,255,0.06)' }, beginAtZero: true }
                    }
                }
            });
        }
    }

    // Dock stats
    const deu = document.getElementById('dock-email-unread');
    const deg = document.getElementById('dock-email-urgent');
    if (deu) deu.textContent = d.unread || 0;
    if (deg) deg.textContent = d.urgent || 0;

    // Donut chart
    const donutCtx = document.getElementById('email-donut-chart');
    if (donutCtx && typeof Chart !== 'undefined') {
        const read = Math.max(d.total - d.unread, 0);
        const vals = [read, d.unread, d.urgent];
        if (emailDonutChart) {
            emailDonutChart.data.datasets[0].data = vals;
            emailDonutChart.update('none');
        } else {
            emailDonutChart = new Chart(donutCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Read', 'Unread', 'Urgent'],
                    datasets: [{ data: vals, backgroundColor: ['rgba(0,255,136,0.5)', 'rgba(255,170,0,0.5)', 'rgba(255,51,85,0.5)'], borderWidth: 0 }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false, cutout: '65%',
                    plugins: { legend: { position: 'bottom', labels: { color: '#6b8899', font: { size: 10, family: 'Courier New' }, padding: 8 } } }
                }
            });
        }
    }

    // Populate email list in dock panel
    const emailListEl = document.getElementById('email-list');
    if (emailListEl) {
        const recent = await api('/api/email/recent');
        if (recent && Array.isArray(recent)) {
            emailListEl.innerHTML = recent.slice(0, 10).map(e => {
                const catColor = e.category === 'customer_inquiry' ? '#00ff88' :
                                 e.category === 'business' ? '#00c8ff' :
                                 e.category === 'spam' || e.category === 'newsletter' ? '#4a5568' : '#6b8899';
                const urgentDot = e.is_urgent ? '<span style="color:#ff3355;margin-right:4px">●</span>' : '';
                const unreadStyle = e.is_read ? 'opacity:0.6' : 'font-weight:bold';
                const catLabel = e.category ? `<span style="color:${catColor};font-size:0.65em;text-transform:uppercase;margin-left:6px">${e.category.replace('_',' ')}</span>` : '';
                return `<div class="email-row" data-uid="${e.uid}" style="padding:6px 8px;border-bottom:1px solid rgba(0,200,255,0.08);cursor:pointer;${unreadStyle};transition:background 0.2s" onmouseover="this.style.background='rgba(0,200,255,0.06)'" onmouseout="this.style.background='transparent'">
                    <div style="font-size:0.8em;color:#00c8ff;display:flex;align-items:center">${urgentDot}${(e.sender||'').substring(0,35)}${catLabel}</div>
                    <div style="font-size:0.75em;color:#8ba4b5;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${e.subject||'(No subject)'}</div>
                </div>`;
            }).join('');
            // Add click handlers
            emailListEl.querySelectorAll('.email-row').forEach(row => {
                row.addEventListener('click', () => openEmailDetail(row.dataset.uid));
            });
        }
    }
}

// ── Email Detail & Reply Panel ───────────────────────────────────
async function openEmailDetail(uid) {
    const d = await api(`/api/email/detail/${uid}`);
    if (!d || d.error) { console.warn('[Email] Detail fetch failed:', d?.error); return; }

    // Close any open dock panel
    if (typeof activeDock !== 'undefined' && activeDock) closeExpandPanels();

    // Build analysis panel with email content
    const bodyPreview = (d.body || d.snippet || '(No content)').substring(0, 2000);
    const catBadge = d.category ? `<span style="background:rgba(0,200,255,0.15);padding:2px 8px;border-radius:4px;font-size:0.7em;text-transform:uppercase;color:#00c8ff">${d.category.replace('_',' ')}</span>` : '';

    const panel = {
        title: `📧 ${d.subject || 'Email Detail'}`,
        stats: [
            { label: 'From', value: (d.sender || '').substring(0, 40) },
            { label: 'Date', value: (d.date || '').substring(0, 25) },
            { label: 'Category', value: d.category ? d.category.replace('_', ' ') : 'Unclassified' },
            { label: 'Status', value: d.is_replied ? 'Replied' : d.is_read ? 'Read' : 'Unread',
              status: d.is_replied ? 'good' : d.is_read ? null : 'warn' },
        ],
        summary: bodyPreview,
    };

    if (typeof voice !== 'undefined' && voice._renderAnalysisPanel) {
        voice._renderAnalysisPanel(panel, true);

        // Inject reply button into right wing after render
        setTimeout(() => {
            const wingR = document.getElementById('analysis-wing-right');
            if (!wingR) return;
            const existing = wingR.querySelector('.email-action-bar');
            if (existing) existing.remove();

            const bar = document.createElement('div');
            bar.className = 'email-action-bar';
            bar.style.cssText = 'display:flex;gap:8px;padding:12px 0;border-top:1px solid rgba(0,200,255,0.15);margin-top:12px;';
            bar.innerHTML = `
                <button class="email-reply-btn" data-uid="${uid}" style="flex:1;padding:8px 16px;background:rgba(0,200,255,0.15);border:1px solid rgba(0,200,255,0.3);color:#00c8ff;border-radius:6px;cursor:pointer;font-family:'Courier New',monospace;font-size:0.85em;transition:all 0.2s">
                    ✉ DRAFT REPLY
                </button>
                <button class="email-classify-btn" data-uid="${uid}" style="padding:8px 12px;background:rgba(100,255,218,0.1);border:1px solid rgba(100,255,218,0.2);color:#64ffda;border-radius:6px;cursor:pointer;font-family:'Courier New',monospace;font-size:0.85em;transition:all 0.2s">
                    🏷 CLASSIFY
                </button>
            `;
            // Append to the summary/content area
            const content = wingR.querySelector('.analysis-content') || wingR;
            content.appendChild(bar);

            bar.querySelector('.email-reply-btn').addEventListener('click', () => _emailDraftReply(uid));
            bar.querySelector('.email-classify-btn').addEventListener('click', () => _emailClassify());
        }, 200);
    }
}

async function _emailDraftReply(uid) {
    const btn = document.querySelector(`.email-reply-btn[data-uid="${uid}"]`);
    if (btn) { btn.textContent = '⏳ DRAFTING...'; btn.disabled = true; }

    const d = await api('/api/email/draft-reply', { method: 'POST', body: JSON.stringify({ uid }) });
    if (!d || d.error) {
        if (btn) { btn.textContent = '❌ FAILED'; btn.disabled = false; }
        console.warn('[Email] Draft failed:', d?.error);
        return;
    }

    // Show draft in a new panel
    const panel = {
        title: `✉ DRAFT REPLY — ${(d.subject || '').substring(0, 50)}`,
        stats: [
            { label: 'To', value: (d.to || '').substring(0, 40) },
            { label: 'Subject', value: (d.subject || '').substring(0, 50) },
        ],
        summary: d.draft || '(Empty draft)',
    };

    if (typeof voice !== 'undefined' && voice._renderAnalysisPanel) {
        voice._renderAnalysisPanel(panel, true);

        // Inject send/edit buttons
        setTimeout(() => {
            const wingR = document.getElementById('analysis-wing-right');
            if (!wingR) return;
            const existing = wingR.querySelector('.email-action-bar');
            if (existing) existing.remove();

            const bar = document.createElement('div');
            bar.className = 'email-action-bar';
            bar.style.cssText = 'display:flex;gap:8px;padding:12px 0;border-top:1px solid rgba(0,200,255,0.15);margin-top:12px;';
            bar.innerHTML = `
                <button class="email-send-btn" style="flex:1;padding:10px 16px;background:rgba(0,255,136,0.15);border:1px solid rgba(0,255,136,0.3);color:#00ff88;border-radius:6px;cursor:pointer;font-family:'Courier New',monospace;font-size:0.9em;font-weight:bold">
                    📤 SEND REPLY
                </button>
                <button class="email-cancel-btn" style="padding:10px 12px;background:rgba(255,51,85,0.1);border:1px solid rgba(255,51,85,0.2);color:#ff3355;border-radius:6px;cursor:pointer;font-family:'Courier New',monospace;font-size:0.85em">
                    ✕ CANCEL
                </button>
            `;
            const content = wingR.querySelector('.analysis-content') || wingR;
            content.appendChild(bar);

            bar.querySelector('.email-send-btn').addEventListener('click', async () => {
                bar.querySelector('.email-send-btn').textContent = '⏳ SENDING...';
                bar.querySelector('.email-send-btn').disabled = true;
                const result = await api('/api/email/send', {
                    method: 'POST',
                    body: JSON.stringify({
                        to: d.to, subject: d.subject,
                        body: d.draft, in_reply_to: d.in_reply_to || '',
                    }),
                });
                if (result && result.ok) {
                    bar.querySelector('.email-send-btn').textContent = '✅ SENT';
                    bar.querySelector('.email-send-btn').style.background = 'rgba(0,255,136,0.25)';
                    if (typeof voice !== 'undefined') voice._speak(`Reply sent to ${d.to.split('<')[0].trim()}, Sir.`);
                    setTimeout(() => { if (typeof voice !== 'undefined') voice._closeAnalysisWings(); }, 3000);
                } else {
                    bar.querySelector('.email-send-btn').textContent = '❌ FAILED';
                    bar.querySelector('.email-send-btn').disabled = false;
                    console.warn('[Email] Send failed:', result?.error);
                }
            });
            bar.querySelector('.email-cancel-btn').addEventListener('click', () => {
                if (typeof voice !== 'undefined') voice._closeAnalysisWings();
            });
        }, 200);
    }
}

async function _emailClassify() {
    const d = await api('/api/email/classify', { method: 'POST', body: '{}' });
    if (d && d.classified > 0) {
        logConvo(`Classified ${d.classified} emails`, 'system');
        refreshEmail();
    }
}

// ── Notification Banner System ───────────────────────────────────
const _NOTIF_CLEAR_MS = 20 * 60 * 1000; // 20 minutes
const _notifSeen = new Set(); // dedup by source+message hash

function _notifIcon(level) {
    if (level === 'critical') return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
    if (level === 'high' || level === 'warning') return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';
}

function _showNotifBanner(level, source, message) {
    const key = `${source}::${message}`;
    if (_notifSeen.has(key)) return;
    _notifSeen.add(key);

    const stack = document.getElementById('notif-stack');
    if (!stack) return;

    const el = document.createElement('div');
    el.className = `notif-banner ${level || 'info'}`;
    const now = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    el.innerHTML = `
        <span class="notif-banner-icon">${_notifIcon(level)}</span>
        <div class="notif-banner-body">
            <div class="notif-banner-source">${_escHtml(source)}</div>
            <div class="notif-banner-msg">${_escHtml(message)}</div>
            <div class="notif-banner-time">${now}</div>
        </div>
        <button class="notif-banner-close" title="Dismiss">✕</button>`;

    // Click to expand/collapse message
    el.querySelector('.notif-banner-msg').addEventListener('click', (e) => {
        e.stopPropagation();
        e.target.classList.toggle('expanded');
    });

    // Close button
    el.querySelector('.notif-banner-close').addEventListener('click', (e) => {
        e.stopPropagation();
        _dismissNotifBanner(el, key);
    });

    stack.prepend(el);

    // Auto-clear after 20 minutes
    setTimeout(() => _dismissNotifBanner(el, key), _NOTIF_CLEAR_MS);

    // Cap at 6 visible banners
    const banners = stack.querySelectorAll('.notif-banner:not(.dismissing)');
    if (banners.length > 6) {
        for (let i = 6; i < banners.length; i++) {
            _dismissNotifBanner(banners[i]);
        }
    }
}

function _dismissNotifBanner(el, key) {
    if (!el || el.classList.contains('dismissing')) return;
    el.classList.add('dismissing');
    if (key) _notifSeen.delete(key);
    setTimeout(() => el.remove(), 450);
}

// ── Panel-overlap notification banner ────────────────────────────
// Shows a dismissable banner when a new analysis panel arrives while one is already active.
// User can click "View" to close the current panel and show the queued one, or dismiss it.
function _showPanelNotif(panel, voiceRef) {
    const stack = document.getElementById('notif-stack');
    if (!stack) return;
    const title = panel.title || panel.sections?.[0]?.title || 'Analysis';
    const el = document.createElement('div');
    el.className = 'notif-banner info';
    const now = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    el.innerHTML = `
        <span class="notif-banner-icon">📊</span>
        <div class="notif-banner-body">
            <div class="notif-banner-source">New Analysis Ready</div>
            <div class="notif-banner-msg">${_escHtml(title)}</div>
            <div class="notif-banner-time">${now}</div>
        </div>
        <button class="notif-panel-view" title="View this panel">VIEW</button>
        <button class="notif-banner-close" title="Dismiss">✕</button>`;

    el.querySelector('.notif-panel-view').addEventListener('click', (e) => {
        e.stopPropagation();
        // Close whatever is active, then render queued panel
        if (typeof activeDock !== 'undefined' && activeDock) closeExpandPanels();
        if (voiceRef && voiceRef._closeAnalysisWings) voiceRef._closeAnalysisWings();
        setTimeout(() => {
            if (voiceRef && voiceRef._renderAnalysisPanel) {
                voiceRef._renderAnalysisPanel(panel, true);
            }
        }, 300);
        el.remove();
    });
    el.querySelector('.notif-banner-close').addEventListener('click', (e) => {
        e.stopPropagation();
        _dismissNotifBanner(el);
    });

    stack.prepend(el);
    // Auto-dismiss after 60s
    setTimeout(() => _dismissNotifBanner(el), 60000);
}

// ── Urgent Bulletins ─────────────────────────────────────────────
async function refreshBulletins() {
    const d = await api('/api/bulletins');
    // Update dock panel feed (hidden panel — for when user opens Bulletins dock panel)
    const dockFeed = document.getElementById('bulletin-feed');
    if (!d || d.length === 0) {
        if (dockFeed) dockFeed.innerHTML = '<div class="feed-empty">All systems nominal.</div>';
        return;
    }
    // Render into dock panel
    if (dockFeed) {
        dockFeed.innerHTML = d.map(b => `
            <div class="bulletin-item">
                <span class="bull-level ${b.level}">${b.level.toUpperCase()}</span>
                <span class="bull-source">${b.source}</span>
                <span class="bull-msg">${b.message}</span>
            </div>`).join('');
    }
    // Push as notification banners (deduped — won't re-show same alert)
    for (const b of d) {
        _showNotifBanner(b.level, b.source, b.message);
    }
    // Log critical bulletins
    d.filter(b => b.level === 'critical').forEach(b => appendLog(`[ALERT] ${b.source}: ${b.message}`, 'error'));
}

// ── Agent Overview ───────────────────────────────────────────────
async function refreshAgents() {
    const d = await api('/api/agents');
    const el = document.getElementById('agent-grid');
    if (!d || d.length === 0) { el.innerHTML = '<div class="feed-empty">No agents registered.</div>'; return; }
    if (el) el.innerHTML = d.map(a => {
        const statusCls = a.status || 'unknown';
        const heartbeat = a.last_heartbeat
            ? `Last heartbeat: ${new Date(a.last_heartbeat).toLocaleTimeString('en-GB')}${a.stale_minutes ? ` (${a.stale_minutes}m ago)` : ''}`
            : 'No heartbeat received';
        const urlAttr = a.url ? `data-url="${a.url}"` : '';
        return `<div class="agent-card" ${urlAttr} onclick="openAgentUrl(this)">
            <div class="agent-card-header">
                <span class="agent-name">${a.name}</span>
                <span class="agent-status-dot ${statusCls}">${statusCls.toUpperCase()}</span>
            </div>
            <div class="agent-desc">${a.description || ''}</div>
            <div class="agent-metrics">
                <div><div class="agent-metric-val">${a.tasks_completed}</div><div class="agent-metric-lbl">DONE</div></div>
                <div><div class="agent-metric-val">${a.tasks_failed}</div><div class="agent-metric-lbl">FAILED</div></div>
                ${a.current_task ? `<div><div class="agent-metric-val" style="font-size:11px;color:var(--amber);">${truncate(a.current_task,20)}</div><div class="agent-metric-lbl">RUNNING</div></div>` : ''}
            </div>
            <div class="agent-heartbeat">${heartbeat}</div>
        </div>`;
    }).join('');
    const online = d.filter(a => a.status === 'online').length;
    const ds = document.getElementById('dock-agents-stat');
    if (ds) { ds.textContent = `${online}/${d.length}`; ds.className = 'dock-stat' + (online === d.length ? ' nominal' : ' caution'); }
}

function openAgentUrl(el) {
    const url = el.getAttribute('data-url');
    if (url) window.open(url, '_blank');
}

// ── AWS & GCP — 3D Wireframe Globe + Pod Status ─────────────────
// Filtered regions: EU central/west + US west/east only
const CLOUD_REGIONS = [
    // ─── GCP ───
    // US East
    { id:'gcp-us-east1',        provider:'gcp', cluster:'US East', name:'S.Carolina',  lat:33.84, lon:-81.16 },
    { id:'gcp-us-east4',        provider:'gcp', cluster:'US East', name:'Virginia',    lat:38.77, lon:-78.17 },
    { id:'gcp-us-east5',        provider:'gcp', cluster:'US East', name:'Columbus',    lat:39.96, lon:-82.99 },
    // US West
    { id:'gcp-us-west1',        provider:'gcp', cluster:'US West', name:'Oregon',      lat:45.59, lon:-121.18 },
    { id:'gcp-us-west2',        provider:'gcp', cluster:'US West', name:'LA',          lat:34.05, lon:-118.24 },
    { id:'gcp-us-west3',        provider:'gcp', cluster:'US West', name:'SLC',         lat:40.76, lon:-111.89 },
    { id:'gcp-us-west4',        provider:'gcp', cluster:'US West', name:'Vegas',       lat:36.17, lon:-115.14 },
    // EU West
    { id:'gcp-europe-west1',    provider:'gcp', cluster:'EU West', name:'Belgium',     lat:50.85, lon:4.35 },
    { id:'gcp-europe-west2',    provider:'gcp', cluster:'EU West', name:'London',      lat:51.51, lon:-0.13 },
    { id:'gcp-europe-west3',    provider:'gcp', cluster:'EU West', name:'Frankfurt',   lat:50.11, lon:8.68 },
    { id:'gcp-europe-west4',    provider:'gcp', cluster:'EU West', name:'Netherlands', lat:53.22, lon:6.57 },
    { id:'gcp-europe-west6',    provider:'gcp', cluster:'EU West', name:'Zurich',      lat:47.37, lon:8.54 },
    { id:'gcp-europe-west8',    provider:'gcp', cluster:'EU West', name:'Milan',       lat:45.46, lon:9.19 },
    { id:'gcp-europe-west9',    provider:'gcp', cluster:'EU West', name:'Paris',       lat:48.86, lon:2.35 },
    { id:'gcp-europe-west10',   provider:'gcp', cluster:'EU West', name:'Berlin',      lat:52.52, lon:13.40 },
    { id:'gcp-europe-west12',   provider:'gcp', cluster:'EU West', name:'Turin',       lat:45.07, lon:7.69 },
    // EU Central
    { id:'gcp-europe-central2', provider:'gcp', cluster:'EU Central', name:'Warsaw',   lat:52.23, lon:21.01 },

    // ─── AWS ───
    // US East
    { id:'aws-us-east-1',       provider:'aws', cluster:'US East', name:'N.Virginia',  lat:39.05, lon:-77.46 },
    { id:'aws-us-east-2',       provider:'aws', cluster:'US East', name:'Ohio',        lat:40.42, lon:-82.91 },
    // US West
    { id:'aws-us-west-1',       provider:'aws', cluster:'US West', name:'N.California',lat:37.35, lon:-121.96 },
    { id:'aws-us-west-2',       provider:'aws', cluster:'US West', name:'Oregon',      lat:44.05, lon:-123.09 },
    // EU West
    { id:'aws-eu-west-1',       provider:'aws', cluster:'EU West', name:'Ireland',     lat:53.35, lon:-6.26 },
    { id:'aws-eu-west-2',       provider:'aws', cluster:'EU West', name:'London',      lat:51.52, lon:-0.08 },
    { id:'aws-eu-west-3',       provider:'aws', cluster:'EU West', name:'Paris',       lat:48.85, lon:2.40 },
    // EU Central
    { id:'aws-eu-central-1',    provider:'aws', cluster:'EU Central', name:'Frankfurt',lat:50.12, lon:8.73 },
    { id:'aws-eu-central-2',    provider:'aws', cluster:'EU Central', name:'Zurich',   lat:47.38, lon:8.58 },
];

// Cluster center coordinates for zoom targeting
const CLUSTER_CENTERS = {
    'US East':    { lat: 37.5, lon: -80.5 },
    'US West':    { lat: 39.0, lon: -118.0 },
    'EU West':    { lat: 50.0, lon: 4.0 },
    'EU Central': { lat: 50.0, lon: 15.0 },
};

// Continent coastlines [lat, lon] — traced from Natural Earth reference data
const COASTLINES = [
    // ── North America (mainland) ──
    [[60,-142],[59,-139],[57,-136],[55,-133],[54,-131],[52,-128],[50,-127],[49,-125],[48,-124],[46,-124],[43,-124],[41,-124],[39,-123],[37,-122],[35,-121],[34,-119],[33,-117],[32,-117],[30,-114],[28,-112],[26,-109],[24,-108],[22,-106],[20,-105],[18,-95],[19,-91],[21,-89],[22,-86],[21,-87],[19,-88],[17,-91],[16,-91],[16,-87],[18,-88],[20,-87],[21,-86],[23,-83],[25,-80],[27,-80],[28,-81],[29,-82],[30,-84],[29,-89],[30,-89],[30,-85],[30,-82],[31,-81],[32,-80],[34,-78],[35,-76],[37,-76],[39,-75],[40,-74],[41,-72],[42,-71],[43,-70],[44,-68],[45,-67],[47,-65],[47,-61],[46,-60],[47,-59],[49,-55],[50,-57],[52,-56],[54,-58],[55,-60],[57,-64],[59,-64],[60,-64],[63,-69],[65,-74],[68,-80],[69,-85],[70,-95],[71,-105],[71,-115],[70,-125],[69,-132],[67,-137],[65,-140],[63,-143],[60,-142]],
    // ── Alaska ──
    [[60,-142],[61,-145],[62,-149],[63,-151],[64,-153],[63,-155],[62,-155],[61,-158],[60,-160],[58,-157],[57,-155],[56,-155],[55,-160],[54,-162],[54,-165],[56,-165],[57,-167],[58,-165],[60,-165],[60,-162],[61,-160],[62,-163],[64,-165],[66,-167],[68,-163],[70,-160],[71,-156],[71,-153],[70,-149],[68,-148],[66,-150],[65,-147],[64,-147],[63,-147],[62,-149]],
    // ── Central America ──
    [[18,-95],[17,-93],[16,-91],[15,-90],[15,-88],[14,-88],[13,-88],[13,-86],[12,-86],[11,-85],[10,-84],[9,-84],[9,-83],[8,-82],[8,-80],[8,-78],[7,-77]],
    // ── Greenland ──
    [[77,-72],[78,-68],[79,-60],[80,-52],[81,-46],[82,-40],[83,-34],[83,-28],[82,-22],[81,-19],[79,-17],[77,-18],[76,-19],[74,-20],[72,-22],[70,-22],[68,-29],[66,-36],[65,-40],[64,-44],[64,-48],[65,-52],[67,-54],[70,-55],[72,-56],[74,-58],[76,-64],[77,-68],[77,-72]],
    // ── South America ──
    [[12,-72],[11,-74],[10,-76],[9,-77],[8,-77],[7,-77],[5,-77],[3,-78],[1,-80],[-1,-80],[-3,-80],[-5,-79],[-7,-77],[-9,-76],[-11,-76],[-13,-77],[-15,-75],[-17,-72],[-19,-70],[-21,-70],[-23,-70],[-25,-68],[-27,-66],[-29,-64],[-31,-61],[-33,-58],[-35,-57],[-37,-57],[-39,-58],[-41,-63],[-43,-65],[-46,-67],[-49,-68],[-51,-69],[-53,-70],[-55,-68],[-54,-66],[-52,-68],[-49,-66],[-47,-64],[-44,-63],[-41,-61],[-38,-56],[-35,-53],[-33,-51],[-30,-49],[-27,-48],[-25,-46],[-23,-43],[-21,-41],[-18,-39],[-15,-39],[-13,-38],[-10,-37],[-8,-35],[-5,-35],[-3,-33],[-1,-30],[1,-30],[2,-35],[1,-40],[1,-44],[2,-48],[4,-52],[6,-56],[7,-60],[9,-62],[10,-67],[11,-69],[12,-72]],
    // ── Europe (Iberia → Scandinavia) ──
    [[36,-6],[37,-2],[38,0],[39,0],[40,-1],[42,-2],[43,-2],[43,0],[43,3],[43,6],[44,8],[45,7],[46,6],[47,6],[48,2],[49,0],[49,-2],[50,-5],[51,-5],[52,-4],[52,-1],[53,1],[53,4],[54,6],[55,8],[56,8],[57,10],[57,12],[56,12],[55,10],[55,12],[56,15],[58,11],[59,10],[60,5],[61,4],[62,5],[63,5],[64,10],[66,14],[68,16],[70,20],[71,25],[71,28],[70,31],[69,30],[67,28],[65,25],[63,22],[61,22],[60,24],[61,25],[63,27],[65,29],[67,32],[66,34],[64,30],[62,28],[61,28],[60,24],[59,22],[57,18],[56,17],[55,17],[54,18],[54,21],[53,21],[52,21],[51,22],[50,20],[49,17],[48,15],[47,14],[46,14],[46,16],[45,14],[44,12],[43,12],[42,13],[41,17],[40,19],[39,20],[38,24],[37,24],[36,22],[36,19],[38,18],[40,20],[40,18],[39,15],[38,12],[37,8],[37,4],[36,0],[36,-6]],
    // ── Great Britain ──
    [[50,-5],[50,-4],[51,-3],[51,-1],[52,0],[52,1],[53,1],[53,0],[54,-1],[55,-2],[56,-3],[57,-2],[58,-3],[58,-5],[58,-7],[57,-7],[56,-6],[55,-7],[55,-6],[54,-5],[54,-6],[53,-6],[53,-9],[54,-10],[55,-8],[56,-6],[57,-6],[58,-5],[58,-7],[57,-7],[56,-7],[55,-8],[54,-8],[53,-10],[52,-8],[52,-6],[51,-5],[50,-5]],
    // ── Ireland ──
    [[52,-6],[52,-7],[52,-9],[53,-10],[54,-10],[55,-8],[55,-7],[54,-6],[53,-6],[52,-6]],
    // ── Africa ──
    [[37,10],[36,11],[35,10],[34,10],[33,10],[32,10],[33,8],[34,2],[35,0],[35,-2],[36,-6],[35,-6],[34,-2],[33,-5],[32,-7],[31,-10],[29,-13],[27,-15],[25,-17],[22,-17],[20,-17],[18,-16],[15,-17],[13,-17],[12,-16],[10,-15],[8,-13],[6,-11],[5,-8],[5,-4],[5,0],[6,1],[5,2],[4,5],[3,10],[1,10],[0,10],[-1,9],[-3,11],[-5,12],[-7,13],[-10,14],[-12,15],[-15,17],[-17,17],[-19,14],[-22,14],[-25,15],[-28,17],[-30,18],[-32,18],[-34,19],[-34,22],[-34,26],[-33,28],[-31,30],[-29,32],[-27,33],[-25,35],[-22,36],[-19,36],[-17,38],[-15,40],[-12,42],[-10,42],[-8,44],[-5,42],[-3,41],[-1,42],[1,43],[3,44],[5,44],[8,46],[10,49],[12,50],[12,45],[14,42],[16,40],[18,40],[20,40],[22,38],[24,38],[26,36],[28,34],[30,33],[32,32],[34,32],[36,28],[37,22],[37,15],[37,10]],
    // ── Middle East ──
    [[32,32],[34,36],[36,36],[38,40],[40,42],[38,44],[36,44],[34,48],[32,48],[30,48],[28,49],[26,50],[24,52],[22,55],[20,57],[18,56],[16,52],[14,48],[14,44],[13,44],[12,44],[12,46],[14,48],[16,52],[18,56],[16,53],[15,49],[14,44],[13,43],[12,43]],
    // ── India + SE Asia ──
    [[30,70],[32,74],[34,74],[34,78],[30,80],[28,78],[24,76],[22,76],[20,73],[18,76],[15,78],[13,78],[11,80],[10,80],[8,77],[8,76],[10,76],[12,74],[14,72],[14,68],[12,70],[10,76],[8,78],[8,80],[10,92],[13,98],[15,100],[17,102],[18,105],[19,105],[20,106],[21,108],[20,108],[18,107],[16,108],[14,109],[12,110],[10,106],[8,105],[4,104],[2,103],[0,104],[-2,106],[-4,106],[-6,105]],
    // ── China + East Asia ──
    [[40,74],[42,75],[44,80],[46,82],[48,87],[50,87],[52,90],[50,95],[48,100],[46,100],[44,98],[42,92],[40,88],[38,84],[36,80],[34,78],[34,74],[30,70],[30,74],[32,77],[35,78],[38,80],[40,82],[42,87],[44,92],[42,98],[40,100],[38,102],[36,104],[34,107],[32,108],[30,110],[28,109],[26,108],[24,108],[22,108],[22,114],[24,116],[28,118],[30,121],[32,122],[34,120],[36,124],[38,125],[38,128],[36,128],[34,130],[36,132],[38,134],[40,132],[42,132],[44,135],[46,142],[48,143],[50,143],[52,140],[54,140],[56,138],[58,135],[60,130],[62,128],[64,126],[66,120],[68,112],[70,105],[72,100],[72,90],[70,82],[68,72],[66,65],[64,60],[62,55],[60,50],[58,48],[56,44],[54,42],[52,40],[50,38],[48,35],[46,34],[44,32],[42,30],[42,32],[44,35],[46,38],[48,42],[50,48],[52,55],[54,58],[56,62],[56,68],[54,72],[52,74],[50,78],[48,82],[46,82],[44,80],[42,75]],
    // ── Japan ──
    [[31,131],[33,132],[34,132],[35,134],[36,136],[37,137],[38,139],[40,140],[41,141],[43,142],[44,144],[46,143],[44,142],[43,141],[42,140],[40,139],[38,137],[36,134],[34,132],[33,131],[31,131]],
    // ── Korean Peninsula ──
    [[35,126],[36,127],[37,127],[38,127],[38,128],[39,128],[40,127],[42,128],[42,130],[41,130],[39,128],[38,128],[37,126],[36,126],[35,126]],
    // ── Australia ──
    [[-12,131],[-12,134],[-14,136],[-16,138],[-18,141],[-20,144],[-23,148],[-26,150],[-28,153],[-30,153],[-33,152],[-35,151],[-37,149],[-38,146],[-38,144],[-37,140],[-36,137],[-35,136],[-34,135],[-33,134],[-32,133],[-32,131],[-33,129],[-34,128],[-34,124],[-33,121],[-32,118],[-30,115],[-28,114],[-26,113],[-24,114],[-22,114],[-20,118],[-18,122],[-16,124],[-14,127],[-12,131]],
    // ── Tasmania ──
    [[-41,144],[-42,145],[-43,147],[-44,147],[-43,148],[-42,148],[-41,146],[-41,144]],
    // ── New Zealand ──
    [[-35,174],[-37,175],[-38,177],[-40,176],[-42,174],[-44,170],[-46,167],[-46,166],[-44,168],[-42,172],[-40,174],[-38,174],[-36,174],[-35,174]],
    // ── Iceland ──
    [[66,-16],[66,-14],[65,-13],[64,-14],[63,-18],[63,-22],[64,-24],[65,-23],[66,-21],[66,-18],[66,-16]],
    // ── Sri Lanka ──
    [[10,80],[8,80],[7,80],[6,81],[7,82],[9,81],[10,80]],
    // ── Borneo ──
    [[7,117],[5,118],[3,118],[1,117],[0,115],[-1,112],[-2,110],[-1,109],[0,109],[1,110],[2,111],[4,115],[5,116],[7,117]],
    // ── Sumatra ──
    [[5,95],[4,98],[2,101],[0,103],[-1,104],[-3,105],[-5,105],[-6,106],[-5,104],[-3,103],[-1,101],[1,99],[3,97],[5,95]],
    // ── Java ──
    [[-6,106],[-7,107],[-7,110],[-8,112],[-8,114],[-7,114],[-6,112],[-6,109],[-6,106]],
    // ── Philippines (Luzon+) ──
    [[18,121],[17,120],[15,120],[14,121],[13,122],[12,124],[13,124],[15,122],[16,121],[18,121]],
    // ── Madagascar ──
    [[-12,49],[-14,48],[-16,46],[-18,44],[-20,44],[-23,44],[-25,47],[-25,49],[-23,49],[-20,49],[-17,50],[-14,50],[-12,49]],
    // ── Italy (boot) ──
    [[44,8],[44,10],[43,11],[42,12],[41,14],[40,16],[40,18],[39,17],[38,16],[38,15],[39,15],[40,16],[40,14],[39,12],[38,13],[37,15],[36,15],[37,13],[38,12],[38,10],[39,9],[40,9],[41,9],[42,9],[43,8],[44,8]],
    // ── Sicily ──
    [[38,13],[37,14],[37,15],[38,15],[38,13]],
    // ── Iberian Peninsula (Spain+Portugal) ──
    [[43,-2],[43,-8],[42,-9],[40,-9],[39,-9],[38,-9],[37,-8],[36,-6],[36,-5],[37,-2],[38,0],[39,0],[40,-1],[42,-2],[43,-2]],
    // ── Scandinavia (Norway/Sweden) ──
    [[58,8],[59,6],[60,5],[61,4],[62,5],[63,5],[64,10],[65,14],[67,15],[68,16],[70,20],[71,25],[71,28],[70,31],[69,29],[68,28],[67,26],[66,24],[64,20],[63,18],[62,16],[60,12],[59,10],[58,8]],
];

// ── Globe Renderer ──────────────────────────────────────────────
let gcpGlobe = null;

// Traffic source cities — real-world locations that send traffic to our DCs
const TRAFFIC_SOURCES = [
    { lat:35.68, lon:139.69, label:'Tokyo' },
    { lat:-33.87, lon:151.21, label:'Sydney' },
    { lat:19.08, lon:72.88, label:'Mumbai' },
    { lat:55.76, lon:37.62, label:'Moscow' },
    { lat:-23.55, lon:-46.63, label:'São Paulo' },
    { lat:1.35, lon:103.82, label:'Singapore' },
    { lat:37.57, lon:126.98, label:'Seoul' },
    { lat:25.20, lon:55.27, label:'Dubai' },
    { lat:-1.29, lon:36.82, label:'Nairobi' },
    { lat:49.28, lon:-123.12, label:'Vancouver' },
    { lat:41.90, lon:12.50, label:'Rome' },
    { lat:59.33, lon:18.07, label:'Stockholm' },
    { lat:30.04, lon:31.24, label:'Cairo' },
    { lat:34.05, lon:-118.24, label:'Los Angeles' },
    { lat:40.71, lon:-74.01, label:'New York' },
    { lat:22.32, lon:114.17, label:'Hong Kong' },
    { lat:43.65, lon:-79.38, label:'Toronto' },
    { lat:48.86, lon:2.35, label:'Paris' },
];

// Key datacenter targets for traffic arcs (subset of CLOUD_REGIONS)
const TRAFFIC_TARGETS = [
    { lat:51.51, lon:-0.13 },   // London
    { lat:38.77, lon:-78.17 },  // Virginia
    { lat:45.59, lon:-121.18 }, // Oregon
    { lat:50.11, lon:8.68 },    // Frankfurt
];

class GlobeRenderer {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.dpr = window.devicePixelRatio || 1;
        this.rotation = -0.2;
        this.tilt = 0.3;
        this.markers = [];
        this.time = 0;
        this.W = 0; this.H = 0;
        this._raf = null;
        this.autoSpin = true;
        this._radarAngle = 0;
        this._radarActive = false;
        this._radarAlpha = 0;
        // Traffic arcs — pre-generate many source→target pairings for dense network look
        this._trafficArcs = [];
        for (let i = 0; i < 48; i++) {
            const src = TRAFFIC_SOURCES[i % TRAFFIC_SOURCES.length];
            const tgt = TRAFFIC_TARGETS[i % TRAFFIC_TARGETS.length];
            this._trafficArcs.push({
                srcLat: src.lat, srcLon: src.lon,
                tgtLat: tgt.lat, tgtLon: tgt.lon,
                phase: Math.random() * Math.PI * 2,
                speed: 0.8 + Math.random() * 1.2,
                arcHeight: 0.12 + Math.random() * 0.18,
            });
        }
        // Load real Natural Earth land polygons
        this._landPolygons = []; // array of arrays of [lon, lat] rings
        this._loadLandData();
    }

    async _loadLandData() {
        try {
            // Use countries dataset for individual country polygons (better detail)
            const resp = await fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json');
            const topo = await resp.json();
            if (typeof topojson === 'undefined') return;

            // Extract polygons from all available objects
            const polys = [];
            const extractGeom = (geom) => {
                if (!geom) return;
                if (geom.type === 'Polygon') {
                    // Only take exterior ring (index 0), skip holes
                    polys.push(geom.coordinates[0]);
                } else if (geom.type === 'MultiPolygon') {
                    geom.coordinates.forEach(polygon => polys.push(polygon[0]));
                }
            };

            // Try countries first (FeatureCollection), then land (single Feature)
            for (const key of Object.keys(topo.objects)) {
                const geo = topojson.feature(topo, topo.objects[key]);
                if (geo.type === 'FeatureCollection') {
                    geo.features.forEach(f => extractGeom(f.geometry));
                } else if (geo.type === 'Feature') {
                    extractGeom(geo.geometry);
                } else {
                    // Bare geometry
                    extractGeom(geo);
                }
            }

            this._landPolygons = polys;
            console.log(`[Globe] Loaded ${polys.length} land polygons from Natural Earth`);
        } catch(e) {
            console.warn('[Globe] Failed to load Natural Earth data, falling back to COASTLINES', e);
        }
    }

    setMarkers(m) { this.markers = m; }

    triggerScan() {
        this._radarActive = true;
        this._radarAlpha = 0.7;
    }

    _resize() {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        const w = rect.width;
        const h = Math.round(w * 0.8);
        if (w < 10) return; // skip resize when hidden (display:none returns 0)
        if (w === this.W && h === this.H) return;
        this.canvas.width = w * this.dpr;
        this.canvas.height = h * this.dpr;
        this.canvas.style.width = w + 'px';
        this.canvas.style.height = h + 'px';
        this.W = w; this.H = h;
    }

    _project(lat, lon) {
        const phi = lat * Math.PI / 180;
        const theta = -lon * Math.PI / 180; // negate to flip east/west
        let x = Math.cos(phi) * Math.cos(theta);
        let y = Math.sin(phi);
        let z = Math.cos(phi) * Math.sin(theta);
        const cr = Math.cos(this.rotation), sr = Math.sin(this.rotation);
        const x1 = x * cr + z * sr, z1 = -x * sr + z * cr;
        const ct = Math.cos(this.tilt), st = Math.sin(this.tilt);
        const y1 = y * ct - z1 * st, z2 = y * st + z1 * ct;
        const radius = Math.min(this.W, this.H) * 0.40;
        return { x: this.W / 2 + x1 * radius, y: this.H / 2 - y1 * radius, z: z2, vis: z2 > -0.05 };
    }

    // Interpolate lat/lon along a great circle with altitude offset for arc
    _arcPoint(srcLat, srcLon, tgtLat, tgtLon, t, arcH) {
        const toRad = Math.PI / 180;
        const p1 = srcLat * toRad, l1 = srcLon * toRad;
        const p2 = tgtLat * toRad, l2 = tgtLon * toRad;
        // Spherical interpolation
        const d = Math.acos(
            Math.sin(p1) * Math.sin(p2) + Math.cos(p1) * Math.cos(p2) * Math.cos(l2 - l1)
        ) || 0.001;
        const A = Math.sin((1 - t) * d) / Math.sin(d);
        const B = Math.sin(t * d) / Math.sin(d);
        const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2);
        const y = A * Math.sin(p1) + B * Math.sin(p2);
        const z = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2);
        // Add arc height (push outward from sphere center)
        const alt = 1 + arcH * Math.sin(t * Math.PI); // parabolic arc
        const lat = Math.atan2(y, Math.sqrt(x * x + z * z)) / toRad;
        const lon = Math.atan2(z, x) / toRad;
        // Project with altitude scaling
        const proj = this._project(lat, lon);
        const cx = this.W / 2, cy = this.H / 2;
        proj.x = cx + (proj.x - cx) * alt;
        proj.y = cy + (proj.y - cy) * alt;
        return proj;
    }

    _draw() {
        this._resize();
        const ctx = this.ctx;
        ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
        this.time += 0.016;
        if (this.autoSpin) this.rotation += 0.003;
        const W = this.W, H = this.H;
        const cx = W / 2, cy = H / 2;
        const R = Math.min(W, H) * 0.40;

        // Clear — transparent to let parent bg show through
        ctx.clearRect(0, 0, W, H);

        // Outer atmosphere haze
        const ag2 = ctx.createRadialGradient(cx, cy, R * 0.9, cx, cy, R * 1.6);
        ag2.addColorStop(0, 'rgba(0,200,255,0.05)');
        ag2.addColorStop(0.4, 'rgba(0,150,255,0.02)');
        ag2.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = ag2;
        ctx.beginPath(); ctx.arc(cx, cy, R * 1.6, 0, Math.PI * 2); ctx.fill();

        // Inner glow
        const ag = ctx.createRadialGradient(cx, cy, R * 0.85, cx, cy, R * 1.15);
        ag.addColorStop(0, 'rgba(0,200,255,0.07)');
        ag.addColorStop(0.6, 'rgba(0,200,255,0.025)');
        ag.addColorStop(1, 'rgba(0,200,255,0)');
        ctx.fillStyle = ag;
        ctx.beginPath(); ctx.arc(cx, cy, R * 1.15, 0, Math.PI * 2); ctx.fill();

        // Globe body — lighter deep ocean blue
        const bodyGrad = ctx.createRadialGradient(cx - R * 0.25, cy - R * 0.25, R * 0.1, cx, cy, R);
        bodyGrad.addColorStop(0, 'rgba(12,35,65,0.55)');
        bodyGrad.addColorStop(0.7, 'rgba(6,18,40,0.7)');
        bodyGrad.addColorStop(1, 'rgba(2,8,22,0.85)');
        ctx.fillStyle = bodyGrad;
        ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();

        // Globe edge ring — brighter
        ctx.strokeStyle = 'rgba(60,220,255,0.35)';
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
        ctx.strokeStyle = 'rgba(60,220,255,0.08)';
        ctx.lineWidth = 4;
        ctx.beginPath(); ctx.arc(cx, cy, R + 3, 0, Math.PI * 2); ctx.stroke();

        // Orbital ring
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(this.time * 0.12);
        ctx.scale(1, 0.22);
        ctx.strokeStyle = `rgba(0,200,255,${0.06 + Math.sin(this.time) * 0.03})`;
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(0, 0, R * 1.3, 0, Math.PI * 2); ctx.stroke();
        const sx = Math.cos(this.time * 0.7) * R * 1.3;
        const sy = Math.sin(this.time * 0.7) * R * 1.3;
        ctx.fillStyle = 'rgba(0,255,200,0.6)';
        ctx.beginPath(); ctx.arc(sx, sy, 2, 0, Math.PI * 2); ctx.fill();
        ctx.restore();

        // Latitude grid — subtle dotted lines
        for (let lat = -60; lat <= 60; lat += 30) {
            const isEq = lat === 0;
            ctx.strokeStyle = isEq ? 'rgba(60,220,255,0.18)' : 'rgba(60,220,255,0.05)';
            ctx.lineWidth = isEq ? 0.8 : 0.4;
            if (!isEq) ctx.setLineDash([2, 6]);
            ctx.beginPath();
            let started = false;
            for (let lon = -180; lon <= 180; lon += 3) {
                const p = this._project(lat, lon);
                if (p.vis && p.z > 0) { if (!started) { ctx.moveTo(p.x, p.y); started = true; } else ctx.lineTo(p.x, p.y); }
                else started = false;
            }
            ctx.stroke();
            ctx.setLineDash([]);
        }
        // Longitude grid
        for (let lon = -180; lon < 180; lon += 30) {
            const isPrime = lon === 0;
            ctx.strokeStyle = isPrime ? 'rgba(60,220,255,0.18)' : 'rgba(60,220,255,0.05)';
            ctx.lineWidth = isPrime ? 0.8 : 0.4;
            if (!isPrime) ctx.setLineDash([2, 6]);
            ctx.beginPath();
            let started = false;
            for (let lat = -90; lat <= 90; lat += 3) {
                const p = this._project(lat, lon);
                if (p.vis && p.z > 0) { if (!started) { ctx.moveTo(p.x, p.y); started = true; } else ctx.lineTo(p.x, p.y); }
                else started = false;
            }
            ctx.stroke();
            ctx.setLineDash([]);
        }

        // ── Helper: extract contiguous visible segments from a point array ──
        const getVisibleSegments = (pts) => {
            const segments = [];
            let current = [];
            for (const p of pts) {
                if (p.z > 0) {
                    current.push(p);
                } else {
                    if (current.length >= 2) segments.push(current);
                    current = [];
                }
            }
            if (current.length >= 2) segments.push(current);
            return segments;
        };

        // ── Render land polygons ──
        const landRings = this._landPolygons.length > 0 ? this._landPolygons : null;

        ctx.save();
        ctx.beginPath(); ctx.arc(cx, cy, R - 1, 0, Math.PI * 2); ctx.clip();

        if (landRings) {
            // ── Real Natural Earth land polygons ──
            landRings.forEach(ring => {
                // GeoJSON coords are [lon, lat]
                const pts = ring.map(c => this._project(c[1], c[0]));
                const segments = getVisibleSegments(pts);
                if (segments.length === 0) return;

                // Fill each visible segment as a closed polygon
                ctx.fillStyle = 'rgba(15,65,105,0.40)';
                segments.forEach(seg => {
                    if (seg.length < 3) return;
                    ctx.beginPath();
                    ctx.moveTo(seg[0].x, seg[0].y);
                    for (let i = 1; i < seg.length; i++) ctx.lineTo(seg[i].x, seg[i].y);
                    ctx.closePath();
                    ctx.fill();
                });
            });

            // Pass 2: wireframe outlines
            landRings.forEach(ring => {
                const pts = ring.map(c => this._project(c[1], c[0]));
                const segments = getVisibleSegments(pts);
                if (segments.length === 0) return;

                segments.forEach(seg => {
                    // Outer glow
                    ctx.strokeStyle = 'rgba(40,200,255,0.12)';
                    ctx.lineWidth = 2.5;
                    ctx.beginPath();
                    ctx.moveTo(seg[0].x, seg[0].y);
                    for (let i = 1; i < seg.length; i++) ctx.lineTo(seg[i].x, seg[i].y);
                    ctx.stroke();

                    // Bright edge
                    ctx.strokeStyle = 'rgba(60,220,255,0.55)';
                    ctx.lineWidth = 0.8;
                    ctx.beginPath();
                    ctx.moveTo(seg[0].x, seg[0].y);
                    for (let i = 1; i < seg.length; i++) ctx.lineTo(seg[i].x, seg[i].y);
                    ctx.stroke();
                });
            });
        } else {
            // ── Fallback: hand-traced COASTLINES ──
            COASTLINES.forEach(coast => {
                const pts = coast.map(c => this._project(c[0], c[1]));
                const segments = getVisibleSegments(pts);
                if (segments.length === 0) return;

                ctx.fillStyle = 'rgba(15,60,100,0.35)';
                segments.forEach(seg => {
                    if (seg.length < 3) return;
                    ctx.beginPath();
                    ctx.moveTo(seg[0].x, seg[0].y);
                    for (let i = 1; i < seg.length; i++) ctx.lineTo(seg[i].x, seg[i].y);
                    ctx.closePath();
                    ctx.fill();
                });

                segments.forEach(seg => {
                    ctx.strokeStyle = 'rgba(60,220,255,0.6)';
                    ctx.lineWidth = 1.0;
                    ctx.beginPath();
                    ctx.moveTo(seg[0].x, seg[0].y);
                    for (let i = 1; i < seg.length; i++) ctx.lineTo(seg[i].x, seg[i].y);
                    ctx.stroke();
                });
            });
        }

        ctx.restore(); // un-clip

        // ── Traffic arcs — smooth animated curves from cities to datacenters ──
        this._trafficArcs.forEach(arc => {
            // Faster looping — speed multiplier increased
            const rawT = ((this.time * arc.speed * 1.2 + arc.phase) % 4.0) / 4.0;
            // Smoothstep for seamless motion
            const t = rawT * rawT * (3 - 2 * rawT);

            const segments = 40; // more segments = smoother curve
            const points = [];
            let allVis = true;
            for (let s = 0; s <= segments; s++) {
                const st2 = s / segments;
                const pt = this._arcPoint(arc.srcLat, arc.srcLon, arc.tgtLat, arc.tgtLon, st2, arc.arcHeight);
                points.push(pt);
                if (!pt.vis || pt.z < 0) allVis = false;
            }
            if (!allVis || points.length < 2) return;

            // Full arc path — very subtle base
            ctx.beginPath();
            ctx.moveTo(points[0].x, points[0].y);
            for (let s = 1; s < points.length; s++) ctx.lineTo(points[s].x, points[s].y);
            ctx.strokeStyle = 'rgba(0,160,255,0.05)';
            ctx.lineWidth = 0.6;
            ctx.stroke();

            // Smooth interpolated packet position (sub-segment precision)
            const exactPos = t * segments;
            const idx = Math.floor(exactPos);
            const frac = exactPos - idx;
            const trailLen = 8;

            // Trailing glow segments
            for (let s = Math.max(0, idx - trailLen); s <= Math.min(segments - 1, idx); s++) {
                const distBehind = idx - s + (1 - frac);
                const alpha = Math.max(0, 1 - distBehind / trailLen) * 0.3;
                ctx.beginPath();
                ctx.moveTo(points[s].x, points[s].y);
                ctx.lineTo(points[s + 1].x, points[s + 1].y);
                ctx.strokeStyle = `rgba(0,160,255,${alpha})`;
                ctx.lineWidth = 1.0;
                ctx.stroke();
            }

            // Packet dot — blue, smoothly interpolated between segment points
            if (idx >= 0 && idx < points.length - 1) {
                const p0 = points[idx], p1 = points[idx + 1];
                const pkX = p0.x + (p1.x - p0.x) * frac;
                const pkY = p0.y + (p1.y - p0.y) * frac;
                ctx.fillStyle = 'rgba(0,160,255,0.85)';
                ctx.beginPath(); ctx.arc(pkX, pkY, 1.6, 0, Math.PI * 2); ctx.fill();
                const pkGrad = ctx.createRadialGradient(pkX, pkY, 0, pkX, pkY, 5);
                pkGrad.addColorStop(0, 'rgba(0,160,255,0.25)');
                pkGrad.addColorStop(1, 'rgba(0,160,255,0)');
                ctx.fillStyle = pkGrad;
                ctx.beginPath(); ctx.arc(pkX, pkY, 5, 0, Math.PI * 2); ctx.fill();
            }
        });

        // HUD scan line
        const scanY = cy + R * Math.sin(this.time * 0.4) * 0.9;
        ctx.save();
        ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.clip();
        const scanGrad = ctx.createLinearGradient(cx - R, scanY - 4, cx + R, scanY + 4);
        scanGrad.addColorStop(0, 'rgba(0,200,255,0)');
        scanGrad.addColorStop(0.3, 'rgba(0,200,255,0.04)');
        scanGrad.addColorStop(0.5, 'rgba(0,255,200,0.08)');
        scanGrad.addColorStop(0.7, 'rgba(0,200,255,0.04)');
        scanGrad.addColorStop(1, 'rgba(0,200,255,0)');
        ctx.fillStyle = scanGrad;
        ctx.fillRect(cx - R, scanY - 4, R * 2, 8);
        ctx.restore();

        // ── Datacenter markers — sort by depth ──
        const projected = this.markers.map((m, i) => ({ ...m, ...this._project(m.lat, m.lon), i }))
            .filter(m => m.vis && m.z > 0)
            .sort((a, b) => a.z - b.z);

        const PROVIDER_TINT = {
            gcp: { r:66, g:133, b:244 },
            aws: { r:255, g:153, b:0 },
        };

        projected.forEach(m => {
            const statusColors = {
                online:   { r:0, g:255, b:136 },
                degraded: { r:255, g:170, b:0 },
                offline:  { r:255, g:51, b:85 },
            };
            const sc = statusColors[m.status] || statusColors.online;
            const pc = PROVIDER_TINT[m.provider] || PROVIDER_TINT.gcp;
            const pulse = Math.sin(this.time * 2.5 + m.i * 0.6) * 0.3 + 0.7;
            const depth = Math.min(1, 0.3 + m.z * 0.7);
            const isAws = m.provider === 'aws';

            // Glow halo
            const gr = 12 + pulse * 6;
            const grad = ctx.createRadialGradient(m.x, m.y, 0, m.x, m.y, gr);
            grad.addColorStop(0, `rgba(${sc.r},${sc.g},${sc.b},${0.4 * depth})`);
            grad.addColorStop(0.5, `rgba(${sc.r},${sc.g},${sc.b},${0.12 * depth})`);
            grad.addColorStop(1, `rgba(${sc.r},${sc.g},${sc.b},0)`);
            ctx.fillStyle = grad;
            ctx.beginPath(); ctx.arc(m.x, m.y, gr, 0, Math.PI * 2); ctx.fill();

            // Provider ring
            ctx.strokeStyle = `rgba(${pc.r},${pc.g},${pc.b},${0.3 * depth})`;
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.arc(m.x, m.y, 8, 0, Math.PI * 2); ctx.stroke();

            // Pulsing ring for degraded/offline
            if (m.status !== 'online') {
                ctx.strokeStyle = `rgba(${sc.r},${sc.g},${sc.b},${0.3 * depth})`;
                ctx.lineWidth = 0.7;
                ctx.beginPath();
                ctx.arc(m.x, m.y, 7 + Math.sin(this.time * 2 + m.i) * 3, 0, Math.PI * 2);
                ctx.stroke();
            }

            // Marker dot
            const dotR = 3.5 + depth * 1.5;
            ctx.fillStyle = `rgba(${sc.r},${sc.g},${sc.b},${(0.7 + pulse * 0.3) * depth})`;
            if (isAws) {
                ctx.beginPath();
                ctx.moveTo(m.x, m.y - dotR * 1.2);
                ctx.lineTo(m.x + dotR, m.y);
                ctx.lineTo(m.x, m.y + dotR * 1.2);
                ctx.lineTo(m.x - dotR, m.y);
                ctx.closePath(); ctx.fill();
            } else {
                ctx.beginPath(); ctx.arc(m.x, m.y, dotR, 0, Math.PI * 2); ctx.fill();
            }
            // Bright centre
            ctx.fillStyle = `rgba(255,255,255,${0.5 * depth})`;
            ctx.beginPath(); ctx.arc(m.x, m.y, dotR * 0.3, 0, Math.PI * 2); ctx.fill();
        });

        // Corner HUD brackets
        const cm = 16;
        ctx.strokeStyle = 'rgba(0,200,255,0.10)';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(0, cm); ctx.lineTo(0, 0); ctx.lineTo(cm, 0); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(W - cm, 0); ctx.lineTo(W, 0); ctx.lineTo(W, cm); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(0, H - cm); ctx.lineTo(0, H); ctx.lineTo(cm, H); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(W - cm, H); ctx.lineTo(W, H); ctx.lineTo(W, H - cm); ctx.stroke();

        this._raf = requestAnimationFrame(() => this._draw());
    }

    start() { if (!this._raf) this._draw(); }
    stop()  { if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; } }
}

// ── refreshGCP — fetch status + update globe + pods ─────────────
async function refreshGCP() {
    const d = await api('/api/gcp/summary');

    // Build globe markers — merge GCP + AWS status
    const gcpStatus = d?.region_status || {};
    const awsStatus = d?.aws_status || {};
    const markers = CLOUD_REGIONS.map(r => {
        const lookup = r.provider === 'aws' ? awsStatus : gcpStatus;
        // Strip provider prefix for backend lookup (gcp-europe-west1 → europe-west1)
        const backendId = r.id.replace(/^(gcp|aws)-/, '');
        return { ...r, status: lookup[backendId] || 'online' };
    });

    // Init globe if needed
    if (!gcpGlobe) {
        const canvas = document.getElementById('gcp-map-canvas');
        if (canvas) {
            gcpGlobe = new GlobeRenderer(canvas);
            gcpGlobe.setMarkers(markers);
            gcpGlobe.start();
        }
    } else {
        gcpGlobe.setMarkers(markers);
    }

    // Region legend — separated by provider (AWS / GCP)
    const legend = document.getElementById('gcp-region-legend');
    if (legend) {
        const clusters = ['US East', 'US West', 'EU West', 'EU Central'];
        const providers = [
            { key: 'gcp', label: 'GCP', cls: 'gcp' },
            { key: 'aws', label: 'AWS', cls: 'aws' },
        ];
        let html = '';
        providers.forEach(prov => {
            let tagsHtml = '';
            clusters.forEach(cl => {
                const clMarkers = markers.filter(m => m.provider === prov.key && m.cluster === cl);
                if (clMarkers.length === 0) return;
                const clUp = clMarkers.every(m => m.status === 'online');
                const clAllDown = clMarkers.every(m => m.status !== 'online');
                const clBoxCls = clUp ? 'status-box-green' : (clAllDown ? 'status-box-red' : 'status-box-amber');
                tagsHtml += `<span class="region-tag"><span class="status-box ${clBoxCls}"></span>${cl}</span>`;
            });
            if (tagsHtml) {
                html += `<div class="legend-provider">
                    <span class="legend-provider-label ${prov.cls}">${prov.label}</span>
                    <div class="legend-clusters">${tagsHtml}</div>
                </div>`;
            }
        });
        legend.innerHTML = html;
    }
}

// ── RevenueCat ───────────────────────────────────────────────────
let revenueChart = null;

async function refreshRevenue() {
    const d = await api('/api/revenue/summary');
    if (!d || !d.configured) return;
    const ov = d.overview || {};

    document.getElementById('rc-subs').textContent = ov.active_subscribers || 0;
    document.getElementById('rc-trials').textContent = ov.active_trials || 0;
    document.getElementById('rc-mrr').textContent = ov.mrr ? `$${Number(ov.mrr).toFixed(0)}` : '—';
    document.getElementById('rc-revenue').textContent = ov.revenue ? `$${Number(ov.revenue).toFixed(0)}` : '—';
    document.getElementById('rc-new').textContent = ov.new_customers || 0;
    document.getElementById('rc-churn').textContent = ov.churned_subscribers || 0;
    // Dock stats
    const drmrr = document.getElementById('dock-rev-mrr');
    const drsubs = document.getElementById('dock-rev-subs');
    if (drmrr) drmrr.textContent = ov.mrr ? `$${Number(ov.mrr).toFixed(0)}` : '—';
    if (drsubs) drsubs.textContent = ov.active_subscribers || 0;

    // Revenue Summary Bar
    const setSum = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    setSum('rsum-mrr', ov.mrr ? `$${Number(ov.mrr).toLocaleString('en-US', {minimumFractionDigits:0, maximumFractionDigits:0})}` : '—');
    setSum('rsum-revenue', ov.revenue ? `$${Number(ov.revenue).toLocaleString('en-US', {minimumFractionDigits:0, maximumFractionDigits:0})}` : '—');
    setSum('rsum-subs', ov.active_subscribers || '—');
    setSum('rsum-trials', ov.active_trials || '—');
    // Ad costs and total costs — use fields if available, otherwise show placeholder
    setSum('rsum-adcost', ov.ad_costs ? `$${Number(ov.ad_costs).toLocaleString('en-US', {minimumFractionDigits:0, maximumFractionDigits:0})}` : '$0');
    setSum('rsum-totalcost', ov.total_costs ? `$${Number(ov.total_costs).toLocaleString('en-US', {minimumFractionDigits:0, maximumFractionDigits:0})}` : '$0');

    // Revenue bar chart
    const ctx = document.getElementById('revenue-chart');
    if (ctx && typeof Chart !== 'undefined') {
        const labels = ['Subscribers', 'Trials', 'New', 'Churned'];
        const values = [ov.active_subscribers || 0, ov.active_trials || 0, ov.new_customers || 0, ov.churned_subscribers || 0];
        const colors = ['rgba(0,200,255,0.6)', 'rgba(0,255,136,0.5)', 'rgba(255,170,0,0.5)', 'rgba(255,51,85,0.5)'];
        if (revenueChart) {
            revenueChart.data.datasets[0].data = values;
            revenueChart.update('none');
        } else {
            revenueChart = new Chart(ctx, {
                type: 'bar',
                data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#6b8899', font: { size: 9, family: 'Courier New' } }, grid: { color: 'rgba(0,200,255,0.06)' } },
                        y: { ticks: { color: '#6b8899', font: { size: 9 } }, grid: { color: 'rgba(0,200,255,0.06)' }, beginAtZero: true }
                    }
                }
            });
        }
    }
}



function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '…' : (s || ''); }

// ── Service Health — Grouped by category ────────────────────────
const HEALTH_LABELS = {
    operational: 'ONLINE', degraded: 'DEGRADED',
    major_outage: 'OUTAGE', maintenance: 'MAINT', unknown: '—',
};

// Map service names → categories
const SVC_CATEGORIES = {
    'CLOUD':   ['Cloudflare', 'Google Cloud', 'AWS'],
    'AI':      ['OpenAI', 'Claude', 'OpenRouter'],
    'EMAIL':   ['Gmail', 'Outlook'],
    'GAMING':  ['Xbox Live', 'PlayStation'],
    'COMMS':   ['WhatsApp'],
    'AUTH':    ['Apple Login', 'Google Login'],
    'DEV':     ['GitHub', 'EAS Build'],
    'LOCAL':   ['ComfyUI'],
};

async function refreshServiceHealth() {
    const data = await api('/api/services/health');
    if (!Array.isArray(data)) return;
    const grid = document.getElementById('health-grid');
    if (!grid) return;

    // Build lookup by name
    const byName = {};
    data.forEach(svc => { byName[svc.name] = svc; });

    let html = '';
    for (const [group, names] of Object.entries(SVC_CATEGORIES)) {
        let dotsHtml = '';
        names.forEach(name => {
            const svc = byName[name];
            const status = svc ? svc.status : 'unknown';
            const label = HEALTH_LABELS[status] || status;
            const desc = svc ? (svc.description || label) : 'Not monitored';
            // Short display name
            const short = name.replace('Google Cloud','GCP').replace('Xbox Live','Xbox').replace('PlayStation','PS').replace('Apple Login','Apple').replace('Google Login','Google').replace('EAS Build','EAS').replace('ComfyUI','RTX 3080 · ComfyUI');
            dotsHtml += `<span class="hg-dot" title="${name}: ${desc}"><span class="hg-dot-indicator ${status}"></span>${short}</span>`;
        });
        html += `<div class="health-group"><span class="hg-label">${group}</span><div class="hg-dots">${dotsHtml}</div></div>`;
    }
    grid.innerHTML = html;
}

// ── Workflows Panel ──────────────────────────────────────────────
const _WF_TEMPLATE_META = {
    full:             { icon: 'broadcast', label: 'Full Pipeline', desc: 'End-to-end business evaluation (8 agents)', colour: '#00e5ff' },
    research:         { icon: 'search', label: 'Research', desc: 'Deep research + data analysis', colour: '#00e5ff' },
    content:          { icon: 'edit', label: 'Content', desc: 'Research → CMO content creation', colour: '#ff4081' },
    technical:        { icon: 'cpu', label: 'Technical', desc: 'Technical landscape → CTO review', colour: '#76ff03' },
    gtm:              { icon: 'rocket', label: 'Go-to-Market', desc: 'Market → CMO → Revenue → COO', colour: '#ffd740' },
    strategy:         { icon: 'compass', label: 'Strategy', desc: 'Research → Visionary → Strategist', colour: '#448aff' },
    story:            { icon: 'book', label: 'Story Creation', desc: 'Research → Child Dev → Story → Art', colour: '#ea80fc' },
    character:        { icon: 'smile', label: 'Character/IP', desc: 'Research → Character → Creative', colour: '#ffab40' },
    engineering:      { icon: 'tool', label: 'Engineering', desc: 'Architect → Eng Manager → QA → Security', colour: '#82b1ff' },
    qa:               { icon: 'check-circle', label: 'QA Pipeline', desc: 'QA Director → Automation → Security', colour: '#00e676' },
    fundraise:        { icon: 'dollar-sign', label: 'Fundraise', desc: 'Intel → Finance → Investor → CEO', colour: '#b2ff59' },
    growth_plan:      { icon: 'trending-up', label: 'Growth', desc: 'Trends → Growth → CMO campaigns', colour: '#69f0ae' },
    content_creation: { icon: 'palette', label: 'Content Creation', desc: 'Trends → Visionary → Creative → CMO', colour: '#b388ff' },
    product_launch:   { icon: 'rocket', label: 'Product Launch', desc: 'Intel → Product → Architect → Eng → CMO', colour: '#ff6e40' },
    social_media:     { icon: 'share', label: 'Social Media', desc: 'Trends → Content → Creative → Growth → CMO', colour: '#e040fb' },
    software_architecture: { icon: 'layers', label: 'Software Architecture', desc: 'Research → Architect → CTO → Security → Eng', colour: '#82b1ff' },
    legal_compliance: { icon: 'shield', label: 'Legal & Compliance', desc: 'Research → Risk → Security → Chief of Staff', colour: '#ff5252' },
};

// _wfMakeCard and refreshWorkflows removed — templates now live in the dropdown only

// ── Custom Workflow Builder ──────────────────────────────────────────
let _cwbAgentList = []; // cached agent list

async function _cwbOpen() {
    let overlay = document.getElementById('cwb-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'cwb-overlay';
        overlay.className = 'cwb-overlay';
        overlay.innerHTML = `
            <div class="cwb-dialog">
                <div class="cwb-header">
                    <span class="cwb-title">CREATE CUSTOM WORKFLOW</span>
                    <button class="cwb-close" onclick="_cwbClose()">✕</button>
                </div>
                <div class="cwb-body">
                    <div class="cwb-field">
                        <label>Name</label>
                        <input type="text" id="cwb-name" class="cwb-input" placeholder="My Workflow" />
                    </div>
                    <div class="cwb-field">
                        <label>Description</label>
                        <input type="text" id="cwb-desc" class="cwb-input" placeholder="What this workflow does…" />
                    </div>
                    <div class="cwb-field">
                        <label>Icon (emoji)</label>
                        <input type="text" id="cwb-icon" class="cwb-input cwb-icon-input" value="⚡" maxlength="2" />
                    </div>
                    <div class="cwb-field">
                        <label>Agents (click to add in order)</label>
                        <div id="cwb-agent-pool" class="cwb-agent-pool"></div>
                    </div>
                    <div class="cwb-field">
                        <label>Chain <span id="cwb-chain-count">(0 agents)</span></label>
                        <div id="cwb-chain" class="cwb-chain"></div>
                    </div>
                </div>
                <div class="cwb-footer">
                    <button class="cwb-save-btn" onclick="_cwbSave()">SAVE WORKFLOW</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
    }
    // Populate agent pool
    if (_cwbAgentList.length === 0) {
        try {
            _cwbAgentList = await api('/api/ceo/agents') || [];
        } catch (e) { console.error('Failed to load agents:', e); }
    }
    const pool = document.getElementById('cwb-agent-pool');
    const chain = document.getElementById('cwb-chain');
    pool.innerHTML = '';
    chain.innerHTML = '';
    document.getElementById('cwb-chain-count').textContent = '(0 agents)';
    document.getElementById('cwb-name').value = '';
    document.getElementById('cwb-desc').value = '';
    document.getElementById('cwb-icon').value = '⚡';
    _cwbAgentList.forEach(agent => {
        const chip = document.createElement('button');
        chip.className = 'cwb-agent-chip';
        chip.textContent = agent.name;
        chip.title = agent.description || agent.role || '';
        chip.dataset.agentId = agent.id;
        chip.onclick = () => _cwbAddAgent(agent);
        pool.appendChild(chip);
    });
    overlay.classList.add('active');
}

function _cwbClose() {
    const overlay = document.getElementById('cwb-overlay');
    if (overlay) overlay.classList.remove('active');
}

function _cwbAddAgent(agent) {
    const chain = document.getElementById('cwb-chain');
    const countEl = document.getElementById('cwb-chain-count');
    const item = document.createElement('div');
    item.className = 'cwb-chain-item';
    item.dataset.agentId = agent.id;
    item.innerHTML = `<span class="cwb-chain-name">${_escHtml(agent.name)}</span><button class="cwb-chain-remove" title="Remove">✕</button>`;
    item.querySelector('.cwb-chain-remove').onclick = () => {
        item.remove();
        countEl.textContent = `(${chain.children.length} agents)`;
    };
    chain.appendChild(item);
    countEl.textContent = `(${chain.children.length} agents)`;
}

async function _cwbSave() {
    const name = document.getElementById('cwb-name').value.trim();
    const desc = document.getElementById('cwb-desc').value.trim();
    const icon = document.getElementById('cwb-icon').value.trim() || '⚡';
    const chain = document.getElementById('cwb-chain');
    const agents = [];
    chain.querySelectorAll('.cwb-chain-item').forEach(el => {
        agents.push({ agent_id: el.dataset.agentId });
    });
    if (!name) { alert('Please enter a workflow name'); return; }
    if (agents.length < 1) { alert('Add at least one agent'); return; }
    try {
        const resp = await fetch('/api/ceo/custom-workflows', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, description: desc, icon, agents }),
        });
        const data = await resp.json();
        if (data.ok) {
            _cwbClose();
            _customWfCache = null;  // bust cache
            _populateTemplateDropdown();
        } else {
            alert(data.error || 'Failed to save workflow');
        }
    } catch (e) {
        console.error('Save workflow error:', e);
        alert('Failed to save workflow');
    }
}

// ── Full-Page Panel Routing ──────────────────────────────────────
// Each dock tile maps to a title and a panel ID; clicking opens a full-page view
const DOCK_EXPAND = {
    email:     { title: 'EMAIL INTELLIGENCE',       panel: 'dock-panel-email' },
    revenue:   { title: 'REVENUE OVERVIEW',          panel: 'dock-panel-revenue' },
    content:   { title: 'CONTENT PIPELINE',          panel: 'dock-panel-content' },
    engage:    { title: 'ENGAGEMENT HUB',            panel: 'dock-panel-engage' },

    deadlines: { title: 'DEADLINES & ROADMAP',       panel: 'dock-panel-deadlines' },
    bulletins: { title: 'BULLETINS',                 panel: 'dock-panel-bulletins' },
    todo:      { title: 'TODO LIST',                 panel: 'dock-panel-todo' },
    cicd:      { title: 'CI/CD',                      panel: 'dock-panel-cicd' },
    claude:    { title: 'CLAUDE API USAGE',           panel: 'dock-panel-claude' },
    ceo:       { title: 'AGENT ORCHESTRATOR',           panel: 'dock-panel-ceo' },
    org:       { title: 'CEO',                        panel: 'dock-panel-org' },
};

let activeDock = null;
let _panelTransitioning = false;

// ── Update Queue: defer panels/SSE while user is in a dock panel ──
const _updateQueue = [];
let _drainTimer = null;

function _queueUpdate(entry) {
    // entry: { type:'panel'|'sse', data: ... }
    _updateQueue.push(entry);
    _updateQueueBadge();
}

function _updateQueueBadge() {
    let badge = document.getElementById('update-queue-badge');
    if (_updateQueue.length === 0) {
        if (badge) badge.style.display = 'none';
        return;
    }
    if (!badge) {
        badge = document.createElement('div');
        badge.id = 'update-queue-badge';
        badge.className = 'update-queue-badge';
        const clock = document.getElementById('clock');
        if (clock) clock.parentElement.appendChild(badge);
    }
    badge.style.display = 'flex';
    badge.textContent = _updateQueue.length;
    badge.title = `${_updateQueue.length} pending update${_updateQueue.length > 1 ? 's' : ''}`;
}

function _drainUpdateQueue() {
    if (_drainTimer) { clearTimeout(_drainTimer); _drainTimer = null; }
    if (_updateQueue.length === 0) { _updateQueueBadge(); return; }
    // Don't drain while a dock panel is open
    if (activeDock) return;
    const next = _updateQueue.shift();
    _updateQueueBadge();
    if (next.type === 'panel' && typeof voice !== 'undefined' && voice._renderAnalysisPanel) {
        voice._renderAnalysisPanel(next.data, true); // true = bypass queue guard
    } else if (next.type === 'sse') {
        _deliverSSEDirect(next.data);
    }
    // Schedule next delivery after user has a moment to see it
    if (_updateQueue.length > 0) {
        _drainTimer = setTimeout(_drainUpdateQueue, 6000);
    }
}

function openExpandPanels(panelKey, pushHistory = true) {
    const cfg = DOCK_EXPAND[panelKey];
    if (!cfg) return;
    if (_panelTransitioning) return;

    // Toggle off if same
    if (activeDock === panelKey) { closeExpandPanels(); return; }

    // If another panel is open, swap content (no re-animate orb)
    const wasOpen = !!activeDock;
    if (wasOpen) {
        _returnPanelContent();
    }

    // If camera is active, close it first
    if (_cam.active) _camClose();

    // Close analysis wings to prevent overlay
    if (typeof voice !== 'undefined' && voice._closeAnalysisWings) voice._closeAnalysisWings();

    const viewport = document.getElementById('panel-viewport');
    const body = document.getElementById('panel-viewport-body');
    const title = document.getElementById('panel-viewport-title');
    if (!viewport || !body) return;

    // Move panel content into viewport
    const src = cfg.panel ? document.getElementById(cfg.panel) : null;
    if (src) {
        body.innerHTML = '';
        body.appendChild(src);
        src.style.display = 'block';
    }
    title.textContent = cfg.title || '';

    activeDock = panelKey;

    // Highlight active dock tile
    document.querySelectorAll('.dock-panel[data-dock]').forEach(t => t.classList.remove('active'));
    const tile = document.querySelector(`.dock-panel[data-dock="${panelKey}"]`);
    if (tile) tile.classList.add('active');

    // Push URL state
    if (pushHistory) {
        history.pushState({ panel: panelKey }, '', `/panel/${panelKey}`);
    }

    // If already in panel-mode, cross-fade to new content (no orb animation needed)
    if (wasOpen) {
        // Fade out old content
        body.classList.add('swapping');
        setTimeout(() => {
            // Content was already swapped by _returnPanelContent + appendChild above
            viewport.classList.add('active');
            // Fade in new content
            requestAnimationFrame(() => {
                body.classList.remove('swapping');
            });
            _panelPostOpen(panelKey);
        }, 300);
        return;
    }

    _panelTransitioning = true;

    // Clear dialogue options
    const dOpts = document.getElementById('dialogue-options');
    if (dOpts) dOpts.innerHTML = '';
    _dismissBriefingPrompt();

    // ── Orb → bottom-right corner ──
    const mc = document.querySelector('.mc-center');
    const startRect = mc.getBoundingClientRect();
    const orbCanvas = document.getElementById('orb-canvas');
    const orbW = orbCanvas ? orbCanvas.offsetWidth : startRect.width;
    const scaleFrom = orbW / 130;

    const startCX = startRect.left + startRect.width / 2;
    const startCY = startRect.top + startRect.height / 2;

    // Resize canvas to 130px
    if (typeof orb !== 'undefined') orb._resize(130);
    const mcW = mc.offsetWidth;
    const mcH = mc.offsetHeight;

    // Pin at current visual center, visually scaled up to original size
    mc.style.position = 'fixed';
    mc.style.top = (startCY - mcH / 2) + 'px';
    mc.style.left = (startCX - mcW / 2) + 'px';
    mc.style.transformOrigin = 'center center';
    mc.style.transform = `translate(0px, 0px) scale(${scaleFrom})`;
    mc.style.transition = 'none';
    mc.style.zIndex = '600';
    void mc.offsetHeight;

    // Dim dashboard
    document.body.classList.add('panel-mode');

    // Target: bottom-right corner, above dock
    const dockEl = document.querySelector('.mc-dock');
    const dockH = dockEl ? dockEl.offsetHeight : 60;
    const targetTop = window.innerHeight - dockH - mcH + 10;
    const targetLeft = window.innerWidth - mcW - 32;
    const targetCX = targetLeft + mcW / 2;
    const targetCY = targetTop + mcH / 2;
    const dx = targetCX - startCX;
    const dy = targetCY - startCY;

    requestAnimationFrame(() => {
        mc.style.transition = 'transform 0.9s cubic-bezier(0.22,1,0.36,1)';
        mc.style.transform = `translate(${dx}px, ${dy}px) scale(1)`;
    });

    setTimeout(() => {
        mc.style.transition = 'none';
        mc.style.top = targetTop + 'px';
        mc.style.left = targetLeft + 'px';
        mc.style.transform = 'none';
    }, 960);

    // Show panel viewport after orb starts moving
    setTimeout(() => {
        viewport.classList.add('active');
        _panelTransitioning = false;
    }, 400);

    _panelPostOpen(panelKey);
}

function _panelPostOpen(panelKey) {
    // Panel-specific init hooks
    if (panelKey === 'ceo') {
        _ceoInitPanel().catch(e => console.error('[CEO] Init panel error:', e));
        // Restore active pipeline after panel is ready
        setTimeout(() => _ceoRestorePipelineState(), 500);
    }
    if (panelKey === 'org') _orgInitPanel().catch(e => console.error('[ORG] Init panel error:', e));
    if (panelKey === 'todo') {
        _renderTodoList();
        const todoAddBtn = document.getElementById('todo-add-btn');
        const todoInput = document.getElementById('todo-input');
        if (todoAddBtn) todoAddBtn.onclick = _addTodo;
        if (todoInput) todoInput.onkeydown = e => { if (e.key === 'Enter') _addTodo(); };
    }
}

function _returnPanelContent() {
    const body = document.getElementById('panel-viewport-body');
    const panels = document.getElementById('dock-panels');
    if (!body) return;
    const child = body.querySelector('.dock-panel-inner');
    if (child && panels) {
        child.style.display = 'none';
        panels.appendChild(child);
    }
    body.innerHTML = '';
}

function closeExpandPanels(pushHistory = true) {
    if (!activeDock) return;
    if (_panelTransitioning) return;

    _panelTransitioning = true;
    _returnPanelContent();

    const viewport = document.getElementById('panel-viewport');
    const title = document.getElementById('panel-viewport-title');
    if (viewport) viewport.classList.remove('active');
    if (title) title.textContent = '';

    activeDock = null;
    document.querySelectorAll('.dock-panel[data-dock]').forEach(t => t.classList.remove('active'));

    // Push URL back to root
    if (pushHistory) {
        history.pushState({}, '', '/');
    }

    // ── Orb → back to center ──
    const mc = document.querySelector('.mc-center');
    if (!mc) { _panelTransitioning = false; document.body.classList.remove('panel-mode'); return; }

    const curRect = mc.getBoundingClientRect();
    const curCX = curRect.left + curRect.width / 2;
    const curCY = curRect.top + curRect.height / 2;
    const fullSize = Math.max(200, Math.min(window.innerWidth * 0.2, 420));
    const scaleFrom = 130 / fullSize;

    // Resize canvas back to full
    if (typeof orb !== 'undefined') orb._resize(Math.round(fullSize));
    const mcW = mc.offsetWidth;
    const mcH = mc.offsetHeight;

    // Where CSS naturally places the orb (center of viewport parent)
    const parent = mc.parentElement;
    const parentRect = parent.getBoundingClientRect();
    const targetCX = parentRect.left + parentRect.width / 2;
    const targetCY = parentRect.top + parentRect.height / 2;

    // Pin at current visual position, visually still small
    mc.style.position = 'fixed';
    mc.style.top = (curCY - mcH / 2) + 'px';
    mc.style.left = (curCX - mcW / 2) + 'px';
    mc.style.transformOrigin = 'center center';
    mc.style.transform = `translate(0px, 0px) scale(${scaleFrom})`;
    mc.style.transition = 'none';
    void mc.offsetHeight;

    // Restore dashboard
    document.body.classList.remove('panel-mode');

    const dx = targetCX - curCX;
    const dy = targetCY - curCY;

    requestAnimationFrame(() => {
        mc.style.transition = 'transform 0.9s cubic-bezier(0.22,1,0.36,1)';
        mc.style.transform = `translate(${dx}px, ${dy}px) scale(1)`;
    });

    setTimeout(() => {
        mc.style.transition = 'none';
        mc.style.cssText = 'transition: none !important;';
        void mc.offsetHeight;
        requestAnimationFrame(() => {
            mc.style.cssText = '';
            if (typeof orb !== 'undefined') orb._resize();
        });
        _panelTransitioning = false;
        // Drain queued updates now that user is back on home page
        if (_updateQueue.length > 0) setTimeout(_drainUpdateQueue, 1500);
    }, 960);
}

// Quick close — removes panel content and body class without orb animation
// Used when transitioning directly to another mode (e.g. camera)
function _panelQuickClose() {
    _returnPanelContent();
    const viewport = document.getElementById('panel-viewport');
    if (viewport) viewport.classList.remove('active');
    document.body.classList.remove('panel-mode');
    activeDock = null;
    _panelTransitioning = false;
    document.querySelectorAll('.dock-panel[data-dock]').forEach(t => t.classList.remove('active'));
    history.pushState({}, '', '/');
    // Drain queued updates
    if (_updateQueue.length > 0) setTimeout(_drainUpdateQueue, 1500);
}

// ── Todo List (localStorage-backed) ─────────────────────────────
const TODO_KEY = 'arbiter_todos';
const TODO_HISTORY_KEY = 'arbiter_todos_history';

function _loadTodos() {
    try { return JSON.parse(localStorage.getItem(TODO_KEY) || '[]'); }
    catch { return []; }
}

function _saveTodos(todos) {
    localStorage.setItem(TODO_KEY, JSON.stringify(todos));
    _updateTodoDock(todos);
}

function _loadTodoHistory() {
    try { return JSON.parse(localStorage.getItem(TODO_HISTORY_KEY) || '[]'); }
    catch { return []; }
}

function _saveTodoHistory(history) {
    localStorage.setItem(TODO_HISTORY_KEY, JSON.stringify(history));
}

function _clearDoneTodos() {
    const todos = _loadTodos();
    const done = todos.filter(t => t.done);
    if (!done.length) return;
    // Archive done tasks with completion timestamp
    const history = _loadTodoHistory();
    for (const t of done) {
        history.unshift({ ...t, archivedAt: new Date().toISOString() });
    }
    _saveTodoHistory(history);
    // Keep only active tasks
    _saveTodos(todos.filter(t => !t.done));
    _renderTodoList();
}

function _updateTodoDock(todos) {
    if (!todos) todos = _loadTodos();
    const total = todos.length;
    const done = todos.filter(t => t.done).length;
    const countEl = document.getElementById('dock-todo-count');
    const doneEl = document.getElementById('dock-todo-done');
    if (countEl) countEl.textContent = total - done;
    if (doneEl) doneEl.textContent = done;
}

function _addTodo() {
    const input = document.getElementById('todo-input');
    const dateInput = document.getElementById('todo-date');
    const timeInput = document.getElementById('todo-time');
    if (!input || !input.value.trim()) return;

    const todos = _loadTodos();
    todos.push({
        id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
        text: input.value.trim(),
        date: dateInput ? dateInput.value : '',
        time: timeInput ? timeInput.value : '',
        done: false,
        created: new Date().toISOString()
    });
    _saveTodos(todos);
    input.value = '';
    if (dateInput) dateInput.value = '';
    if (timeInput) timeInput.value = '';
    _renderTodoList();
}

function _toggleTodo(id) {
    const todos = _loadTodos();
    const t = todos.find(x => x.id === id);
    if (t) t.done = !t.done;
    _saveTodos(todos);
    _renderTodoList();
}

function _deleteTodo(id) {
    let todos = _loadTodos();
    const removed = todos.find(x => x.id === id);
    // Archive if it was completed
    if (removed && removed.done) {
        const history = _loadTodoHistory();
        history.unshift({ ...removed, archivedAt: new Date().toISOString() });
        _saveTodoHistory(history);
    }
    todos = todos.filter(x => x.id !== id);
    _saveTodos(todos);
    _renderTodoList();
}

function _renderTodoList() {
    const container = document.getElementById('todo-schedule');
    if (!container) return;
    const todos = _loadTodos();
    const history = _loadTodoHistory();
    _updateTodoDock(todos);

    const doneCount = todos.filter(t => t.done).length;

    if (!todos.length && !history.length) {
        container.innerHTML = '<div class="feed-empty">NO TASKS — ADD ONE ABOVE</div>';
        return;
    }

    // Group by date
    const now = new Date();
    const todayStr = now.toISOString().slice(0, 10);
    const tomorrowStr = new Date(now.getTime() + 86400000).toISOString().slice(0, 10);
    const groups = {};
    const noDate = [];

    for (const t of todos) {
        if (t.date) {
            if (!groups[t.date]) groups[t.date] = [];
            groups[t.date].push(t);
        } else {
            noDate.push(t);
        }
    }

    // Sort dates
    const sortedDates = Object.keys(groups).sort();

    let html = '';

    // Clear done button (only if there are completed tasks)
    if (doneCount > 0) {
        html += `<div class="todo-actions-bar">
            <button class="todo-clear-done-btn" id="todo-clear-done">⏏ CLEAR ${doneCount} DONE</button>
        </div>`;
    }

    // Render dated groups
    for (const date of sortedDates) {
        const items = groups[date].sort((a, b) => (a.time || '').localeCompare(b.time || ''));
        let label = date;
        let groupClass = 'upcoming';
        if (date === todayStr) { label = 'TODAY — ' + _formatDateLabel(date); groupClass = 'today'; }
        else if (date === tomorrowStr) { label = 'TOMORROW — ' + _formatDateLabel(date); groupClass = 'upcoming'; }
        else if (date < todayStr) { label = 'OVERDUE — ' + _formatDateLabel(date); groupClass = 'overdue'; }
        else { label = _formatDateLabel(date); }

        html += `<div class="todo-day-group"><div class="todo-day-label">${label}</div>`;
        for (const t of items) {
            html += _renderTodoItem(t, groupClass);
        }
        html += '</div>';
    }

    // Undated tasks
    if (noDate.length) {
        html += '<div class="todo-day-group"><div class="todo-day-label">UNSCHEDULED</div>';
        for (const t of noDate) {
            html += _renderTodoItem(t, 'upcoming');
        }
        html += '</div>';
    }

    // ── History section (collapsible) ──
    if (history.length) {
        // Group history by archived date (day)
        const histByDay = {};
        for (const h of history) {
            const day = (h.archivedAt || h.created || '').slice(0, 10);
            const key = day || 'UNKNOWN';
            if (!histByDay[key]) histByDay[key] = [];
            histByDay[key].push(h);
        }
        const histDays = Object.keys(histByDay).sort().reverse(); // newest first

        html += `<div class="todo-history-section">
            <button class="todo-history-toggle" id="todo-history-toggle">
                <span class="todo-history-chevron" id="todo-history-chevron">▶</span>
                HISTORY <span class="todo-history-count">${history.length}</span>
            </button>
            <div class="todo-history-body" id="todo-history-body" style="display:none;">`;
        for (const day of histDays) {
            const label = day === todayStr ? 'TODAY' : _formatDateLabel(day);
            html += `<div class="todo-day-group"><div class="todo-day-label todo-day-label-hist">${label}</div>`;
            for (const h of histByDay[day]) {
                const timeStr = h.time ? h.time.slice(0, 5) : '';
                const origDate = h.date ? _formatDateLabel(h.date) : '';
                html += `<div class="todo-item done history">
                    <span class="todo-hist-check">✓</span>
                    <span class="todo-item-time">${timeStr}</span>
                    <span class="todo-item-text">${h.text}</span>
                    ${origDate ? `<span class="todo-hist-orig">${origDate}</span>` : ''}
                </div>`;
            }
            html += '</div>';
        }
        html += '</div></div>';
    }

    container.innerHTML = html;

    // Attach event listeners — active tasks
    container.querySelectorAll('.todo-check').forEach(btn => {
        btn.addEventListener('click', () => _toggleTodo(btn.dataset.id));
    });
    container.querySelectorAll('.todo-item-delete').forEach(btn => {
        btn.addEventListener('click', () => _deleteTodo(btn.dataset.id));
    });
    // Clear done button
    const clearBtn = document.getElementById('todo-clear-done');
    if (clearBtn) clearBtn.addEventListener('click', _clearDoneTodos);
    // History toggle
    const histToggle = document.getElementById('todo-history-toggle');
    if (histToggle) {
        histToggle.addEventListener('click', () => {
            const body = document.getElementById('todo-history-body');
            const chevron = document.getElementById('todo-history-chevron');
            if (!body) return;
            const open = body.style.display !== 'none';
            body.style.display = open ? 'none' : 'block';
            if (chevron) chevron.textContent = open ? '▶' : '▼';
        });
    }
}

function _renderTodoItem(t, groupClass) {
    const cls = (t.done ? 'done' : groupClass);
    const timeStr = t.time ? t.time.slice(0, 5) : '';
    return `<div class="todo-item ${cls}">
        <button class="todo-check ${t.done ? 'checked' : ''}" data-id="${t.id}">${t.done ? '✓' : ''}</button>
        <span class="todo-item-time">${timeStr}</span>
        <span class="todo-item-text">${t.text}</span>
        <button class="todo-item-delete" data-id="${t.id}">✕</button>
    </div>`;
}

function _formatDateLabel(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    const days = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
    const months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
    return `${days[d.getDay()]} ${d.getDate()} ${months[d.getMonth()]}`;
}

// ── Todo Reminders (local cron — no LLM) ────────────────────────
const _firedReminders = new Set();
let _reminderInterval = null;

function _initTodoReminders() {
    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
    // Check every 30 seconds
    if (_reminderInterval) clearInterval(_reminderInterval);
    _reminderInterval = setInterval(_checkTodoReminders, 30_000);
    // Also run once immediately
    _checkTodoReminders();
}

function _checkTodoReminders() {
    const todos = _loadTodos();
    const now = new Date();
    const nowDate = now.toISOString().slice(0, 10);
    const nowMins = now.getHours() * 60 + now.getMinutes();

    for (const t of todos) {
        if (t.done || !t.date || !t.time || _firedReminders.has(t.id)) continue;

        const taskMins = parseInt(t.time.split(':')[0]) * 60 + parseInt(t.time.split(':')[1]);

        // Fire if: task is today and within 1 minute of now, OR task is overdue
        if (t.date === nowDate && Math.abs(taskMins - nowMins) <= 1) {
            _fireReminder(t);
        } else if (t.date < nowDate) {
            // Overdue — fire once
            _fireReminder(t, true);
        }
    }
}

function _fireReminder(todo, overdue = false) {
    _firedReminders.add(todo.id);
    const title = overdue ? '⏰ OVERDUE TASK' : '🔔 TASK DUE NOW';
    const body = `${todo.text}${todo.time ? ' — ' + todo.time.slice(0, 5) : ''}`;

    // Browser notification
    if ('Notification' in window && Notification.permission === 'granted') {
        const n = new Notification(title, {
            body,
            icon: '/static/comfyui_output/arbiter-icon.png',
            tag: `todo-${todo.id}`,
            requireInteraction: true,
        });
        n.onclick = () => {
            window.focus();
            if (typeof openExpandPanels === 'function') openExpandPanels('todo');
            n.close();
        };
    }

    // Audio alert — short beep using Web Audio API
    _playReminderBeep();

    // In-app toast (re-use existing HUD pattern)
    _showReminderToast(title, body);
}

function _playReminderBeep() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = 880;
        osc.type = 'sine';
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.5);
        // Second beep
        const osc2 = ctx.createOscillator();
        const gain2 = ctx.createGain();
        osc2.connect(gain2);
        gain2.connect(ctx.destination);
        osc2.frequency.value = 1100;
        osc2.type = 'sine';
        gain2.gain.setValueAtTime(0.3, ctx.currentTime + 0.6);
        gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 1.1);
        osc2.start(ctx.currentTime + 0.6);
        osc2.stop(ctx.currentTime + 1.1);
    } catch (e) { /* audio not supported */ }
}

function _showReminderToast(title, body) {
    const toast = document.createElement('div');
    toast.className = 'reminder-toast';
    toast.innerHTML = `
        <div class="reminder-toast-title">${title}</div>
        <div class="reminder-toast-body">${body}</div>
    `;
    toast.addEventListener('click', () => {
        if (typeof openExpandPanels === 'function') openExpandPanels('todo');
        toast.remove();
    });
    document.body.appendChild(toast);
    // Auto-remove after 10 seconds
    setTimeout(() => { if (toast.parentNode) toast.remove(); }, 10_000);
}

// ── Roadmap / Business Planner ──────────────────────────────────
let _roadmapData = [];

async function refreshDeadlines() {
    const grid = document.getElementById('deadlines-grid');
    if (!grid) return;

    // Fetch from API (auto-seed if empty)
    try {
        let d = await api('/api/roadmap');
        if (!d || !d.milestones || d.milestones.length === 0) {
            await api('/api/roadmap/seed', 'POST');
            d = await api('/api/roadmap');
        }
        _roadmapData = d.milestones || [];
    } catch (e) {
        console.warn('[ROADMAP] Fetch failed:', e);
    }

    if (!_roadmapData.length) {
        grid.innerHTML = '<div class="feed-empty">NO MILESTONES SET</div>';
        return;
    }

    const now = new Date();
    let nextDeadline = null;
    const catIcons = { launch: _SVG('rocket',14), milestone: _SVG('pin',14), campaign: _SVG('broadcast',14), review: _SVG('clipboard',14) };
    const STATUS_LABEL = { planned: 'PLANNED', in_progress: 'ACTIVE', at_risk: 'AT RISK', blocked: 'BLOCKED', completed: 'DONE' };
    const STATUS_CLS   = { planned: 'planned', in_progress: 'active', at_risk: 'at-risk', blocked: 'at-risk', completed: 'done' };

    // Sort by date
    const sorted = [..._roadmapData].sort((a, b) => new Date(a.date) - new Date(b.date));

    // ── 1. Quarterly horizontal timeline ───────────────────────
    const quarters = {};
    sorted.forEach(m => {
        const q = m.quarter || 'Other';
        if (!quarters[q]) quarters[q] = [];
        quarters[q].push(m);
    });

    const qOrder = Object.keys(quarters).sort();
    let html = '<div class="rm-timeline-strip">';
    qOrder.forEach((q, qi) => {
        const items = quarters[q];
        html += `<div class="rm-q-col">
            <div class="rm-q-header">${q}</div>
            <div class="rm-q-track">`;
        items.forEach(m => {
            const status = m.status || 'planned';
            const cls = STATUS_CLS[status] || 'planned';
            const icon = catIcons[m.category] || _SVG('pin',14);
            const shortTitle = m.title.length > 20 ? m.title.slice(0, 18) + '…' : m.title;
            html += `<div class="rm-q-marker ${cls}" title="${m.title} — ${m.date}">
                <span class="rm-q-dot"></span>
                <span class="rm-q-label">${icon} ${shortTitle}</span>
            </div>`;
        });
        html += '</div></div>';
        if (qi < qOrder.length - 1) html += '<div class="rm-q-divider"></div>';
    });
    html += '</div>';

    // ── 2. Pipeline stage summary (single row) ────────────────
    const counts = { planned: 0, in_progress: 0, at_risk: 0, completed: 0 };
    sorted.forEach(m => {
        const s = m.status || 'planned';
        if (s === 'blocked') counts.at_risk++;
        else if (counts[s] !== undefined) counts[s]++;
    });
    html += `<div class="rm-pipeline-summary">
        <div class="rm-pipe-stage planned"><span class="rm-pipe-count">${counts.planned}</span> PLANNED</div>
        <div class="rm-pipe-arrow">→</div>
        <div class="rm-pipe-stage active"><span class="rm-pipe-count">${counts.in_progress}</span> IN PROGRESS</div>
        <div class="rm-pipe-arrow">→</div>
        <div class="rm-pipe-stage at-risk"><span class="rm-pipe-count">${counts.at_risk}</span> AT RISK</div>
        <div class="rm-pipe-arrow">→</div>
        <div class="rm-pipe-stage done"><span class="rm-pipe-count">${counts.completed}</span> DONE</div>
    </div>`;

    // ── 3. Compact milestone rows ─────────────────────────────
    sorted.forEach(m => {
        const target = new Date(m.date);
        const diffDays = Math.ceil((target - now) / (1000 * 60 * 60 * 24));
        const icon = catIcons[m.category] || _SVG('pin',14);
        const status = m.status || 'planned';
        const statusDotCls = status === 'completed' ? 'success'
            : status === 'at_risk' || status === 'blocked' ? 'failure'
            : status === 'in_progress' ? 'running' : 'unknown';
        const dateStr = target.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });

        let countdownText = '';
        if (status === 'completed') countdownText = '✓ DONE';
        else if (diffDays < 0) countdownText = `${Math.abs(diffDays)}d OVER`;
        else countdownText = `${diffDays}d`;

        if (!nextDeadline && diffDays >= 0 && status !== 'completed') {
            nextDeadline = { ...m, days: diffDays };
        }

        const priorityBadge = m.priority === 'critical' ? '<span class="rm-priority critical">CRIT</span>'
            : m.priority === 'high' ? '<span class="rm-priority high">HIGH</span>' : '';

        const statusBadge = `<span class="rm-status-badge ${STATUS_CLS[status]}">${STATUS_LABEL[status]}</span>`;

        html += `<div class="rm-row" title="${m.description || ''}">
            <span class="cicd-status ${statusDotCls}"></span>
            <span class="rm-row-icon">${icon}</span>
            <span class="rm-row-title">${m.title} ${priorityBadge}</span>
            ${statusBadge}
            <span class="rm-row-date">${dateStr}</span>
            <span class="rm-row-countdown ${status === 'completed' ? 'done' : diffDays < 0 ? 'overdue' : diffDays <= 30 ? 'soon' : 'upcoming'}">${countdownText}</span>
        </div>`;
    });

    grid.innerHTML = html;

    // Update dock summary
    const dlNext = document.getElementById('dock-dl-next');
    const dlLabel = document.getElementById('dock-dl-label');
    if (dlNext && nextDeadline) {
        dlNext.textContent = `${nextDeadline.days}d`;
        dlNext.className = 'dp-val ' + (nextDeadline.days <= 14 ? 'alert' : nextDeadline.days <= 30 ? 'caution' : 'nominal');
    }
    if (dlLabel && nextDeadline) {
        dlLabel.textContent = nextDeadline.title.substring(0, 16);
    }
}

// ══════════════════════════════════════════════════════════════════
// JOB TRACKER — Floating top-right HUD for active jobs/queues
// ══════════════════════════════════════════════════════════════════
const _jobs = new Map();      // jobId → { id, type, label, status, startTime, progress?, total? }
let _jobIdCounter = 0;
let _jobTickTimer = null;

const _JOB_TYPES = {
    agent:    { label: 'AGENT',    colour: 'var(--cyan)' },
    pipeline: { label: 'PIPELINE', colour: '#7c4dff' },
    chat:     { label: 'QUERY',    colour: 'var(--cyan)' },
    voice:    { label: 'VOICE',    colour: '#ffd740' },
};

function _jobAdd(type, label) {
    const id = `job_${Date.now()}_${++_jobIdCounter}`;
    _jobs.set(id, { id, type, label, status: 'running', startTime: Date.now(), progress: 0, total: 0 });
    _jobRender();
    _jobStartTick();
    return id;
}

function _jobUpdate(id, updates) {
    const job = _jobs.get(id);
    if (!job) return;
    Object.assign(job, updates);
    _jobRender();
}

function _jobComplete(id, error) {
    const job = _jobs.get(id);
    if (!job) return;
    job.status = error ? 'error' : 'complete';
    job.endTime = Date.now();
    _jobRender();
    // Auto-remove after a short delay
    setTimeout(() => {
        const el = document.getElementById(id);
        if (el) { el.classList.add('removing'); }
        setTimeout(() => { _jobs.delete(id); _jobRender(); }, 450);
    }, error ? 4000 : 2200);
}

function _jobElapsed(ms) {
    const s = Math.floor(ms / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    return `${m}m${String(s % 60).padStart(2, '0')}s`;
}

function _jobStartTick() {
    if (_jobTickTimer) return;
    _jobTickTimer = setInterval(() => {
        const running = [..._jobs.values()].filter(j => j.status === 'running');
        if (!running.length) { clearInterval(_jobTickTimer); _jobTickTimer = null; return; }
        // Update elapsed timers
        for (const j of running) {
            const el = document.getElementById(`${j.id}-elapsed`);
            if (el) el.textContent = _jobElapsed(Date.now() - j.startTime);
        }
    }, 1000);
}

function _jobRender() {
    const container = document.getElementById('job-tracker');
    if (!container) return;

    if (_jobs.size === 0) {
        container.classList.add('empty');
        container.innerHTML = '';
        return;
    }
    container.classList.remove('empty');

    // Build items — most recent first
    const sorted = [..._jobs.values()].sort((a, b) => b.startTime - a.startTime);
    let html = '';
    for (const job of sorted) {
        const typeMeta = _JOB_TYPES[job.type] || _JOB_TYPES.chat;
        const elapsed = _jobElapsed((job.endTime || Date.now()) - job.startTime);

        let iconHtml;
        if (job.status === 'running') {
            iconHtml = '<div class="jt-spinner"></div>';
        } else if (job.status === 'complete') {
            iconHtml = `<div class="jt-icon complete">${_SVG('check-circle', 14)}</div>`;
        } else {
            iconHtml = `<div class="jt-icon error">${_SVG('alert-triangle', 14)}</div>`;
        }

        // Progress bar for pipelines
        let progressHtml = '';
        if (job.type === 'pipeline' && job.total > 0) {
            const pct = Math.round((job.progress / job.total) * 100);
            progressHtml = `<div class="jt-progress"><div class="jt-progress-bar" style="width:${pct}%"></div></div>`;
        }

        html += `<div class="job-tracker-item ${job.status}" id="${job.id}" style="position:relative;">
            ${iconHtml}
            <span class="jt-type">${typeMeta.label}</span>
            <span class="jt-label" title="${_escHtml(job.label)}">${_escHtml(job.label)}</span>
            <span class="jt-elapsed" id="${job.id}-elapsed">${elapsed}</span>
            ${progressHtml}
        </div>`;
    }
    container.innerHTML = html;
}

// ── Active Agents Panel (below conversation logs) ────────────────
async function refreshActiveAgents() {
    const container = document.getElementById('active-agents-list');
    if (!container) return;

    try {
        const data = await api('/api/active-jobs');
        if (!data || !data.jobs) return;
        const jobs = data.jobs;

        if (jobs.length === 0) {
            container.innerHTML = '<div class="aa-empty">NO ACTIVE JOBS</div>';
            return;
        }

        let html = '';
        for (const job of jobs) {
            const kindCls = job.kind || 'agent';
            const kindLabel = { pipeline: 'PIPELINE', team: 'TEAM', agent: 'AGENT' }[kindCls] || 'AGENT';
            const statusCls = job.status === 'running' ? 'running' : job.status === 'complete' ? 'complete' : job.status === 'error' ? 'error' : 'waiting';

            // Status icon
            let statusIcon;
            if (statusCls === 'running') statusIcon = '<div class="aa-spinner"></div>';
            else if (statusCls === 'complete') statusIcon = `<div class="aa-icon complete">${_SVG('check-circle', 12)}</div>`;
            else if (statusCls === 'error') statusIcon = `<div class="aa-icon error">${_SVG('alert-triangle', 12)}</div>`;
            else statusIcon = '<div class="aa-icon waiting">◉</div>';

            // Progress info
            let progressHtml = '';
            if (job.total > 0) {
                const pct = Math.round((job.progress / job.total) * 100);
                progressHtml = `<div class="aa-progress"><div class="aa-progress-bar" style="width:${pct}%"></div></div>`;
            }

            // Sub-info line
            let subInfo = '';
            if (job.current_agent) subInfo = job.current_agent;
            else if (job.agent_name) subInfo = job.agent_name;
            else if (job.team_name) subInfo = job.team_name;
            if (job.total > 0) subInfo += (subInfo ? ' · ' : '') + `${job.progress}/${job.total}`;

            // Time ago
            let timeAgo = '';
            if (job.created_at) {
                const diff = Date.now() - new Date(job.created_at).getTime();
                if (diff < 60000) timeAgo = `${Math.floor(diff / 1000)}s`;
                else if (diff < 3600000) timeAgo = `${Math.floor(diff / 60000)}m`;
                else timeAgo = `${Math.floor(diff / 3600000)}h`;
            }

            html += `<div class="aa-card ${statusCls} kind-${kindCls}" title="${_escHtml(job.label)}">
                <div class="aa-card-top">
                    ${statusIcon}
                    <span class="aa-kind">${kindLabel}</span>
                    <span class="aa-label">${_escHtml(job.label)}</span>
                    <span class="aa-time">${timeAgo}</span>
                </div>
                ${subInfo ? `<div class="aa-sub">${_escHtml(subInfo)}</div>` : ''}
                ${progressHtml}
            </div>`;
        }
        container.innerHTML = html;
    } catch (e) {
        console.warn('[ActiveAgents] refresh error:', e);
    }
}

// ── Organisation Mode Module ─────────────────────────────────────
let _orgTemplates = null;
let _orgCustomAgents = null;
let _activeOrgRun = null;
let _orgRunPollTimer = null;
let _orgEditId = null; // template being edited

async function _orgInitPanel() {
    console.log('[ORG] Initialising org panel...');
    // Wire up buttons
    const newTeamBtn = document.getElementById('org-new-team-btn');
    if (newTeamBtn) newTeamBtn.onclick = () => _orgShowTeamModal();

    // Wire up team modal
    const teamModalClose = document.getElementById('org-team-modal-close');
    const teamSaveBtn = document.getElementById('org-team-save');
    if (teamModalClose) teamModalClose.onclick = _orgHideTeamModal;
    if (teamSaveBtn) teamSaveBtn.onclick = _orgSaveTeam;

    // Wire up run controls
    const approveBtn = document.getElementById('org-run-approve');
    const rejectBtn = document.getElementById('org-run-reject');
    if (approveBtn) approveBtn.onclick = _orgRunApprove;
    if (rejectBtn) rejectBtn.onclick = _orgRunReject;

    // Load templates
    await _orgLoadTemplates();
}

// Lightweight fetch of team count for the dock badge (no panel DOM needed)
async function refreshOrgTeamCount() {
    try {
        const resp = await fetch('/api/org/templates');
        const data = await resp.json();
        _orgTemplates = data;
        const badge = document.getElementById('dock-org-teams');
        if (badge) badge.textContent = Array.isArray(data) ? data.length : 0;
    } catch (e) {
        console.warn('[ORG] Team count fetch failed:', e);
    }
}

async function _orgLoadTemplates() {
    try {
        // Ensure agents are cached for rendering agent names/icons
        if (!_ceoAgents) {
            try {
                const agResp = await fetch('/api/ceo/agents');
                _ceoAgents = await agResp.json();
            } catch (e) { /* ignore */ }
        }
        const resp = await fetch('/api/org/templates');
        _orgTemplates = await resp.json();
        _orgRenderTeamsList();
        // Update dock badge
        const badge = document.getElementById('dock-org-teams');
        if (badge) badge.textContent = Array.isArray(_orgTemplates) ? _orgTemplates.length : 0;
    } catch (e) {
        console.error('[ORG] Failed to load templates:', e);
    }
}

function _orgRenderTeamsList() {
    const list = document.getElementById('org-teams-list');
    if (!list) return;

    if (!_orgTemplates || _orgTemplates.length === 0) {
        list.innerHTML = '<div class="org-empty">No teams created yet. Click <b>+ TEAM</b> to build your first team.</div>';
        return;
    }

    list.innerHTML = '';

    // Separate agile vs service templates
    const agileTemplates = _orgTemplates.filter(t => !t.category || t.category !== 'service');
    const serviceTemplates = _orgTemplates.filter(t => t.category === 'service');

    if (agileTemplates.length > 0) {
        const agileHeader = document.createElement('div');
        agileHeader.className = 'org-section-header';
        agileHeader.innerHTML = `<span class="org-section-icon">${_SVG('settings', 14)}</span> AGILE TEAMS <span class="org-section-count">${agileTemplates.length}</span>`;
        list.appendChild(agileHeader);
        for (const t of agileTemplates) _orgRenderCard(list, t);
    }

    if (serviceTemplates.length > 0) {
        const svcHeader = document.createElement('div');
        svcHeader.className = 'org-section-header org-section-service';
        svcHeader.innerHTML = `<span class="org-section-icon">${_SVG('briefcase', 14)}</span> SERVICE BUSINESSES <span class="org-section-count">${serviceTemplates.length}</span>`;
        list.appendChild(svcHeader);
        for (const t of serviceTemplates) _orgRenderCard(list, t);
    }

    if (agileTemplates.length === 0 && serviceTemplates.length === 0) {
        list.innerHTML = '<div class="org-empty">No teams created yet. Click <b>+ TEAM</b> to build your first team.</div>';
    }
}

function _orgRenderCard(list, t) {
    const card = document.createElement('div');
    card.className = 'org-team-card';
    const nodeCount = (t.nodes || []).length;
    const levels = new Set((t.nodes || []).map(n => n.level || 0));
    const maxLevel = levels.size;
    const estCost = (0.01 + (nodeCount - 1) * 0.001 + (maxLevel - 1) * 0.001).toFixed(3);

    // Build agent tile flow by level
    const agentMap = {};
    if (_ceoAgents) for (const a of _ceoAgents) agentMap[a.id] = a;
    const levelGroups = {};
    for (const n of (t.nodes || [])) {
        const lvl = n.level || 0;
        if (!levelGroups[lvl]) levelGroups[lvl] = [];
        levelGroups[lvl].push(n.agent_id);
    }
    let flowHtml = '';
    const sortedLevels = Object.keys(levelGroups).sort((a, b) => a - b);
    for (let i = 0; i < sortedLevels.length; i++) {
        const lvl = sortedLevels[i];
        const labelMap = { '0': 'LEAD', '1': 'CORE', '2': 'OPS', '3': 'COMMS', '4': 'FINANCE' };
        const label = labelMap[lvl] || `L${lvl}`;
        let tilesHtml = '';
        for (const aid of levelGroups[lvl]) {
            const ag = agentMap[aid] || {};
            const col = ag.colour || '#00e5ff';
            const tier = ag.model_tier || (ag.provider === 'claude' ? 'strategic' : ag.provider === 'gemini' ? 'research' : 'execution');
            const tierLabel = tier === 'strategic' ? 'STR' : tier === 'research' ? 'RES' : 'EXE';
            const tierClass = `org-tile-tier-${tier}`;
            tilesHtml += `
                <div class="org-agent-tile" style="--tile-accent:${col}">
                    <div class="org-tile-icon">${_SVG(ag.icon || 'user', 18)}</div>
                    <div class="org-tile-info">
                        <div class="org-tile-name">${_escHtml(ag.name || aid)}</div>
                        <div class="org-tile-role">${_escHtml(ag.role || '')}</div>
                    </div>
                    <span class="org-tile-tier ${tierClass}">${tierLabel}</span>
                </div>`;
        }
        flowHtml += `<div class="org-flow-level">
            <span class="org-flow-level-tag">${label}</span>
            <div class="org-flow-level-tiles">${tilesHtml}</div>
        </div>`;
        if (i < sortedLevels.length - 1) {
            flowHtml += '<div class="org-flow-arrow"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12l7 7 7-7"/></svg></div>';
        }
    }

    card.innerHTML = `
        <div class="org-team-card-header">
            <span class="org-team-card-icon">${_SVG('layers', 16)}</span>
            <span class="org-team-card-name">${_escHtml(t.name)}</span>
            <span class="org-team-card-meta">${nodeCount} agents · ${maxLevel} levels · ~$${estCost}</span>
        </div>
        <div class="org-team-card-desc">${_escHtml(t.description || '')}</div>
        <div class="org-team-card-flow">${flowHtml}</div>
        <div class="org-team-card-actions">
            <input type="text" class="org-team-directive-input" placeholder="Enter directive for this team..." autocomplete="off"/>
            <button class="org-btn org-btn-run" title="Run organisation">▶ RUN</button>
            <button class="org-btn org-btn-edit" title="Edit team">✎</button>
            <button class="org-btn org-btn-del" title="Delete team">✕</button>
        </div>
    `;

    // Wire up buttons
    const runBtn = card.querySelector('.org-btn-run');
    const editBtn = card.querySelector('.org-btn-edit');
    const delBtn = card.querySelector('.org-btn-del');
    const directiveInput = card.querySelector('.org-team-directive-input');

    runBtn.addEventListener('click', () => {
        const directive = directiveInput.value.trim();
        if (!directive) { directiveInput.focus(); directiveInput.style.borderColor = '#ff4081'; return; }
        directiveInput.style.borderColor = '';
        _orgStartRun(t.id, directive);
    });
    directiveInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && directiveInput.value.trim()) runBtn.click();
    });
    editBtn.addEventListener('click', () => _orgShowTeamModal(t));
    delBtn.addEventListener('click', () => _orgDeleteTeam(t.id));

    list.appendChild(card);
}

// ── Agent Creator Modal ──
function _orgShowAgentModal() {
    const modal = document.getElementById('org-agent-modal');
    if (modal) modal.style.display = 'flex';
    // Clear fields
    ['org-agent-name', 'org-agent-role', 'org-agent-desc', 'org-agent-prompt'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    const tierSel = document.getElementById('org-agent-tier');
    if (tierSel) tierSel.value = 'execution';
    const colourInp = document.getElementById('org-agent-colour');
    if (colourInp) colourInp.value = '#00e5ff';
}

function _orgHideAgentModal() {
    const modal = document.getElementById('org-agent-modal');
    if (modal) modal.style.display = 'none';
}

async function _orgCreateAgent() {
    const name = document.getElementById('org-agent-name')?.value.trim();
    const role = document.getElementById('org-agent-role')?.value.trim();
    const desc = document.getElementById('org-agent-desc')?.value.trim();
    const tier = document.getElementById('org-agent-tier')?.value || 'execution';
    const icon = document.getElementById('org-agent-icon')?.value || 'user';
    const colour = document.getElementById('org-agent-colour')?.value || '#00e5ff';
    const prompt = document.getElementById('org-agent-prompt')?.value.trim();

    if (!name) { document.getElementById('org-agent-name')?.focus(); return; }

    const saveBtn = document.getElementById('org-agent-save');
    if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'CREATING...'; }

    try {
        const resp = await fetch('/api/agents/custom', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, role, description: desc, model_tier: tier, icon, colour, system_prompt: prompt }),
        });
        const data = await resp.json();
        if (data.error) {
            alert('Error: ' + data.error);
        } else {
            _orgHideAgentModal();
            // Invalidate agent cache so CEO panel + ORG panel re-fetch
            _ceoAgents = null;
            _orgCustomAgents = null;
            // Re-render CEO agent nodes to include the new agent
            const nodesWrap = document.getElementById('wf-graph-nodes');
            if (nodesWrap) { nodesWrap.innerHTML = ''; }
            _ceoInitPanel();
            // Reload team modal palette if open
            _orgLoadAgentPalette();
        }
    } catch (e) {
        alert('Failed to create agent: ' + e.message);
    } finally {
        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'CREATE AGENT'; }
    }
}

// ── Team Builder Modal ──
async function _orgShowTeamModal(existing = null) {
    const modal = document.getElementById('org-team-modal');
    if (modal) modal.style.display = 'flex';

    const titleEl = document.getElementById('org-team-modal-title');
    const nameInput = document.getElementById('org-team-name');
    const descInput = document.getElementById('org-team-desc');

    if (existing) {
        _orgEditId = existing.id;
        if (titleEl) titleEl.textContent = 'EDIT TEAM';
        if (nameInput) nameInput.value = existing.name || '';
        if (descInput) descInput.value = existing.description || '';
        // Populate levels with existing nodes
        _orgPopulateLevels(existing.nodes || []);
    } else {
        _orgEditId = null;
        if (titleEl) titleEl.textContent = 'CREATE TEAM';
        if (nameInput) nameInput.value = '';
        if (descInput) descInput.value = '';
        // Clear levels
        document.querySelectorAll('.org-level-slots').forEach(el => el.innerHTML = '');
    }

    await _orgLoadAgentPalette();
    _orgUpdateCostEstimate();

    // Wire the inline + AGENT button inside the palette header
    const inlineAgentBtn = document.getElementById('org-team-new-agent-btn');
    if (inlineAgentBtn) {
        inlineAgentBtn.onclick = () => {
            _orgShowAgentModal();
        };
    }
}

function _orgHideTeamModal() {
    const modal = document.getElementById('org-team-modal');
    if (modal) modal.style.display = 'none';
    _orgEditId = null;
}

async function _orgLoadAgentPalette() {
    const paletteList = document.getElementById('org-team-palette-list');
    if (!paletteList) return;

    paletteList.innerHTML = '<div style="color:var(--text-dim);padding:8px;font-size:10px;">Loading agents...</div>';

    // Fetch all agents (built-in + custom)
    try {
        const resp = await fetch('/api/ceo/agents');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const agents = await resp.json();
        if (!Array.isArray(agents) || agents.length === 0) {
            paletteList.innerHTML = '<div style="color:var(--text-dim);padding:8px;font-size:10px;">No agents found. Create agents in the Agent Orchestrator panel first.</div>';
            return;
        }
        // Also update the cached agent list for other panels
        _ceoAgents = agents;
        paletteList.innerHTML = '';

        for (const agent of agents) {
            const item = document.createElement('div');
            item.className = 'org-palette-agent';
            item.dataset.agentId = agent.id;
            item.style.setProperty('--agent-colour', agent.colour || '#00e5ff');
            const tierLabel = agent.model_tier === 'strategic' ? 'STR' : agent.model_tier === 'research' ? 'RES' : 'EXE';
            item.innerHTML = `
                <span class="org-palette-icon">${_SVG(agent.icon || 'user', 14)}</span>
                <span class="org-palette-name">${_escHtml(agent.name)}</span>
                <span class="org-palette-tier" style="font-size:7px;padding:1px 4px;border-radius:2px;background:rgba(0,200,255,0.1);color:#6b8899;margin-left:auto">${tierLabel}</span>
                ${agent.custom ? '<span class="org-palette-badge">CUSTOM</span>' : ''}
            `;
            item.title = `${agent.role || ''} — ${agent.description || ''}\nClick to add to team`;
            item.draggable = true;
            item.addEventListener('dragstart', e => {
                e.dataTransfer.setData('text/plain', agent.id);
                e.dataTransfer.effectAllowed = 'copy';
            });
            // Also support click to add to first available level
            item.addEventListener('click', () => _orgAddAgentToLevel(agent.id, agent));
            paletteList.appendChild(item);
        }
        console.log(`[ORG] Agent palette loaded: ${agents.length} agents`);
    } catch (e) {
        console.error('[ORG] Failed to load agent palette:', e);
        paletteList.innerHTML = '<div style="color:#ff3355;padding:8px;font-size:10px;">Failed to load agents. Check server connection.</div>';
    }
}

function _orgAddAgentToLevel(agentId, agent, targetLevel = null) {
    // Find which level to add to — prefer targetLevel, otherwise first with fewest items
    const levels = document.querySelectorAll('.org-level-slots');
    let target = null;

    if (targetLevel !== null) {
        target = document.querySelector(`.org-level-slots[data-level="${targetLevel}"]`);
    } else {
        // Check if agent already exists in any level
        const existing = document.querySelector(`.org-team-agent[data-agent-id="${agentId}"]`);
        if (existing) return; // Already added

        // Add to level with fewest agents, preferring higher levels
        let minCount = Infinity;
        levels.forEach(l => {
            const count = l.querySelectorAll('.org-team-agent').length;
            if (count < minCount) { minCount = count; target = l; }
        });
    }
    if (!target) return;

    // Check if already in this level
    if (target.querySelector(`.org-team-agent[data-agent-id="${agentId}"]`)) return;

    const chip = document.createElement('div');
    chip.className = 'org-team-agent';
    chip.dataset.agentId = agentId;
    chip.style.setProperty('--agent-colour', agent?.colour || '#00e5ff');
    chip.innerHTML = `
        <span class="org-team-agent-icon">${_SVG(agent?.icon || 'user', 14)}</span>
        <span class="org-team-agent-name">${_escHtml(agent?.name || agentId)}</span>
        <button class="org-team-agent-remove" title="Remove">✕</button>
    `;
    chip.querySelector('.org-team-agent-remove').addEventListener('click', (e) => {
        e.stopPropagation();
        chip.remove();
        _orgUpdateCostEstimate();
    });

    // Make draggable between levels
    chip.draggable = true;
    chip.addEventListener('dragstart', e => {
        e.dataTransfer.setData('text/plain', agentId);
        chip.classList.add('dragging');
    });
    chip.addEventListener('dragend', () => chip.classList.remove('dragging'));

    target.appendChild(chip);
    _orgUpdateCostEstimate();
}

function _orgPopulateLevels(nodes) {
    // Clear all levels first
    document.querySelectorAll('.org-level-slots').forEach(el => el.innerHTML = '');

    // We need agent info for icons/names — use cached _ceoAgents or fetch
    const agentMap = {};
    if (_ceoAgents) {
        for (const a of _ceoAgents) agentMap[a.id] = a;
    }

    for (const node of nodes) {
        const agent = agentMap[node.agent_id] || { id: node.agent_id, name: node.agent_id, icon: 'user', colour: '#00e5ff' };
        _orgAddAgentToLevel(node.agent_id, agent, node.level || 0);
    }
}

function _orgUpdateCostEstimate() {
    const estEl = document.getElementById('org-cost-estimate');
    if (!estEl) return;
    let count = 0;
    document.querySelectorAll('.org-level-slots .org-team-agent').forEach(() => count++);
    // Rough estimate: first agent Claude ($0.01), rest GPT-4o-mini ($0.001), + compression
    const levels = document.querySelectorAll('.org-level-slots');
    let levelCount = 0;
    levels.forEach(l => { if (l.querySelectorAll('.org-team-agent').length > 0) levelCount++; });
    const est = count > 0 ? (0.01 + Math.max(0, count - 1) * 0.001 + Math.max(0, levelCount - 1) * 0.001) : 0;
    estEl.textContent = `EST. COST: ~$${est.toFixed(3)}`;
}

async function _orgSaveTeam() {
    const name = document.getElementById('org-team-name')?.value.trim();
    const desc = document.getElementById('org-team-desc')?.value.trim();
    if (!name) { document.getElementById('org-team-name')?.focus(); return; }

    // Collect nodes from levels
    const nodes = [];
    const edges = [];
    document.querySelectorAll('.org-level-slots').forEach(levelSlot => {
        const level = parseInt(levelSlot.dataset.level || '0');
        levelSlot.querySelectorAll('.org-team-agent').forEach(chip => {
            nodes.push({ agent_id: chip.dataset.agentId, level });
        });
    });

    if (nodes.length === 0) { alert('Add at least one agent to the team.'); return; }

    // Auto-generate edges: each level 0 agent directs all level 1 agents, etc.
    for (let lvl = 0; lvl < 3; lvl++) {
        const parents = nodes.filter(n => n.level === lvl);
        const children = nodes.filter(n => n.level === lvl + 1);
        for (const p of parents) {
            for (const c of children) {
                edges.push({ from: p.agent_id, to: c.agent_id, type: 'directs' });
            }
        }
    }

    const saveBtn = document.getElementById('org-team-save');
    if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'SAVING...'; }

    try {
        const url = _orgEditId ? `/api/org/templates/${_orgEditId}` : '/api/org/templates';
        const method = _orgEditId ? 'PUT' : 'POST';
        const resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description: desc, nodes, edges }),
        });
        const data = await resp.json();
        if (data.error) {
            alert('Error: ' + data.error);
        } else {
            _orgHideTeamModal();
            await _orgLoadTemplates();
        }
    } catch (e) {
        alert('Failed to save team: ' + e.message);
    } finally {
        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'SAVE TEAM'; }
    }
}

async function _orgDeleteTeam(templateId) {
    if (!confirm('Delete this team?')) return;
    try {
        await fetch(`/api/org/templates/${templateId}/delete`, { method: 'POST' });
        await _orgLoadTemplates();
    } catch (e) {
        console.error('[ORG] Delete failed:', e);
    }
}

// ── Org Execution ──
async function _orgStartRun(orgId, directive) {
    const runView = document.getElementById('org-run-view');
    const teamsList = document.getElementById('org-teams-list');

    try {
        const resp = await fetch('/api/org/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ org_id: orgId, directive }),
        });
        const data = await resp.json();
        if (data.error) { alert('Error: ' + data.error); return; }

        _activeOrgRun = data;
        if (teamsList) teamsList.style.display = 'none';
        if (runView) runView.style.display = 'block';
        _orgRenderRun();

        // Start polling if still running
        if (data.status === 'running') _orgStartRunPolling();
    } catch (e) {
        alert('Failed to start run: ' + e.message);
    }
}

function _orgRenderRun() {
    if (!_activeOrgRun) return;

    const titleEl = document.getElementById('org-run-title');
    const costEl = document.getElementById('org-run-cost');
    const chartEl = document.getElementById('org-run-chart');
    const controlsEl = document.getElementById('org-run-controls');
    const levelInfoEl = document.getElementById('org-run-level-info');

    if (titleEl) titleEl.textContent = `${_activeOrgRun.org_name || 'CEO RUN'} — ${_activeOrgRun.directive?.substring(0, 60) || ''}`;
    if (costEl) costEl.textContent = `$${(_activeOrgRun.total_cost_usd || 0).toFixed(3)}`;

    // Build the agent map for icons/names
    const agentMap = {};
    if (_ceoAgents) for (const a of _ceoAgents) agentMap[a.id] = a;

    // Render levels
    if (chartEl) {
        const nodes = _activeOrgRun.nodes || [];
        const levels = {};
        for (const n of nodes) {
            const lvl = n.level || 0;
            if (!levels[lvl]) levels[lvl] = [];
            levels[lvl].push(n);
        }

        const labelMap = { '0': 'LEAD', '1': 'CORE', '2': 'OPS', '3': 'COMMS', '4': 'FINANCE' };
        let html = '';
        const sortedLevels = Object.entries(levels).sort((a, b) => a[0] - b[0]);
        for (let li = 0; li < sortedLevels.length; li++) {
            const [lvl, levelNodes] = sortedLevels[li];
            const tag = labelMap[lvl] || `L${lvl}`;
            html += `<div class="org-flow-level" style="padding:6px 0">
                <span class="org-flow-level-tag">${tag}</span>
                <div class="org-flow-level-tiles" style="gap:8px">`;
            for (const node of levelNodes) {
                const agent = agentMap[node.agent_id] || {};
                const col = agent.colour || '#00e5ff';
                const tier = agent.model_tier || (agent.provider === 'claude' ? 'strategic' : agent.provider === 'gemini' ? 'research' : 'execution');
                const tierLabel = tier === 'strategic' ? 'STR' : tier === 'research' ? 'RES' : 'EXE';
                const tierClass = `org-tile-tier-${tier}`;
                const statusClass = node.status === 'complete' ? 'complete' : node.status === 'running' ? 'running' : node.status === 'error' ? 'error' : 'pending';
                const statusIcon = node.status === 'complete' ? '✓' : node.status === 'running' ? '◌' : node.status === 'error' ? '✗' : '○';
                const costStr = node.cost_usd > 0 ? `$${node.cost_usd.toFixed(3)}` : '';
                html += `
                    <div class="org-agent-tile org-run-tile-${statusClass}" style="--tile-accent:${col}; flex-direction:column; align-items:stretch; max-width:280px; min-width:200px">
                        <div style="display:flex; align-items:center; gap:8px">
                            <div class="org-tile-icon">${_SVG(agent.icon || 'user', 18)}</div>
                            <div class="org-tile-info">
                                <div class="org-tile-name">${_escHtml(agent.name || node.agent_id)}</div>
                                <div class="org-tile-role">${_escHtml(agent.role || '')}</div>
                            </div>
                            <span class="org-tile-tier ${tierClass}">${tierLabel}</span>
                            <span class="org-run-status-badge org-run-status-${statusClass}">${statusIcon}</span>
                        </div>
                        ${costStr ? `<div style="font-size:7px;font-family:var(--font-mono);color:var(--text-dim);margin-top:4px">${costStr}</div>` : ''}
                        ${node.output ? `<div class="org-run-node-output">${_escHtml(node.output.substring(0, 300))}${node.output.length > 300 ? '…' : ''}</div>` : ''}
                        ${node.brief_in && node.status !== 'pending' ? `<div class="org-run-node-brief"><b>BRIEF:</b> ${_escHtml(node.brief_in.substring(0, 150))}…</div>` : ''}
                    </div>`;
            }
            html += '</div></div>';
            if (li < sortedLevels.length - 1) {
                html += '<div class="org-flow-arrow"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12l7 7 7-7"/></svg></div>';
            }
        }
        chartEl.innerHTML = html;
    }

    // Show/hide approval controls
    if (_activeOrgRun.status === 'awaiting_approval') {
        if (controlsEl) controlsEl.style.display = 'block';
        if (levelInfoEl) {
            const nextLevel = _activeOrgRun.approval_level || (_activeOrgRun.current_level + 1);
            levelInfoEl.textContent = `Level ${_activeOrgRun.current_level} complete — review outputs before approving Level ${nextLevel}`;
        }
    } else if (_activeOrgRun.status === 'complete') {
        if (controlsEl) controlsEl.style.display = 'block';
        if (levelInfoEl) levelInfoEl.textContent = '✓ CEO run complete';
        const approveBtn = document.getElementById('org-run-approve');
        const rejectBtn = document.getElementById('org-run-reject');
        if (approveBtn) approveBtn.style.display = 'none';
        if (rejectBtn) { rejectBtn.textContent = '← BACK'; rejectBtn.onclick = _orgCloseRun; }
    } else if (_activeOrgRun.status === 'rejected') {
        if (controlsEl) controlsEl.style.display = 'block';
        if (levelInfoEl) levelInfoEl.textContent = '✕ CEO run stopped';
        const approveBtn = document.getElementById('org-run-approve');
        const rejectBtn = document.getElementById('org-run-reject');
        if (approveBtn) approveBtn.style.display = 'none';
        if (rejectBtn) { rejectBtn.textContent = '← BACK'; rejectBtn.onclick = _orgCloseRun; }
    } else {
        if (controlsEl) controlsEl.style.display = 'none';
    }
}

async function _orgRunApprove() {
    if (!_activeOrgRun) return;
    const approveBtn = document.getElementById('org-run-approve');
    if (approveBtn) { approveBtn.disabled = true; approveBtn.textContent = 'EXECUTING...'; }

    try {
        const resp = await fetch(`/api/org/run/${_activeOrgRun.id}/approve`, { method: 'POST' });
        const data = await resp.json();
        if (data.error) { alert('Error: ' + data.error); return; }
        _activeOrgRun = data;
        _orgRenderRun();
        if (data.status === 'running') _orgStartRunPolling();
    } catch (e) {
        alert('Approve failed: ' + e.message);
    } finally {
        if (approveBtn) { approveBtn.disabled = false; approveBtn.textContent = '✓ APPROVE & CONTINUE'; }
    }
}

async function _orgRunReject() {
    if (!_activeOrgRun) return;
    try {
        const resp = await fetch(`/api/org/run/${_activeOrgRun.id}/reject`, { method: 'POST' });
        const data = await resp.json();
        _activeOrgRun = data;
        _orgRenderRun();
        _orgStopRunPolling();
    } catch (e) {
        alert('Reject failed: ' + e.message);
    }
}

function _orgCloseRun() {
    _activeOrgRun = null;
    _orgStopRunPolling();
    const runView = document.getElementById('org-run-view');
    const teamsList = document.getElementById('org-teams-list');
    if (runView) runView.style.display = 'none';
    if (teamsList) teamsList.style.display = '';
    // Reset buttons
    const approveBtn = document.getElementById('org-run-approve');
    const rejectBtn = document.getElementById('org-run-reject');
    if (approveBtn) { approveBtn.style.display = ''; approveBtn.textContent = '✓ APPROVE & CONTINUE'; }
    if (rejectBtn) { rejectBtn.style.display = ''; rejectBtn.textContent = '✕ STOP'; rejectBtn.onclick = _orgRunReject; }
}

function _orgStartRunPolling() {
    _orgStopRunPolling();
    _orgRunPollTimer = setInterval(async () => {
        if (!_activeOrgRun) { _orgStopRunPolling(); return; }
        try {
            const resp = await fetch(`/api/org/run/${_activeOrgRun.id}`);
            const data = await resp.json();
            if (data.error) return;
            _activeOrgRun = data;
            _orgRenderRun();
            if (data.status !== 'running') _orgStopRunPolling();
        } catch (e) { /* ignore poll errors */ }
    }, 2000);
}

function _orgStopRunPolling() {
    if (_orgRunPollTimer) { clearInterval(_orgRunPollTimer); _orgRunPollTimer = null; }
}

// Set up drag-and-drop on level slots
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        document.querySelectorAll('.org-level-slots').forEach(slot => {
            slot.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; slot.classList.add('drag-over'); });
            slot.addEventListener('dragleave', () => slot.classList.remove('drag-over'));
            slot.addEventListener('drop', async e => {
                e.preventDefault();
                slot.classList.remove('drag-over');
                const agentId = e.dataTransfer.getData('text/plain');
                if (!agentId) return;
                // Fetch agent info
                let agent = null;
                if (_ceoAgents) agent = _ceoAgents.find(a => a.id === agentId);
                if (!agent) {
                    try {
                        const resp = await fetch('/api/ceo/agents');
                        const agents = await resp.json();
                        agent = agents.find(a => a.id === agentId);
                    } catch (e) { /* ignore */ }
                }
                // Remove from any other level first
                document.querySelectorAll(`.org-team-agent[data-agent-id="${agentId}"]`).forEach(el => el.remove());
                _orgAddAgentToLevel(agentId, agent || { id: agentId, name: agentId }, parseInt(slot.dataset.level || '0'));
            });
        });
    }, 500);
});

// ── CEO Orchestration Module ──────────────────────────────────────
let _ceoAgents = null;
let _lastPipeData = null;  // Store latest pipe data for stage click access

// Pipeline chain order — agents rendered left-to-right in this sequence
// Must match the "full" pipeline template order in server.py
const _DEFAULT_CHAIN_ORDER = ['researcher', 'analyst', 'visionary', 'strategist', 'product', 'cto', 'risk', 'chief_of_staff'];
let _CHAIN_ORDER = [..._DEFAULT_CHAIN_ORDER];

async function _ceoInitPanel() {
    console.log('[CEO] Initialising agent panel...');
    const nodesWrap = document.getElementById('wf-graph-nodes');
    if (!nodesWrap) { console.warn('[CEO] wf-graph-nodes not found in DOM'); return; }

    // Wire up + AGENT button and modal (lives in CEO panel)
    const createAgentBtn = document.getElementById('ceo-create-agent-btn');
    if (createAgentBtn) createAgentBtn.onclick = _orgShowAgentModal;
    const agentModalClose = document.getElementById('org-agent-modal-close');
    const agentSaveBtn = document.getElementById('org-agent-save');
    if (agentModalClose) agentModalClose.onclick = _orgHideAgentModal;
    if (agentSaveBtn) agentSaveBtn.onclick = _orgCreateAgent;

    // Fetch agent definitions if not cached
    if (!_ceoAgents) {
        try {
            const resp = await fetch('/api/ceo/agents');
            if (!resp.ok) { console.error('[CEO] /api/ceo/agents returned', resp.status); }
            _ceoAgents = await resp.json();
            console.log('[CEO] Loaded', _ceoAgents.length, 'agents:', _ceoAgents.map(a => a.id));
        } catch (e) {
            console.error('[CEO] Failed to load agents:', e);
            nodesWrap.innerHTML = '<div class="feed-empty">FAILED TO LOAD AGENTS</div>';
            return;
        }
    }

    // Only render if nodes are empty (avoid re-render on panel reopen)
    // But still allow pipeline rebuild check below
    const alreadyRendered = !!nodesWrap.querySelector('.wf-node[data-agent-id]');
    if (alreadyRendered) {
        console.log('[CEO] Nodes already rendered, checking for pending pipeline...');
        // Still check if there's pending pipeline data to rebuild
        if (_lastPipeData && _lastPipeData.stages) {
            _rebuildChainNodes(_lastPipeData.stages);
            _ceoPipelineUpdateUI(_lastPipeData);
        }
        return;
    }

    nodesWrap.innerHTML = '';

    // Sort agents: chain-order first, then remaining
    const agentMap = {};
    for (const a of _ceoAgents) agentMap[a.id] = a;
    const chainAgents = _CHAIN_ORDER.filter(id => agentMap[id]).map(id => agentMap[id]);
    const otherAgents = _ceoAgents.filter(a => !_CHAIN_ORDER.includes(a.id));

    // ─── Pipeline chain row ───
    const chainRow = document.createElement('div');
    chainRow.className = 'wf-chain-row';

    // Directive source node (first in chain)
    const srcNode = document.createElement('div');
    srcNode.className = 'wf-node wf-node-src wf-chain-node';
    srcNode.id = 'wf-src-node';
    srcNode.innerHTML = `
        <div class="wf-node-header">
            <div class="wf-node-icon">${_SVG('broadcast', 18)}</div>
            <div class="wf-node-title">DIRECTIVE</div>
        </div>
        <div class="wf-node-body">
            <div class="wf-node-desc" id="wf-src-task" style="text-align:center;color:var(--text-dim);font-size:9px;">Awaiting directive...</div>
        </div>
        <div class="wf-port wf-port-out" id="wf-port-src-out"></div>
    `;
    chainRow.appendChild(srcNode);

    // Chain agent nodes
    chainAgents.forEach((agent, i) => {
        const node = document.createElement('div');
        node.className = 'wf-node wf-chain-node';
        node.style.setProperty('--node-colour', agent.colour || 'var(--cyan)');
        node.dataset.agentId = agent.id;
        node.dataset.chainIdx = i;
        node.innerHTML = `
            <div class="wf-port wf-port-in" id="wf-port-${agent.id}-in"></div>
            <div class="wf-node-header">
                <div class="wf-node-icon">${_SVG(agent.icon || 'search', 18)}</div>
                <div class="wf-node-title">${agent.name}</div>
                <div class="wf-node-status" id="wf-status-${agent.id}"></div>
            </div>
            <div class="wf-node-body">
                <div class="wf-node-role">${agent.role}</div>
                <div class="wf-node-desc">${agent.description}</div>
                <div class="wf-node-model">MODEL <b>${agent.model}</b></div>
            </div>
            <div class="wf-node-input-row">
                <input type="text" class="wf-node-input" placeholder="Task..." autocomplete="off" />
                <button class="wf-node-send">▶</button>
            </div>
            <button class="wf-node-run-btn" id="wf-run-btn-${agent.id}" style="display:none;">▶ RUN</button>
            <div class="wf-node-output" id="wf-output-${agent.id}"></div>
            <div class="wf-port wf-port-out" id="wf-port-${agent.id}-out"></div>
        `;

        // Wire up send
        const input = node.querySelector('.wf-node-input');
        const sendBtn = node.querySelector('.wf-node-send');
        const sendFn = () => _ceoDispatch(agent.id, input, node);
        sendBtn.addEventListener('click', sendFn);
        input.addEventListener('keydown', e => { if (e.key === 'Enter' && input.value.trim()) sendFn(); });

        // Click header/body to view stage report
        const header = node.querySelector('.wf-node-header');
        const body = node.querySelector('.wf-node-body');
        if (header) { header.style.cursor = 'pointer'; header.addEventListener('click', () => _ceoPipelineShowStageReport(agent.id)); }
        if (body) { body.style.cursor = 'pointer'; body.addEventListener('click', () => _ceoPipelineShowStageReport(agent.id)); }

        chainRow.appendChild(node);
    });
    nodesWrap.appendChild(chainRow);

    // ─── Other agents row (CTO, Sales, etc.) ───
    if (otherAgents.length > 0) {
        const otherLabel = document.createElement('div');
        otherLabel.className = 'wf-other-label';
        otherLabel.textContent = 'STANDALONE AGENTS';
        nodesWrap.appendChild(otherLabel);

        const otherRow = document.createElement('div');
        otherRow.className = 'wf-other-row';
        for (const agent of otherAgents) {
            const node = document.createElement('div');
            node.className = 'wf-node wf-other-node';
            node.style.setProperty('--node-colour', agent.colour || 'var(--cyan)');
            node.dataset.agentId = agent.id;
            node.innerHTML = `
                <div class="wf-node-header">
                    <div class="wf-node-icon">${_SVG(agent.icon || 'search', 18)}</div>
                    <div class="wf-node-title">${agent.name}</div>
                    <div class="wf-node-status" id="wf-status-${agent.id}"></div>
                </div>
                <div class="wf-node-body">
                    <div class="wf-node-role">${agent.role}</div>
                    <div class="wf-node-desc">${agent.description}</div>
                    <div class="wf-node-model">MODEL <b>${agent.model}</b></div>
                </div>
                <div class="wf-node-input-row">
                    <input type="text" class="wf-node-input" placeholder="Task..." autocomplete="off" />
                    <button class="wf-node-send">▶</button>
                </div>
                <div class="wf-node-output" id="wf-output-${agent.id}"></div>
            `;
            const input = node.querySelector('.wf-node-input');
            const sendBtn = node.querySelector('.wf-node-send');
            const sendFn = () => _ceoDispatch(agent.id, input, node);
            sendBtn.addEventListener('click', sendFn);
            input.addEventListener('keydown', e => { if (e.key === 'Enter' && input.value.trim()) sendFn(); });
            otherRow.appendChild(node);
        }
        nodesWrap.appendChild(otherRow);
    }

    // Wire up pipeline launcher
    const pipeInput = document.getElementById('ceo-pipeline-input');
    const pipeBtn = document.getElementById('ceo-pipeline-btn');
    const pipeSelect = document.getElementById('ceo-template-select');
    if (pipeBtn && pipeInput) {
        const pipeFn = () => _ceoPipelineLaunch(pipeInput, pipeSelect);
        pipeBtn.onclick = pipeFn;
        pipeInput.onkeydown = e => { if (e.key === 'Enter' && pipeInput.value.trim()) pipeFn(); };
    }

    // Populate template dropdown with built-in + custom workflows
    _populateTemplateDropdown();
    // Wire up gate approve/reject buttons
    const approveBtn = document.getElementById('ceo-pipe-approve');
    const rejectBtn = document.getElementById('ceo-pipe-reject');
    if (approveBtn) approveBtn.onclick = () => _ceoPipelineApprove();
    if (rejectBtn) rejectBtn.onclick = () => _ceoPipelineReject();

    // Draw SVG noodles after DOM layout settles
    requestAnimationFrame(() => { requestAnimationFrame(_drawNoodles); });

    // If a pipeline is already active (launched from Workflows panel), rebuild chain to match
    if (_lastPipeData && _lastPipeData.stages) {
        _rebuildChainNodes(_lastPipeData.stages);
        _ceoPipelineUpdateUI(_lastPipeData);
    }

    // Init workflow activity view
    _wfInit();
}

// ── Template dropdown — dynamically populated with built-in + custom ────
let _templateCache = null;
let _customWfCache = null;

async function _populateTemplateDropdown() {
    const select = document.getElementById('ceo-template-select');
    if (!select) return;

    // Fetch built-in templates + custom workflows in parallel
    const [templates, customWfs] = await Promise.all([
        api('/api/ceo/pipeline/templates'),
        api('/api/ceo/custom-workflows'),
    ]);

    _templateCache = templates || {};
    _customWfCache = customWfs || {};

    const prevVal = select.value;
    select.innerHTML = '';

    // Built-in templates
    const builtInKeys = Object.keys(_templateCache);
    if (builtInKeys.length > 0) {
        const grp = document.createElement('optgroup');
        grp.label = 'BUILT-IN';
        for (const key of builtInKeys) {
            const meta = _WF_TEMPLATE_META[key];
            const label = meta ? meta.label.toUpperCase() : key.toUpperCase();
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = `◈ ${label}`;
            grp.appendChild(opt);
        }
        select.appendChild(grp);
    }

    // Custom workflows
    const customKeys = Object.keys(_customWfCache);
    if (customKeys.length > 0) {
        const grp = document.createElement('optgroup');
        grp.label = 'CUSTOM';
        for (const key of customKeys) {
            const cw = _customWfCache[key];
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = `★ ${(cw.name || key).toUpperCase()}`;
            grp.appendChild(opt);
        }
        select.appendChild(grp);
    }

    // Restore previous selection if still valid, otherwise default to first
    if (prevVal && select.querySelector(`option[value="${prevVal}"]`)) {
        select.value = prevVal;
    } else if (select.options.length > 0) {
        select.selectedIndex = 0;
    }

    // Trigger change to update the node graph
    _ceoTemplateChanged(select.value);
}

async function _ceoTemplateChanged(templateKey) {
    // Ensure agents are loaded
    if (!_ceoAgents) {
        try {
            const agResp = await fetch('/api/ceo/agents');
            _ceoAgents = await agResp.json();
        } catch (e) { console.error('[CEO] Failed to load agents:', e); return; }
    }
    // Ensure caches are populated
    if (!_templateCache) {
        try {
            const tResp = await fetch('/api/ceo/pipeline/templates');
            _templateCache = await tResp.json();
        } catch (e) { console.warn('[CEO] Template fetch failed:', e); return; }
    }
    if (!_customWfCache) {
        try { _customWfCache = await api('/api/ceo/custom-workflows') || {}; } catch { _customWfCache = {}; }
    }

    // Look up in built-in first, then custom workflows
    let stages = _templateCache[templateKey];
    if (!stages && _customWfCache[templateKey]) {
        // Convert custom workflow agents to stage format for the node graph
        const cw = _customWfCache[templateKey];
        stages = (cw.agents || []).map(a => ({
            agent_id: a.agent_id,
            agent_name: a.agent_name || a.agent_id,
            description: a.task_hint || cw.description || '',
            gate: false,
        }));
    }

    if (stages && stages.length) {
        _rebuildChainNodes(stages);
        _activePipelineId = null;
        _lastPipeData = null;
    }
}

/**
 * Rebuild the entire graph — pipeline chain row + standalone agents row.
 * Replaces chain-row DOM, updates _CHAIN_ORDER, redraws noodles.
 */
function _rebuildChainNodes(stages) {
    if (!stages || !stages.length || !_ceoAgents) return;
    const newOrder = stages.map(s => s.agent_id);
    // Skip rebuild if chain already matches
    if (newOrder.length === _CHAIN_ORDER.length && newOrder.every((id, i) => id === _CHAIN_ORDER[i])) return;

    _CHAIN_ORDER = newOrder;
    const agentMap = {};
    for (const a of _ceoAgents) agentMap[a.id] = a;

    const nodesWrap = document.getElementById('wf-graph-nodes');
    if (!nodesWrap) return;

    // Clear entire graph — chain row, other label, other row
    nodesWrap.innerHTML = '';

    // ─── Build new chain row ───
    const chainRow = document.createElement('div');
    chainRow.className = 'wf-chain-row';

    // Directive source node
    const srcNode = document.createElement('div');
    srcNode.className = 'wf-node wf-node-src wf-chain-node';
    srcNode.id = 'wf-src-node';
    srcNode.innerHTML = `
        <div class="wf-node-header">
            <div class="wf-node-icon">${_SVG('broadcast', 18)}</div>
            <div class="wf-node-title">DIRECTIVE</div>
        </div>
        <div class="wf-node-body">
            <div class="wf-node-desc" id="wf-src-task" style="text-align:center;color:var(--text-dim);font-size:9px;">Awaiting directive...</div>
        </div>
        <div class="wf-port wf-port-out" id="wf-port-src-out"></div>
    `;
    chainRow.appendChild(srcNode);

    // Chain agent nodes
    _CHAIN_ORDER.forEach((aid, i) => {
        const agent = agentMap[aid];
        if (!agent) { console.warn('[CEO] Agent not found:', aid); return; }
        const node = document.createElement('div');
        node.className = 'wf-node wf-chain-node';
        node.style.setProperty('--node-colour', agent.colour || 'var(--cyan)');
        node.dataset.agentId = agent.id;
        node.dataset.chainIdx = i;
        node.innerHTML = `
            <div class="wf-port wf-port-in" id="wf-port-${agent.id}-in"></div>
            <div class="wf-node-header">
                <div class="wf-node-icon">${_SVG(agent.icon || 'search', 18)}</div>
                <div class="wf-node-title">${agent.name}</div>
                <div class="wf-node-status" id="wf-status-${agent.id}"></div>
            </div>
            <div class="wf-node-body">
                <div class="wf-node-role">${agent.role}</div>
                <div class="wf-node-desc">${agent.description}</div>
                <div class="wf-node-model">MODEL <b>${agent.model}</b></div>
            </div>
            <div class="wf-node-input-row">
                <input type="text" class="wf-node-input" placeholder="Task..." autocomplete="off" />
                <button class="wf-node-send">▶</button>
            </div>
            <button class="wf-node-run-btn" id="wf-run-btn-${agent.id}" style="display:none;">▶ RUN</button>
            <div class="wf-node-output" id="wf-output-${agent.id}"></div>
            <div class="wf-port wf-port-out" id="wf-port-${agent.id}-out"></div>
        `;
        // Wire up send
        const input = node.querySelector('.wf-node-input');
        const sendBtn = node.querySelector('.wf-node-send');
        const sendFn = () => _ceoDispatch(agent.id, input, node);
        sendBtn.addEventListener('click', sendFn);
        input.addEventListener('keydown', e => { if (e.key === 'Enter' && input.value.trim()) sendFn(); });
        // Click header/body for stage report
        const header = node.querySelector('.wf-node-header');
        const body = node.querySelector('.wf-node-body');
        if (header) { header.style.cursor = 'pointer'; header.addEventListener('click', () => _ceoPipelineShowStageReport(agent.id)); }
        if (body) { body.style.cursor = 'pointer'; body.addEventListener('click', () => _ceoPipelineShowStageReport(agent.id)); }
        chainRow.appendChild(node);
    });

    nodesWrap.appendChild(chainRow);

    // ─── Rebuild standalone agents (those not in the current chain) ───
    const otherAgents = _ceoAgents.filter(a => !_CHAIN_ORDER.includes(a.id));
    if (otherAgents.length > 0) {
        const otherLabel = document.createElement('div');
        otherLabel.className = 'wf-other-label';
        otherLabel.textContent = 'STANDALONE AGENTS';
        nodesWrap.appendChild(otherLabel);

        const otherRow = document.createElement('div');
        otherRow.className = 'wf-other-row';
        for (const agent of otherAgents) {
            const node = document.createElement('div');
            node.className = 'wf-node wf-other-node';
            node.style.setProperty('--node-colour', agent.colour || 'var(--cyan)');
            node.dataset.agentId = agent.id;
            node.innerHTML = `
                <div class="wf-node-header">
                    <div class="wf-node-icon">${_SVG(agent.icon || 'search', 18)}</div>
                    <div class="wf-node-title">${agent.name}</div>
                    <div class="wf-node-status" id="wf-status-${agent.id}"></div>
                </div>
                <div class="wf-node-body">
                    <div class="wf-node-role">${agent.role}</div>
                    <div class="wf-node-desc">${agent.description}</div>
                    <div class="wf-node-model">MODEL <b>${agent.model}</b></div>
                </div>
                <div class="wf-node-input-row">
                    <input type="text" class="wf-node-input" placeholder="Task..." autocomplete="off" />
                    <button class="wf-node-send">▶</button>
                </div>
                <div class="wf-node-output" id="wf-output-${agent.id}"></div>
            `;
            const input = node.querySelector('.wf-node-input');
            const sendBtn = node.querySelector('.wf-node-send');
            const sendFn = () => _ceoDispatch(agent.id, input, node);
            sendBtn.addEventListener('click', sendFn);
            input.addEventListener('keydown', e => { if (e.key === 'Enter' && input.value.trim()) sendFn(); });
            otherRow.appendChild(node);
        }
        nodesWrap.appendChild(otherRow);
    }

    // Redraw noodles after layout
    requestAnimationFrame(() => { requestAnimationFrame(_drawNoodles); });
}

function _drawNoodles() {
    const svg = document.getElementById('wf-graph-svg');
    const wrap = document.getElementById('wf-graph-wrap');
    if (!svg || !wrap) return;

    const wrapRect = wrap.getBoundingClientRect();
    svg.innerHTML = '';
    svg.setAttribute('viewBox', `0 0 ${wrapRect.width} ${wrapRect.height}`);

    // Build the chain: src → researcher → cmo → analyst → publisher → ...
    const chainIds = ['src', ..._CHAIN_ORDER];

    // Find a single consistent Y from the first output port
    const firstOut = document.getElementById(`wf-port-${chainIds[0]}-out`);
    if (!firstOut) return;
    const firstOutRect = firstOut.getBoundingClientRect();
    const lineY = firstOutRect.top + firstOutRect.height / 2 - wrapRect.top;

    for (let i = 0; i < chainIds.length - 1; i++) {
        const fromId = chainIds[i];
        const toId = chainIds[i + 1];
        const outPort = document.getElementById(`wf-port-${fromId}-out`);
        const inPort = document.getElementById(`wf-port-${toId}-in`);
        if (!outPort || !inPort) continue;

        const outRect = outPort.getBoundingClientRect();
        const inRect = inPort.getBoundingClientRect();
        const sx = outRect.left + outRect.width / 2 - wrapRect.left;
        const ex = inRect.left + inRect.width / 2 - wrapRect.left;

        // Perfectly straight horizontal line at the consistent Y
        const d = `M${sx},${lineY} L${ex},${lineY}`;

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('class', 'wf-noodle');
        path.id = `wf-noodle-${toId}`;
        svg.appendChild(path);
    }
}

let _ceoRouteCount = 0;
let _ceoReadCount = 0;

function _ceoUpdateStats() {
    const routeEl = document.getElementById('ceo-stat-routes');
    const readEl = document.getElementById('ceo-stat-reads');
    if (routeEl) routeEl.textContent = _ceoRouteCount;
    if (readEl) readEl.textContent = _ceoReadCount;
}

function _nodeSetStatus(agentId, status) {
    const dot = document.getElementById(`wf-status-${agentId}`);
    if (dot) dot.className = `wf-node-status ${status}`;
    const noodle = document.getElementById(`wf-noodle-${agentId}`);
    if (noodle) noodle.setAttribute('class', `wf-noodle ${status}`);
    const portIn = document.getElementById(`wf-port-${agentId}-in`);
    if (portIn) portIn.className = `wf-port wf-port-in ${status}`;
}

async function _ceoDispatch(agentId, inputEl, nodeEl) {
    const task = inputEl.value.trim();
    if (!task) return;
    inputEl.value = '';

    const output = document.getElementById(`wf-output-${agentId}`);

    // Set working state on node
    _nodeSetStatus(agentId, 'working');
    if (output) { output.classList.add('active'); output.textContent = 'Processing directive...'; }
    _ceoRouteCount++;
    _ceoUpdateStats();
    const _jtId = _jobAdd('agent', `${agentId.toUpperCase()}: ${task.substring(0, 50)}`);

    // Update source node with task
    const srcTask = document.getElementById('wf-src-task');
    if (srcTask) srcTask.textContent = task.substring(0, 80) + (task.length > 80 ? '…' : '');

    // Add live workflow entry
    const agentName = nodeEl.querySelector('.wf-node-title')?.textContent || agentId;
    const wfId = _wfAddLive('dispatch', task, [{ agent_id: agentId, agent_name: agentName, status: 'running' }]);

    // Set master card to working
    const masterStatus = document.querySelector('#ceo-master-card .ceo-master-status');
    if (masterStatus) { masterStatus.className = 'ceo-master-status working'; masterStatus.innerHTML = '<span class="ceo-dot"></span> ROUTING'; }

    // Show progress bar for individual dispatch
    _ceoProgressShow(`${agentName.toUpperCase()} — PROCESSING...`, 0, true);

    try {
        const resp = await fetch('/api/ceo/dispatch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: agentId, task }),
        });
        const data = await resp.json();
        _ceoReadCount++;
        _ceoUpdateStats();

        // Build provider badge
        const providerBadge = data.provider
            ? `<span class="ceo-provider-badge ${data.provider}">${data.provider.toUpperCase()}</span>`
            : '';

        if (data.error) {
            _nodeSetStatus(agentId, 'error');
            if (output) output.textContent = `Error: ${data.error}`;
            _wfUpdateLive(wfId, agentId, 'error', data.error);
            _jobComplete(_jtId, true);
            _ceoProgressComplete(true);
        } else {
            _nodeSetStatus(agentId, 'complete');
            if (output) {
                output.innerHTML = _renderMarkdown(data.response || 'No response') + providerBadge;
            }
            _wfUpdateLive(wfId, agentId, 'complete', data.response, data.model);
            _jobComplete(_jtId);
            _ceoProgressComplete(false);
        }
    } catch (e) {
        _nodeSetStatus(agentId, 'error');
        if (output) output.textContent = `Network error: ${e.message}`;
        _wfUpdateLive(wfId, agentId, 'error', e.message);
        _jobComplete(_jtId, true);
        _ceoProgressComplete(true);
    }

    // Reset master card
    if (masterStatus) { masterStatus.className = 'ceo-master-status ready'; masterStatus.innerHTML = '<span class="ceo-dot"></span> ONLINE'; }
}

// ── Sequential Pipeline ──────────────────────────────────────────
let _activePipelineId = null;
let _pipelinePollTimer = null;
let _pipelineReportData = null;
let _pipelineReportDirective = '';
let _pipelineReportPollTimer = null;
// _lastPipeData declared above in CEO Orchestration Module

// ── Pipeline Persistence Helpers ────────────────────────────────
function _ceoSavePipelineState() {
    if (_activePipelineId) {
        localStorage.setItem('ceo_active_pipeline', _activePipelineId);
    } else {
        localStorage.removeItem('ceo_active_pipeline');
    }
}
function _ceoRestorePipelineState() {
    const savedId = localStorage.getItem('ceo_active_pipeline');
    if (!savedId) return;
    console.log(`[CEO] Restoring pipeline: ${savedId}`);
    _activePipelineId = savedId;
    // Show status bar immediately
    const statusBar = document.getElementById('ceo-pipeline-status');
    const pipeLabel = document.getElementById('ceo-pipe-label');
    const pipeStage = document.getElementById('ceo-pipe-stage');
    if (statusBar) statusBar.style.display = 'inline-flex';
    if (pipeLabel) { pipeLabel.textContent = 'RECONNECTING...'; pipeLabel.className = 'ceo-pipe-label'; }
    if (pipeStage) pipeStage.textContent = 'Restoring after refresh';
    _ceoProgressShow('RECONNECTING...', 0, true);
    // Fetch current state and resume
    fetch(`/api/ceo/pipeline/${savedId}`).then(r => r.json()).then(data => {
        if (data.error) {
            console.warn('[CEO] Pipeline restore failed:', data.error);
            _activePipelineId = null;
            localStorage.removeItem('ceo_active_pipeline');
            _ceoProgressHide();
            return;
        }
        _ceoPipelineUpdateUI(data);
        // Resume polling if still active
        if (!['complete', 'error', 'cancelled'].includes(data.status)) {
            _ceoPipelineStartPolling();
        }
    }).catch(e => {
        console.error('[CEO] Pipeline restore error:', e);
        _activePipelineId = null;
        localStorage.removeItem('ceo_active_pipeline');
        _ceoProgressHide();
    });
}

// ── Progress Bar Helpers ─────────────────────────────────────────
function _ceoProgressShow(text, pct, indeterminate) {
    const bar = document.getElementById('ceo-progress-bar');
    const fill = document.getElementById('ceo-progress-fill');
    const txt = document.getElementById('ceo-progress-text');
    if (!bar) return;
    bar.classList.add('active');
    bar.classList.remove('complete', 'error');
    if (fill) fill.style.width = indeterminate ? '100%' : `${Math.max(4, pct)}%`;
    if (txt) txt.textContent = text || 'PROCESSING...';
}
function _ceoProgressUpdate(text, pct) {
    const fill = document.getElementById('ceo-progress-fill');
    const txt = document.getElementById('ceo-progress-text');
    if (fill) fill.style.width = `${Math.max(4, pct)}%`;
    if (txt) txt.textContent = text || '';
}
function _ceoProgressComplete(isError) {
    const bar = document.getElementById('ceo-progress-bar');
    const fill = document.getElementById('ceo-progress-fill');
    const txt = document.getElementById('ceo-progress-text');
    if (!bar) return;
    bar.classList.add(isError ? 'error' : 'complete');
    if (fill) fill.style.width = '100%';
    if (txt) txt.textContent = isError ? 'ERROR' : 'COMPLETE';
    setTimeout(() => _ceoProgressHide(), isError ? 5000 : 3000);
}
function _ceoProgressHide() {
    const bar = document.getElementById('ceo-progress-bar');
    if (bar) bar.classList.remove('active', 'complete', 'error');
}

async function _ceoPipelineLaunch(inputEl, selectEl) {
    const directive = inputEl.value.trim();
    if (!directive) return;
    const template = selectEl ? selectEl.value : 'full';
    inputEl.value = '';

    // Disable launch button during run
    const launchBtn = document.getElementById('ceo-pipeline-btn');
    if (launchBtn) launchBtn.disabled = true;

    // Update source node with directive
    const srcTask = document.getElementById('wf-src-task');
    if (srcTask) srcTask.textContent = directive.substring(0, 80) + (directive.length > 80 ? '…' : '');

    // Set master to working
    const masterStatus = document.querySelector('#ceo-master-card .ceo-master-status');
    if (masterStatus) { masterStatus.className = 'ceo-master-status working'; masterStatus.innerHTML = '<span class="ceo-dot"></span> PIPELINE RUNNING'; }

    // Reset all node statuses
    _CHAIN_ORDER.forEach(aid => {
        _nodeSetStatus(aid, '');
        const output = document.getElementById(`wf-output-${aid}`);
        if (output) { output.classList.remove('active'); output.textContent = ''; }
    });

    // Show pipeline status bar
    const statusBar = document.getElementById('ceo-pipeline-status');
    const pipeLabel = document.getElementById('ceo-pipe-label');
    const pipeStage = document.getElementById('ceo-pipe-stage');
    if (statusBar) statusBar.style.display = 'inline-flex';
    if (pipeLabel) { pipeLabel.textContent = 'LAUNCHING PIPELINE'; pipeLabel.className = 'ceo-pipe-label'; }
    if (pipeStage) pipeStage.textContent = `Template: ${template.toUpperCase()}`;

    _ceoRouteCount++;
    _ceoUpdateStats();
    const _jtPipeId = _jobAdd('pipeline', `${template.toUpperCase()}: ${directive.substring(0, 40)}`);
    // Store job tracker ID on the pipeline for progress updates
    window._activeJtPipeId = _jtPipeId;

    try {
        const resp = await fetch('/api/ceo/pipeline', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ directive, template }),
        });
        const data = await resp.json();

        if (data.error) {
            if (pipeLabel) { pipeLabel.textContent = 'PIPELINE ERROR'; pipeLabel.className = 'ceo-pipe-label error'; }
            if (pipeStage) pipeStage.textContent = data.error;
            if (launchBtn) launchBtn.disabled = false;
            _jobComplete(_jtPipeId, true);
            window._activeJtPipeId = null;
            return;
        }

        // Update job with total stage count
        _jobUpdate(_jtPipeId, { total: data.stages ? data.stages.length : 0 });

        _activePipelineId = data.id || data.pipeline_id;
        _ceoSavePipelineState();
        // Rebuild chain nodes to match this pipeline's agents
        if (data.stages) _rebuildChainNodes(data.stages);
        // Update source node with directive text
        const srcTaskEl = document.getElementById('wf-src-task');
        if (srcTaskEl) srcTaskEl.textContent = directive.substring(0, 80) + (directive.length > 80 ? '…' : '');
        // Show progress bar
        const totalStages = data.stages ? data.stages.length : 0;
        _ceoProgressShow(`PIPELINE LAUNCHED — 0/${totalStages} stages`, 0);
        // Process initial response then start polling
        _ceoPipelineUpdateUI(data);
        _ceoPipelineStartPolling();

    } catch (e) {
        if (pipeLabel) { pipeLabel.textContent = 'NETWORK ERROR'; pipeLabel.className = 'ceo-pipe-label error'; }
        if (pipeStage) pipeStage.textContent = e.message;
        if (launchBtn) launchBtn.disabled = false;
        _jobComplete(_jtPipeId, true);
        window._activeJtPipeId = null;
        _ceoProgressComplete(true);
    }
}

function _ceoPipelineUpdateUI(pipe) {
    if (!pipe || !pipe.stages) return;
    _lastPipeData = pipe;  // Cache for stage click access

    // Ensure chain nodes match this pipeline's agents (handles page refresh mid-pipeline)
    _rebuildChainNodes(pipe.stages);

    const pipeLabel = document.getElementById('ceo-pipe-label');
    const pipeStage = document.getElementById('ceo-pipe-stage');
    const approveBtn = document.getElementById('ceo-pipe-approve');
    const rejectBtn = document.getElementById('ceo-pipe-reject');
    const cancelBtn = document.getElementById('ceo-pipe-cancel');
    const launchBtn = document.getElementById('ceo-pipeline-btn');

    // Update each node tile based on stage status
    pipe.stages.forEach((stage, i) => {
        const aid = stage.agent_id;
        const output = document.getElementById(`wf-output-${aid}`);

        if (stage.status === 'running') {
            _nodeSetStatus(aid, 'working');
            if (output) { output.classList.add('active'); output.textContent = 'Processing...'; }
        } else if (stage.status === 'complete') {
            _nodeSetStatus(aid, 'complete');
            if (output) {
                output.classList.add('active');
                const txt = stage.output || 'Complete';
                output.innerHTML = _renderMarkdown(txt);
            }
            _ceoReadCount++;
        } else if (stage.status === 'error') {
            _nodeSetStatus(aid, 'error');
            if (output) { output.classList.add('active'); output.textContent = `Error: ${stage.error}`; }
        } else if (stage.status === 'waiting') {
            _nodeSetStatus(aid, 'ready');
            if (output) { output.classList.add('active'); output.textContent = '⏸ Waiting for your approval...'; }
        } else if (stage.status === 'ready') {
            _nodeSetStatus(aid, 'ready');
        }
        // pending — leave as default
    });

    _ceoUpdateStats();

    // Update pipeline status bar
    const runningStage = pipe.stages.find(s => s.status === 'running');
    const waitingStage = pipe.stages.find(s => s.status === 'waiting');
    const completedCount = pipe.stages.filter(s => s.status === 'complete').length;
    const totalCount = pipe.stages.length;

    // Update job tracker progress
    if (window._activeJtPipeId) {
        const running = runningStage ? runningStage.agent_name : null;
        _jobUpdate(window._activeJtPipeId, {
            progress: completedCount,
            total: totalCount,
            label: running ? `${running} (${completedCount}/${totalCount})` : `Pipeline ${completedCount}/${totalCount}`,
        });
        if (pipe.status === 'complete') { _jobComplete(window._activeJtPipeId); window._activeJtPipeId = null; }
        else if (pipe.status === 'error' || pipe.status === 'cancelled') { _jobComplete(window._activeJtPipeId, true); window._activeJtPipeId = null; }
    }

    // Update progress bar
    const pctDone = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;
    if (runningStage) {
        _ceoProgressShow(`${runningStage.agent_name.toUpperCase()} — ${completedCount}/${totalCount} stages`, pctDone);
    } else if (waitingStage) {
        _ceoProgressShow(`AWAITING APPROVAL — ${completedCount}/${totalCount} stages`, pctDone);
    } else if (pipe.status === 'complete') {
        _ceoProgressComplete(false);
    } else if (pipe.status === 'error' || pipe.status === 'cancelled') {
        _ceoProgressComplete(true);
    } else if (pipe.status === 'running' || pipe.status === 'ready') {
        _ceoProgressShow(`STARTING PIPELINE — ${completedCount}/${totalCount} stages`, pctDone, true);
    }

    const reportGroup = document.getElementById('ceo-pipe-report-group');
    const reportBtn = document.getElementById('ceo-pipe-report');
    const previewBtn = document.getElementById('ceo-pipe-preview');

    // Show cancel button for active pipelines, hide for terminal states
    const isActive = !['complete', 'error', 'cancelled'].includes(pipe.status);
    if (cancelBtn) cancelBtn.style.display = isActive ? '' : 'none';

    if (pipe.status === 'complete') {
        if (pipeLabel) { pipeLabel.textContent = 'PIPELINE COMPLETE'; pipeLabel.className = 'ceo-pipe-label complete'; }
        if (pipeStage) pipeStage.textContent = `${completedCount}/${totalCount} stages finished`;
        if (approveBtn) approveBtn.style.display = 'none';
        if (rejectBtn) rejectBtn.style.display = 'none';
        if (launchBtn) launchBtn.disabled = false;
        _ceoPipelineStopPolling();
        const completedPipeId = _activePipelineId || pipe.id;
        _activePipelineId = null;
        _ceoSavePipelineState();
        const masterStatus = document.querySelector('#ceo-master-card .ceo-master-status');
        if (masterStatus) { masterStatus.className = 'ceo-master-status ready'; masterStatus.innerHTML = '<span class="ceo-dot"></span> ONLINE'; }

        if (reportBtn) { reportBtn.dataset.pipelineId = completedPipeId || ''; }
        if (previewBtn) { previewBtn.dataset.pipelineId = completedPipeId || ''; }
        if (pipe.report) {
            _pipelineReportData = pipe.report;
            if (reportGroup) { reportGroup.style.display = 'inline-flex'; }
            if (reportBtn) { reportBtn.disabled = false; }
        } else {
            if (reportGroup) { reportGroup.style.display = 'inline-flex'; }
            if (reportBtn) { reportBtn.disabled = true; }
            _ceoPipelineReportPoll(completedPipeId);
        }
    } else if (pipe.status === 'cancelled') {
        if (pipeLabel) { pipeLabel.textContent = 'PIPELINE CANCELLED'; pipeLabel.className = 'ceo-pipe-label error'; }
        if (pipeStage) pipeStage.textContent = `Cancelled at stage ${pipe.current_idx + 1}/${totalCount}`;
        if (approveBtn) approveBtn.style.display = 'none';
        if (rejectBtn) rejectBtn.style.display = 'none';
        if (reportGroup) reportGroup.style.display = 'none';
        if (launchBtn) launchBtn.disabled = false;
        _ceoPipelineStopPolling();
        _activePipelineId = null;
        _ceoSavePipelineState();
    } else if (pipe.status === 'error') {
        if (pipeLabel) { pipeLabel.textContent = 'PIPELINE ERROR'; pipeLabel.className = 'ceo-pipe-label error'; }
        const errStage = pipe.stages.find(s => s.status === 'error');
        if (pipeStage) pipeStage.textContent = errStage ? `${errStage.agent_name}: ${errStage.error}` : 'Unknown error';
        if (approveBtn) approveBtn.style.display = 'none';
        if (rejectBtn) rejectBtn.style.display = 'none';
        if (reportGroup) reportGroup.style.display = 'none';
        if (launchBtn) launchBtn.disabled = false;
        _ceoPipelineStopPolling();
        _activePipelineId = null;
        _ceoSavePipelineState();
    } else if (waitingStage) {
        if (pipeLabel) { pipeLabel.textContent = 'AWAITING APPROVAL'; pipeLabel.className = 'ceo-pipe-label'; }
        if (pipeStage) pipeStage.textContent = `${waitingStage.agent_name} — review output before continuing`;
        if (approveBtn) approveBtn.style.display = '';
        if (rejectBtn) rejectBtn.style.display = '';
        if (reportGroup) reportGroup.style.display = 'none';
    } else if (runningStage) {
        if (pipeLabel) { pipeLabel.textContent = 'PIPELINE RUNNING'; pipeLabel.className = 'ceo-pipe-label'; }
        if (pipeStage) pipeStage.textContent = `${runningStage.agent_name} (${completedCount}/${totalCount})`;
        if (approveBtn) approveBtn.style.display = 'none';
        if (rejectBtn) rejectBtn.style.display = 'none';
        if (reportGroup) reportGroup.style.display = 'none';
    } else {
        // Status is 'ready' — some manual stages remain
        if (pipeLabel) { pipeLabel.textContent = 'PIPELINE RUNNING'; pipeLabel.className = 'ceo-pipe-label'; }
        if (pipeStage) pipeStage.textContent = `${completedCount}/${totalCount} stages complete`;
        if (reportGroup) reportGroup.style.display = 'none';
    }
}

function _ceoPipelineStartPolling() {
    _ceoPipelineStopPolling();
    _pipelinePollTimer = setInterval(async () => {
        if (!_activePipelineId) { _ceoPipelineStopPolling(); return; }
        try {
            const resp = await fetch(`/api/ceo/pipeline/${_activePipelineId}`);
            const data = await resp.json();
            if (data.error) { _ceoPipelineStopPolling(); return; }
            _ceoPipelineUpdateUI(data);
            // Stop polling on terminal states
            if (data.status === 'complete' || data.status === 'error' || data.status === 'cancelled') {
                _ceoPipelineStopPolling();
            }
        } catch (e) {
            console.error('Pipeline poll error:', e);
        }
    }, 2000);
}

function _ceoPipelineStopPolling() {
    if (_pipelinePollTimer) { clearInterval(_pipelinePollTimer); _pipelinePollTimer = null; }
}

async function _ceoPipelineCancel() {
    if (!_activePipelineId) return;
    const cancelBtn = document.getElementById('ceo-pipe-cancel');
    const pipeLabel = document.getElementById('ceo-pipe-label');
    if (cancelBtn) cancelBtn.disabled = true;
    try {
        const resp = await fetch(`/api/ceo/pipeline/${_activePipelineId}/cancel`, { method: 'POST' });
        const data = await resp.json();
        _ceoPipelineUpdateUI(data);
        _ceoPipelineStopPolling();
    } catch (e) {
        if (pipeLabel) { pipeLabel.textContent = 'CANCEL ERROR'; pipeLabel.className = 'ceo-pipe-label error'; }
    }
    if (cancelBtn) cancelBtn.disabled = false;
}

async function _ceoPipelineApprove() {
    if (!_activePipelineId) return;
    const approveBtn = document.getElementById('ceo-pipe-approve');
    const rejectBtn = document.getElementById('ceo-pipe-reject');
    if (approveBtn) approveBtn.style.display = 'none';
    if (rejectBtn) rejectBtn.style.display = 'none';

    const pipeLabel = document.getElementById('ceo-pipe-label');
    if (pipeLabel) { pipeLabel.textContent = 'APPROVED — CONTINUING'; pipeLabel.className = 'ceo-pipe-label'; }

    try {
        const resp = await fetch(`/api/ceo/pipeline/${_activePipelineId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        const data = await resp.json();
        _ceoPipelineUpdateUI(data);
        // Resume polling for next stages
        _ceoPipelineStartPolling();
    } catch (e) {
        if (pipeLabel) { pipeLabel.textContent = 'APPROVE ERROR'; pipeLabel.className = 'ceo-pipe-label error'; }
    }
}

async function _ceoPipelineReject() {
    if (!_activePipelineId) return;
    const pipeLabel = document.getElementById('ceo-pipe-label');
    const approveBtn = document.getElementById('ceo-pipe-approve');
    const rejectBtn = document.getElementById('ceo-pipe-reject');
    if (approveBtn) approveBtn.style.display = 'none';
    if (rejectBtn) rejectBtn.style.display = 'none';
    if (pipeLabel) { pipeLabel.textContent = 'PIPELINE CANCELLED'; pipeLabel.className = 'ceo-pipe-label error'; }
    const launchBtn = document.getElementById('ceo-pipeline-btn');
    if (launchBtn) launchBtn.disabled = false;
    _ceoPipelineStopPolling();
    _activePipelineId = null;
    _ceoSavePipelineState();
    _ceoProgressComplete(true);
    const masterStatus = document.querySelector('#ceo-master-card .ceo-master-status');
    if (masterStatus) { masterStatus.className = 'ceo-master-status ready'; masterStatus.innerHTML = '<span class="ceo-dot"></span> ONLINE'; }
}

function _ceoPipelineReportPoll(pipeId) {
    if (_pipelineReportPollTimer) clearInterval(_pipelineReportPollTimer);
    const pollId = pipeId || _activePipelineId;
    if (!pollId) return;
    let attempts = 0;
    _pipelineReportPollTimer = setInterval(async () => {
        if (attempts > 30) {
            clearInterval(_pipelineReportPollTimer);
            _pipelineReportPollTimer = null;
            const btn = document.getElementById('ceo-pipe-report');
            if (btn && !_pipelineReportData) { btn.disabled = false; }
            return;
        }
        attempts++;
        try {
            const resp = await fetch(`/api/ceo/pipeline/${pollId}`);
            const data = await resp.json();
            if (data.report) {
                _pipelineReportData = data.report;
                _pipelineReportDirective = data.directive || '';
                const btn = document.getElementById('ceo-pipe-report');
                if (btn) { btn.disabled = false; }
                const grp = document.getElementById('ceo-pipe-report-group');
                if (grp) grp.style.display = 'inline-flex';
                clearInterval(_pipelineReportPollTimer);
                _pipelineReportPollTimer = null;
            }
        } catch (e) { console.error('Report poll error:', e); }
    }, 3000);
}

// ── PDF Download (opens report view then triggers print-to-PDF) ──
async function _ceoPipelineDownloadPDF() {
    // First open the preview, then trigger print
    await _ceoPipelinePreviewReport();
    // Small delay to let the DOM render
    setTimeout(() => window.print(), 600);
}

// ── Print from report overlay ──
function _reportPrintPDF() {
    window.print();
}

// ── Markdown rendering helper ──
function _renderMarkdown(mdText) {
    const lines = mdText.split('\n');
    const out = [];
    let inTable = false;
    let tableRows = [];

    function flushTable() {
        if (!tableRows.length) return;
        let html = '<table class="md-table"><thead><tr>';
        const headers = tableRows[0].split('|').map(c => c.trim()).filter(c => c);
        headers.forEach(h => { html += `<th>${_escHtml(h)}</th>`; });
        html += '</tr></thead><tbody>';
        for (let r = 2; r < tableRows.length; r++) {
            const cells = tableRows[r].split('|').map(c => c.trim()).filter(c => c);
            html += '<tr>';
            cells.forEach(c => { html += `<td>${_escHtml(c)}</td>`; });
            html += '</tr>';
        }
        html += '</tbody></table>';
        out.push(html);
        tableRows = [];
        inTable = false;
    }

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const isTableRow = /^\|(.+)\|$/.test(line.trim());
        const isSeparator = /^\|[\s:|-]+\|$/.test(line.trim());

        if (isTableRow || isSeparator) {
            if (!inTable) inTable = true;
            tableRows.push(line.trim());
            continue;
        }
        if (inTable) flushTable();

        const escaped = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const rendered = escaped
            .replace(/^# (.+)$/, '<h2>$1</h2>')
            .replace(/^## (.+)$/, '<h3>$1</h3>')
            .replace(/^### (.+)$/, '<h4>$1</h4>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/^- (.+)$/, '<div style="padding-left:12px;">• $1</div>')
            .replace(/^(\d+\.)\s(.+)$/, '<div style="padding-left:12px;">$1 $2</div>')
            .replace(/^---$/, '<hr>')
            .replace(/`([^`]+)`/g, '<code style="background:rgba(0,200,255,0.08);padding:1px 4px;border-radius:3px;font-size:11px;">$1</code>');
        out.push(rendered);
    }
    if (inTable) flushTable();
    return out.join('\n');
}

async function _ceoPipelinePreviewReport() {
    const pipeId = _activePipelineId
        || (document.getElementById('ceo-pipe-report') || {}).dataset?.pipelineId
        || (_lastPipeData && _lastPipeData.id);
    if (!pipeId) { console.warn('[CEO] No pipeline ID for preview'); return; }

    const overlay = document.getElementById('pipeline-report-overlay');
    const body = document.getElementById('pipeline-report-body');
    const titleEl = document.getElementById('pipeline-report-title');
    const metaEl = document.getElementById('pipeline-report-meta');
    if (!overlay || !body) return;

    body.innerHTML = '<div style="color:var(--text-dim);padding:40px;text-align:center;">Loading report…</div>';
    if (titleEl) titleEl.textContent = 'EXECUTIVE REPORT';
    if (metaEl) metaEl.textContent = '';
    overlay.classList.add('active');
    document.body.classList.add('report-active');

    try {
        const mdResp = await fetch(`/api/ceo/pipeline/${pipeId}/report/download?fmt=md`);
        if (!mdResp.ok) {
            // Try raw pipeline data (report not generated yet)
            const pipeResp = await fetch(`/api/ceo/pipeline/${pipeId}`);
            const pipeData = await pipeResp.json();
            if (pipeData.stages && pipeData.stages.some(s => s.output)) {
                body.innerHTML = '';
                if (titleEl) titleEl.textContent = 'PIPELINE OUTPUT';
                if (metaEl) metaEl.textContent = pipeData.directive ? pipeData.directive.slice(0, 80) : '';
                pipeData.stages.forEach((stage, i) => {
                    if (!stage.output) return;
                    const sec = document.createElement('div');
                    sec.className = 'pr-section';
                    sec.innerHTML = `<div class="pr-section-header"><span class="pr-section-num">${i + 1}</span><span class="pr-section-agent">${_escHtml(stage.agent_name || stage.agent_id)}</span></div>`;
                    const content = document.createElement('div');
                    content.className = 'pr-section-content';
                    content.textContent = stage.output;
                    sec.appendChild(content);
                    body.appendChild(sec);
                });
            } else {
                body.innerHTML = '<div style="color:var(--text-dim);padding:40px;text-align:center;">No report data available yet.</div>';
            }
            return;
        }
        const mdText = await mdResp.text();
        body.innerHTML = '';
        if (titleEl) titleEl.textContent = 'EXECUTIVE REPORT';
        const pre = document.createElement('div');
        pre.className = 'pr-section-content';
        pre.innerHTML = _renderMarkdown(mdText);
        body.appendChild(pre);
    } catch (e) {
        console.error('[CEO] Report preview error:', e);
        body.innerHTML = '<div style="color:var(--red);padding:40px;">Failed to load report preview.</div>';
    }
}

// ── Report History (browse saved markdown reports) ──
async function _reportShowHistory() {
    const body = document.getElementById('pipeline-report-body');
    const titleEl = document.getElementById('pipeline-report-title');
    const metaEl = document.getElementById('pipeline-report-meta');
    const overlay = document.getElementById('pipeline-report-overlay');
    if (!body || !overlay) return;

    if (titleEl) titleEl.textContent = 'SAVED REPORTS';
    if (metaEl) metaEl.textContent = 'Markdown files saved for git commit';
    overlay.classList.add('active');
    document.body.classList.add('report-active');
    body.innerHTML = '<div style="color:var(--text-dim);padding:40px;text-align:center;">Loading…</div>';

    try {
        const resp = await fetch('/api/reports');
        const data = await resp.json();
        const reports = data.reports || [];

        if (reports.length === 0) {
            body.innerHTML = '<div style="color:var(--text-dim);padding:40px;text-align:center;">No saved reports yet. Run a pipeline to generate reports.</div>';
            return;
        }

        body.innerHTML = '';
        for (const r of reports) {
            const item = document.createElement('div');
            item.className = 'pr-history-item';
            // Parse timestamp
            const ts = r.timestamp || '';
            const dateStr = ts.length >= 15 ? `${ts.slice(0,4)}-${ts.slice(4,6)}-${ts.slice(6,8)} ${ts.slice(9,11)}:${ts.slice(11,13)}` : ts;
            const sizeKB = (r.size / 1024).toFixed(1);
            const slug = (r.slug || r.filename).replace(/_/g, ' ').replace(/\.[^.]+$/, '');
            item.innerHTML = `
                <span class="pr-history-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></span>
                <span class="pr-history-name" title="${_escHtml(r.filename)}">${_escHtml(slug)}</span>
                <span class="pr-history-date">${_escHtml(dateStr)}</span>
                <span class="pr-history-size">${sizeKB} KB</span>
            `;
            item.addEventListener('click', () => _reportLoadFromHistory(r.filename));
            body.appendChild(item);
        }
    } catch (e) {
        console.error('[CEO] Report history error:', e);
        body.innerHTML = '<div style="color:var(--red);padding:40px;">Failed to load report history.</div>';
    }
}

async function _reportLoadFromHistory(filename) {
    const body = document.getElementById('pipeline-report-body');
    const titleEl = document.getElementById('pipeline-report-title');
    const metaEl = document.getElementById('pipeline-report-meta');
    if (!body) return;

    body.innerHTML = '<div style="color:var(--text-dim);padding:40px;text-align:center;">Loading…</div>';
    const slug = filename.replace(/_/g, ' ').replace(/\.[^.]+$/, '');
    if (titleEl) titleEl.textContent = 'REPORT';
    if (metaEl) metaEl.textContent = slug.slice(0, 60);

    try {
        const resp = await fetch(`/api/reports/${encodeURIComponent(filename)}`);
        if (!resp.ok) { body.innerHTML = '<div style="color:var(--red);padding:40px;">Report not found.</div>'; return; }
        const mdText = await resp.text();
        body.innerHTML = '';
        const pre = document.createElement('div');
        pre.className = 'pr-section-content';
        pre.innerHTML = _renderMarkdown(mdText);
        body.appendChild(pre);
    } catch (e) {
        console.error('[CEO] Load report error:', e);
        body.innerHTML = '<div style="color:var(--red);padding:40px;">Failed to load report.</div>';
    }
}

function _ceoPipelineCloseReport() {
    const overlay = document.getElementById('pipeline-report-overlay');
    if (overlay) overlay.classList.remove('active');
    document.body.classList.remove('report-active');
}

function _ceoPipelineShowStageReport(agentId) {
    if (!_lastPipeData || !_lastPipeData.stages) return;
    const stage = _lastPipeData.stages.find(s => s.agent_id === agentId);
    if (!stage) return;
    if (stage.status !== 'complete' && stage.status !== 'error' && stage.status !== 'waiting') return; // Nothing to show yet

    const overlay = document.getElementById('pipeline-report-overlay');
    const body = document.getElementById('pipeline-report-body');
    const titleEl = document.getElementById('pipeline-report-title');
    const metaEl = document.getElementById('pipeline-report-meta');
    if (!overlay || !body) return;

    body.innerHTML = '';
    const agentName = (stage.agent_name || agentId).toUpperCase();
    const stageIdx = _lastPipeData.stages.indexOf(stage) + 1;
    if (titleEl) titleEl.textContent = `STAGE ${stageIdx}: ${agentName} REPORT`;
    if (metaEl) metaEl.textContent = stage.status === 'error' ? `Status: ERROR` : `Status: ${(stage.status || '').toUpperCase()}`;

    if (stage.status === 'error') {
        const errSection = document.createElement('div');
        errSection.className = 'report-section';
        errSection.innerHTML = `
            <div class="report-section-header">
                <span class="report-section-num" style="color:var(--red);">✗</span>
                <span class="report-section-query">ERROR</span>
            </div>
            <div class="report-summary-block"><p class="report-summary-line" style="color:var(--red);">${_escHtmlGlobal(stage.error || 'Unknown error')}</p></div>`;
        body.appendChild(errSection);
    } else if (stage.output) {
        // Try to parse output as structured data for rich rendering
        let parsed = null;
        try {
            const cleaned = stage.output.trim().replace(/^```[a-z]*\n?/i, '').replace(/```$/, '').trim();
            parsed = JSON.parse(cleaned);
        } catch (e) { /* not JSON, render as text */ }

        if (parsed && typeof parsed === 'object') {
            // Render structured output using ARBITER visualization components
            const vizSection = document.createElement('div');
            vizSection.className = 'report-section';
            vizSection.innerHTML = `<div class="report-section-header"><span class="report-section-num">◆</span><span class="report-section-query">${agentName} ANALYSIS</span></div>`;
            const vizContainer = document.createElement('div');
            vizContainer.className = 'report-viz-container';
            voice._renderSection(vizContainer, parsed);
            vizSection.appendChild(vizContainer);
            body.appendChild(vizSection);
        } else {
            // Render as formatted text blocks
            const output = stage.output;
            const sections = output.split(/\n(?=#{1,3}\s|[A-Z][A-Z\s&]{3,}:|\d+\.\s)/).filter(s => s.trim());

            if (sections.length > 1) {
                sections.forEach((sec, i) => {
                    const lines = sec.trim().split('\n');
                    const heading = lines[0].replace(/^#+\s*/, '').replace(/:$/, '').trim();
                    const content = lines.slice(1).join('\n').trim() || lines[0];
                    const secEl = document.createElement('div');
                    secEl.className = 'report-section';
                    secEl.innerHTML = `
                        <div class="report-section-header">
                            <span class="report-section-num">${i + 1}</span>
                            <span class="report-section-query">${_escHtmlGlobal(heading.substring(0, 80))}</span>
                        </div>
                        <div class="report-summary-block pr-section-content" style="font-size:12px;line-height:1.6;color:var(--text-main);max-height:400px;overflow-y:auto;">${_renderMarkdown(content || heading)}</div>`;
                    body.appendChild(secEl);
                });
            } else {
                const secEl = document.createElement('div');
                secEl.className = 'report-section';
                secEl.innerHTML = `
                    <div class="report-section-header">
                        <span class="report-section-num">◆</span>
                        <span class="report-section-query">${agentName} OUTPUT</span>
                    </div>
                    <div class="report-summary-block pr-section-content" style="font-size:12px;line-height:1.6;color:var(--text-main);max-height:600px;overflow-y:auto;">${_renderMarkdown(output)}</div>`;
                body.appendChild(secEl);
            }
        }
    } else if (stage.status === 'waiting') {
        const waitSection = document.createElement('div');
        waitSection.className = 'report-section';
        waitSection.innerHTML = `
            <div class="report-section-header">
                <span class="report-section-num">⏸</span>
                <span class="report-section-query">AWAITING APPROVAL</span>
            </div>
            <div class="report-summary-block"><p class="report-summary-line">This stage is waiting for your review and approval before the pipeline continues.</p></div>`;
        body.appendChild(waitSection);
    }

    overlay.classList.add('active');
    document.body.classList.add('report-active');
}

function _escHtmlGlobal(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}


// ── Agent Workflow View ──────────────────────────────────────────
// Live in-memory workflows (current session) + historical from DB
const _wfLive = new Map();  // wfId -> { id, type, task, created_at, agents: [{agent_id, agent_name, status, response, model, error}] }

let _wfIdCounter = 0;

function _wfAddLive(type, task, agents) {
    const wfId = `live_${Date.now()}_${++_wfIdCounter}`;
    _wfLive.set(wfId, {
        id: wfId,
        type,
        task,
        created_at: new Date().toISOString(),
        agents: agents.map(a => ({ ...a, response: null, error: null, model: null })),
    });
    _wfRender();
    return wfId;
}

function _wfUpdateLive(wfId, agentId, status, content, model) {
    const wf = _wfLive.get(wfId);
    if (!wf) return;
    const agent = wf.agents.find(a => a.agent_id === agentId);
    if (agent) {
        agent.status = status;
        if (status === 'error') agent.error = content;
        else agent.response = content;
        if (model) agent.model = model;
    }
    _wfRender();
}

async function _wfInit() {
    // Load historical workflows from DB
    await _wfRefreshFromDB();
}

async function _wfRefreshFromDB() {
    try {
        const resp = await fetch('/api/ceo/activity?limit=20');
        const data = await resp.json();
        _wfRender(data.workflows || []);
    } catch (e) {
        console.error('[WF] Failed to load activity:', e);
        _wfRender([]);
    }
}

function _wfRender(dbWorkflows) {
    const runsEl = document.getElementById('wf-runs');

    // Merge live workflows (on top) with DB workflows
    const allWfs = [];
    for (const [, wf] of _wfLive) { allWfs.push(wf); }
    if (dbWorkflows) {
        const liveIds = new Set([...(_wfLive.keys())]);
        for (const wf of dbWorkflows) {
            if (!liveIds.has(wf.id)) allWfs.push(wf);
        }
    }
    // Store last DB results for re-renders triggered by live updates
    if (dbWorkflows) _wfRender._lastDB = dbWorkflows;
    else if (_wfRender._lastDB) {
        const liveIds = new Set([...(_wfLive.keys())]);
        for (const wf of _wfRender._lastDB) {
            if (!liveIds.has(wf.id)) allWfs.push(wf);
        }
    }

    // Sort: newest first
    allWfs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    // Update overview stats
    let active = 0, complete = 0, errors = 0;
    for (const wf of allWfs) {
        const agents = wf.agents || [];
        const hasRunning = agents.some(a => a.status === 'running');
        const hasError = agents.some(a => a.status === 'error' || a.error);
        const allComplete = agents.every(a => a.status === 'complete' || a.response);
        if (hasRunning) active++;
        else if (hasError) errors++;
        else if (allComplete) complete++;
    }
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setVal('wf-stat-active', active);
    setVal('wf-stat-complete', complete);
    setVal('wf-stat-errors', errors);

    // Render compact run history cards below graph
    if (!runsEl) return;
    if (allWfs.length === 0) { runsEl.innerHTML = ''; return; }

    runsEl.innerHTML = allWfs.slice(0, 20).map(wf => {
        const agents = wf.agents || [];
        const hasRunning = agents.some(a => a.status === 'running');
        const hasError = agents.some(a => a.status === 'error' || a.error);
        const allComplete = agents.length > 0 && agents.every(a => a.status === 'complete' || a.response);
        const wfStatus = hasRunning ? 'working' : hasError ? 'error' : allComplete ? 'complete' : 'pending';
        const typeLabel = wf.type === 'broadcast' ? 'BROADCAST' : 'DISPATCH';
        const timeAgo = _wfTimeAgo(wf.created_at);

        return `<div class="wf-run-card ${wfStatus}" onclick="_wfToggleRunDetail('${wf.id}')">
            <span class="wf-run-type ${wf.type}">${typeLabel}</span>
            <span class="wf-run-task">${_escHtml(wf.task.substring(0, 80))}</span>
            <span class="wf-run-agents">${agents.map(a => {
                const s = a.status === 'running' ? 'working' : (a.error ? 'error' : (a.response || a.status === 'complete') ? 'complete' : 'pending');
                return `<span class="wf-run-agent-dot ${s}" title="${a.agent_name}"></span>`;
            }).join('')}</span>
            <span class="wf-run-time">${timeAgo}</span>
        </div>`;
    }).join('');
}

function _wfToggleRunDetail(wfId) {
    // Find the workflow data from live or DB cache
    let wf = _wfLive.get(wfId);
    if (!wf && _wfRender._lastDB) wf = _wfRender._lastDB.find(w => w.id === wfId);
    if (!wf) return;

    // Open the report overlay with all agent outputs
    const overlay = document.getElementById('pipeline-report-overlay');
    const body = document.getElementById('pipeline-report-body');
    const titleEl = document.getElementById('pipeline-report-title');
    const metaEl = document.getElementById('pipeline-report-meta');
    if (!overlay || !body) return;

    body.innerHTML = '';
    const typeLabel = wf.type === 'broadcast' ? 'BROADCAST' : 'DISPATCH';
    if (titleEl) titleEl.textContent = `${typeLabel} REPORT`;
    if (metaEl) metaEl.textContent = wf.task ? wf.task.substring(0, 120) : '';

    // Directive section
    if (wf.task) {
        const dirSection = document.createElement('div');
        dirSection.className = 'report-section';
        dirSection.innerHTML = `
            <div class="report-section-header">
                <span class="report-section-num" style="color:var(--amber);">⌘</span>
                <span class="report-section-query">DIRECTIVE</span>
            </div>
            <div class="report-summary-block" style="white-space:pre-wrap;font-size:13px;line-height:1.6;color:var(--text-main);">${_escHtmlGlobal(wf.task)}</div>`;
        body.appendChild(dirSection);
    }

    const agents = wf.agents || [];
    agents.forEach((a, i) => {
        const output = a.response || a.error || '';
        if (!output) return;

        const isError = !!(a.error);
        const agentName = (a.agent_name || a.agent_id || 'Agent').toUpperCase();

        // Try JSON parse for rich rendering
        let parsed = null;
        try {
            const cleaned = output.trim().replace(/^```[a-z]*\n?/i, '').replace(/```$/, '').trim();
            parsed = JSON.parse(cleaned);
        } catch (e) { /* not JSON */ }

        if (parsed && typeof parsed === 'object' && typeof voice !== 'undefined' && voice._renderSection) {
            const vizSection = document.createElement('div');
            vizSection.className = 'report-section';
            vizSection.innerHTML = `<div class="report-section-header"><span class="report-section-num">${i + 1}</span><span class="report-section-query">${agentName}${a.model ? ` · ${a.model}` : ''}</span></div>`;
            const vizContainer = document.createElement('div');
            vizContainer.className = 'report-viz-container';
            voice._renderSection(vizContainer, parsed);
            vizSection.appendChild(vizContainer);
            body.appendChild(vizSection);
        } else {
            // Split output by headings for readability
            const sections = output.split(/\n(?=#{1,3}\s|[A-Z][A-Z\s&]{3,}:|\d+\.\s)/).filter(s => s.trim());

            const secEl = document.createElement('div');
            secEl.className = 'report-section';

            if (sections.length > 1) {
                secEl.innerHTML = `<div class="report-section-header"><span class="report-section-num" style="${isError ? 'color:var(--red)' : ''}">${i + 1}</span><span class="report-section-query">${agentName}${a.model ? ` · ${a.model}` : ''}</span></div>`;
                sections.forEach(sec => {
                    const lines = sec.trim().split('\n');
                    const heading = lines[0].replace(/^#+\s*/, '').replace(/:$/, '').trim();
                    const content = lines.slice(1).join('\n').trim() || heading;
                    const subEl = document.createElement('div');
                    subEl.className = 'report-summary-block';
                    subEl.style.cssText = 'white-space:pre-wrap;font-size:12px;line-height:1.6;color:var(--text-main);max-height:500px;overflow-y:auto;margin-bottom:8px;';
                    if (heading !== content) {
                        subEl.innerHTML = `<strong style="color:var(--cyan);font-size:11px;letter-spacing:0.5px;">${_escHtmlGlobal(heading)}</strong>\n${_escHtmlGlobal(content)}`;
                    } else {
                        subEl.textContent = content;
                    }
                    secEl.appendChild(subEl);
                });
            } else {
                secEl.innerHTML = `
                    <div class="report-section-header">
                        <span class="report-section-num" style="${isError ? 'color:var(--red)' : ''}">${i + 1}</span>
                        <span class="report-section-query">${agentName}${a.model ? ` · ${a.model}` : ''}</span>
                    </div>
                    <div class="report-summary-block" style="white-space:pre-wrap;font-size:12px;line-height:1.6;color:var(--text-main);max-height:600px;overflow-y:auto;${isError ? 'color:var(--red);' : ''}">${_escHtmlGlobal(output)}</div>`;
            }
            body.appendChild(secEl);
        }
    });

    overlay.classList.add('active');
    document.body.classList.add('report-active');
}

function _wfTimeAgo(iso) {
    if (!iso) return '';
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}






// ── Camera Vision Module (background mode) ──────────────────────
const _cam = {
    stream: null,
    active: false,
    particles: [],
    animFrame: null,
};

function _camOpen() {
    if (_cam.active) return;
    const bg = document.getElementById('cam-bg');
    const video = document.getElementById('cam-video');
    if (!bg || !video) return;

    // Close any open panel (quick, no orb animation — camera will handle that)
    if (activeDock) _panelQuickClose();

    _cam.active = true;

    // Clear any dialogue options / briefing prompt so they don't travel with the orb
    const dOpts = document.getElementById('dialogue-options');
    if (dOpts) dOpts.innerHTML = '';
    _dismissBriefingPrompt();

    // Request camera first (so stream is ready when viewport appears)
    navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
    }).then(stream => {
        _cam.stream = stream;
        video.srcObject = stream;

        const mc = document.querySelector('.mc-center');
        const startRect = mc.getBoundingClientRect();
        const orbCanvas = document.getElementById('orb-canvas');
        const orbW = orbCanvas ? orbCanvas.offsetWidth : startRect.width;
        const scaleFrom = orbW / 130;

        // ── Capture the visual center of the orb before any changes ──
        const startCX = startRect.left + startRect.width / 2;
        const startCY = startRect.top + startRect.height / 2;

        // ── Resize canvas to 130px immediately (correct render intensity) ──
        if (typeof orb !== 'undefined') orb._resize(130);
        const mcW = mc.offsetWidth;
        const mcH = mc.offsetHeight;

        // ── Fix position so visual center stays at startCX/startCY ──
        // scale() from center doesn't move the center, so top/left sets box position
        mc.style.position = 'fixed';
        mc.style.top = (startCY - mcH / 2) + 'px';
        mc.style.left = (startCX - mcW / 2) + 'px';
        mc.style.transformOrigin = 'center center';
        mc.style.transform = `translate(0px, 0px) scale(${scaleFrom})`;
        mc.style.transition = 'none';
        mc.style.zIndex = '600';
        void mc.offsetHeight;

        // ── Slide panels out ──
        document.body.classList.add('vision-mode');

        // ── Target: bottom-right corner at scale(1), element edge at margin ──
        const targetTop = window.innerHeight - 28 - mcH;
        const targetLeft = window.innerWidth - 32 - mcW;
        const targetCX = targetLeft + mcW / 2;
        const targetCY = targetTop + mcH / 2;
        const dx = targetCX - startCX;
        const dy = targetCY - startCY;

        // ── Animate: translate to corner + scale down to 1 (real 130px) ──
        requestAnimationFrame(() => {
            mc.style.transition = 'transform 0.9s cubic-bezier(0.22,1,0.36,1)';
            mc.style.transform = `translate(${dx}px, ${dy}px) scale(1)`;
        });

        // ── After animation: swap transform for direct top/left ──
        setTimeout(() => {
            mc.style.transition = 'none';
            mc.style.top = targetTop + 'px';
            mc.style.left = targetLeft + 'px';
            mc.style.transform = 'none';
        }, 960);

        // ── Camera viewport fades in after orb has settled ──
        setTimeout(() => {
            bg.classList.add('active');
            document.getElementById('cam-particles')?.classList.add('active');
            _camInitParticles();
        }, 1100);

        const ds = document.getElementById('dock-cam-status');
        if (ds) { ds.textContent = 'LIVE'; ds.className = 'dp-val nominal'; }
    }).catch(err => {
        console.error('[VISION] Camera error:', err);
        _cam.active = false;
        document.body.classList.remove('vision-mode');
        const mc = document.querySelector('.mc-center');
        if (mc) mc.style.cssText = '';
        const ds = document.getElementById('dock-cam-status');
        if (ds) { ds.textContent = 'ERR'; ds.className = 'dp-val alert'; }
    });
}

function _camClose() {
    if (!_cam.active) return;
    _cam.active = false;
    _camScanStop();

    const mc = document.querySelector('.mc-center');

    // ── Step 1: Fade out camera feed + particles + vision panels ──
    document.getElementById('cam-bg')?.classList.remove('active');
    document.getElementById('cam-particles')?.classList.remove('active');
    if (_cam.animFrame) { cancelAnimationFrame(_cam.animFrame); _cam.animFrame = null; }
    const vbl = document.getElementById('vision-body-left');
    const vbr = document.getElementById('vision-body-right');
    if (vbl) vbl.innerHTML = '';
    if (vbr) vbr.innerHTML = '';
    console.log('[VISION] Step 1: Camera fading out');

    // ── Step 2: After camera fades, animate orb back to center & grow ──
    setTimeout(() => {
        const curRect = mc.getBoundingClientRect();
        const curCX = curRect.left + curRect.width / 2;
        const curCY = curRect.top + curRect.height / 2;
        const fullSize = Math.max(200, Math.min(window.innerWidth * 0.2, 420));
        const scaleFrom = 130 / fullSize;

        // ── Resize canvas to full immediately (correct render intensity) ──
        if (typeof orb !== 'undefined') orb._resize(Math.round(fullSize));
        const mcW = mc.offsetWidth;
        const mcH = mc.offsetHeight;

        // ── Fix position so visual center stays at curCX/curCY ──
        mc.style.position = 'fixed';
        mc.style.top = (curCY - mcH / 2) + 'px';
        mc.style.left = (curCX - mcW / 2) + 'px';
        mc.style.transformOrigin = 'center center';
        mc.style.transform = `translate(0px, 0px) scale(${scaleFrom})`;
        mc.style.transition = 'none';
        mc.style.zIndex = '600';
        void mc.offsetHeight;

        // ── Measure where CSS will naturally place the orb ──
        // CSS: position absolute, top 50%, left 50%, translate(-50%,-50%) inside .mc-viewport
        const parent = mc.parentElement;
        const parentRect = parent.getBoundingClientRect();
        const cssCX = parentRect.left + parentRect.width / 2;
        const cssCY = parentRect.top + parentRect.height / 2;
        const dx = cssCX - curCX;
        const dy = cssCY - curCY;

        // Remove vision-mode (panels slide back in)
        document.body.classList.remove('vision-mode');

        // Animate: translate to center + scale up to 1 (real full size)
        requestAnimationFrame(() => {
            mc.style.transition = 'transform 0.9s cubic-bezier(0.22,1,0.36,1)';
            mc.style.transform = `translate(${dx}px, ${dy}px) scale(1)`;
        });

        // After animation: clear inline styles without triggering CSS transitions
        setTimeout(() => {
            // Temporarily kill CSS transitions on mc-center, then clear inline styles
            mc.style.transition = 'none';
            mc.style.cssText = 'transition: none !important;';
            void mc.offsetHeight; // force reflow with no transition
            // Re-enable CSS transitions next frame — element is already at rest
            requestAnimationFrame(() => {
                mc.style.cssText = '';
                if (typeof orb !== 'undefined') orb._resize();
            });
        }, 960);
    }, 600);

    // ── Step 3: Cleanup camera stream after all transitions finish ──
    setTimeout(() => {
        if (_cam.stream) {
            _cam.stream.getTracks().forEach(t => t.stop());
            _cam.stream = null;
        }
        const video = document.getElementById('cam-video');
        if (video) video.srcObject = null;
    }, 2200);

    // Update dock badge immediately
    const ds = document.getElementById('dock-cam-status');
    if (ds) { ds.textContent = 'OFF'; ds.className = 'dp-val'; }
}

function _camToggle() { _cam.active ? _camClose() : _camOpen(); }

/** Start the continuous scanning effect while processing a vision query */
function _camScanStart() {
    const scanline = document.getElementById('cam-scanline');
    const grid = document.getElementById('cam-scan-grid');
    if (scanline) { scanline.classList.remove('active'); scanline.classList.add('scanning'); }
    if (grid) grid.classList.add('active');
    document.body.classList.add('vision-scanning');
}

/** Stop the scanning effect */
function _camScanStop() {
    const scanline = document.getElementById('cam-scanline');
    const grid = document.getElementById('cam-scan-grid');
    if (scanline) { scanline.classList.remove('scanning'); scanline.classList.remove('active'); }
    if (grid) grid.classList.remove('active');
    document.body.classList.remove('vision-scanning');
}

/**
 * Render a vision API response into the left/right flanking panels.
 * Left panel: identification & details (what is it, specs, properties).
 * Right panel: actionable guidance (how-to steps, tips, warnings).
 */
function _camRenderVisionPanels(reply, query) {
    const bodyL = document.getElementById('vision-body-left');
    const bodyR = document.getElementById('vision-body-right');
    const titleL = document.getElementById('vision-title-left');
    const titleR = document.getElementById('vision-title-right');
    if (!bodyL || !bodyR) return;

    // Split reply into paragraphs
    const paragraphs = reply.split(/\n\n+/).map(p => p.trim()).filter(Boolean);
    if (!paragraphs.length) return;

    // Heuristic: detect numbered/bulleted steps for the right panel
    const stepRegex = /^(\d+[\.\)]\s*|[-•]\s+)/;
    const isHowTo = query && /\b(how|guide|steps?|setup|install|connect|configure|build|make|create|use|tutorial)\b/i.test(query);

    // Split content: identification paragraphs vs actionable steps
    const identParts = [];
    const guideParts = [];
    let foundSteps = false;

    for (const p of paragraphs) {
        const lines = p.split('\n').map(l => l.trim()).filter(Boolean);
        const hasSteps = lines.some(l => stepRegex.test(l));

        if (hasSteps || foundSteps) {
            foundSteps = true;
            guideParts.push(...lines);
        } else {
            identParts.push(p);
        }
    }

    // If no steps found but it's a how-to query, try splitting on sentence boundaries
    if (!guideParts.length && isHowTo && identParts.length > 1) {
        // Move second half to guide
        const mid = Math.ceil(identParts.length / 2);
        guideParts.push(...identParts.splice(mid).flatMap(p => p.split('\n').map(l => l.trim()).filter(Boolean)));
    }

    // If still no split, put everything on the left, summary on right
    if (!guideParts.length) {
        // Extract key terms as tags
        const allText = identParts.join(' ');
        const sentences = allText.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 10);
        if (sentences.length > 2) {
            // Put first half left, second half right
            const mid = Math.ceil(sentences.length / 2);
            guideParts.push(...sentences.slice(mid).map(s => s + '.'));
            identParts.length = 0;
            identParts.push(sentences.slice(0, mid).map(s => s + '.').join(' '));
        }
    }

    // ── Render LEFT panel (Analysis / Identification) ──
    titleL.textContent = 'ANALYSIS';
    let leftHtml = '';

    if (identParts.length) {
        leftHtml += '<div class="v-section">';
        leftHtml += '<div class="v-section-title">IDENTIFICATION</div>';
        for (const p of identParts) {
            // Check for key-value patterns like "Model: Raspberry Pi 4"
            const kvLines = p.split('\n').map(l => l.trim()).filter(Boolean);
            for (const line of kvLines) {
                const kvMatch = line.match(/^[*-]?\s*\*?\*?([A-Za-z\s]+)\*?\*?\s*[:–—]\s*(.+)/);
                if (kvMatch) {
                    leftHtml += `<div class="v-item"><div class="v-item-dot cyan"></div><div><div class="v-item-text">${_escHtml(kvMatch[2])}</div><div class="v-item-label">${_escHtml(kvMatch[1])}</div></div></div>`;
                } else {
                    leftHtml += `<div class="v-item"><div class="v-item-dot"></div><div class="v-item-text">${_escHtml(line)}</div></div>`;
                }
            }
        }
        leftHtml += '</div>';
    }

    bodyL.innerHTML = leftHtml || '<div class="v-item"><div class="v-item-dot"></div><div class="v-item-text" style="color:rgba(60,140,255,0.3)">No details identified.</div></div>';

    // ── Render RIGHT panel (Guidance / Steps) ──
    titleR.textContent = guideParts.length ? (isHowTo ? 'HOW-TO' : 'DETAILS') : 'GUIDANCE';
    let rightHtml = '';

    if (guideParts.length) {
        // Check if these are numbered steps
        const numbered = guideParts.some(l => /^\d+[\.\)]/.test(l));

        if (numbered || isHowTo) {
            rightHtml += '<div class="v-section">';
            rightHtml += `<div class="v-section-title">${isHowTo ? 'STEPS' : 'GUIDANCE'}</div>`;
            let stepNum = 0;
            for (const line of guideParts) {
                const cleaned = line.replace(/^(\d+[\.\)]\s*|[-•]\s+)/, '').trim();
                if (!cleaned) continue;
                stepNum++;
                rightHtml += `<div class="v-step"><div class="v-step-num">${stepNum}</div><div class="v-step-text">${_escHtml(cleaned)}</div></div>`;
            }
            rightHtml += '</div>';
        } else {
            rightHtml += '<div class="v-section">';
            rightHtml += '<div class="v-section-title">ADDITIONAL DETAILS</div>';
            for (const line of guideParts) {
                rightHtml += `<div class="v-item"><div class="v-item-dot green"></div><div class="v-item-text">${_escHtml(line)}</div></div>`;
            }
            rightHtml += '</div>';
        }
    }

    bodyR.innerHTML = rightHtml || '<div class="v-item"><div class="v-item-dot"></div><div class="v-item-text" style="color:rgba(60,140,255,0.3)">Ask a question to receive guidance.</div></div>';

    // Mark panels as having content for CSS
    document.getElementById('vision-panel-left')?.classList.add('has-content');
    document.getElementById('vision-panel-right')?.classList.add('has-content');
}

function _escHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _camCaptureFrame() {
    const video = document.getElementById('cam-video');
    const canvas = document.getElementById('cam-capture');
    if (!video || !canvas || !_cam.stream) return null;

    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Show scanline effect
    const scanline = document.getElementById('cam-scanline');
    if (scanline) {
        scanline.classList.remove('active');
        void scanline.offsetWidth; // reflow
        scanline.classList.add('active');
        setTimeout(() => scanline.classList.remove('active'), 1300);
    }

    return canvas.toDataURL('image/jpeg', 0.85).split(',')[1];
}

// ── Particle System (border particles) ──────────────────────────
function _camInitParticles() {
    const canvas = document.getElementById('cam-particles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    function resize() {
        canvas.width = window.innerWidth * dpr;
        canvas.height = window.innerHeight * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener('resize', resize);

    // Create particles along the border
    _cam.particles = [];
    const TOTAL = 120;
    const w = window.innerWidth, h = window.innerHeight;
    const perimeter = 2 * (w + h);

    for (let i = 0; i < TOTAL; i++) {
        const pos = (i / TOTAL) * perimeter;
        let x, y;
        if (pos < w) { x = pos; y = 0; }
        else if (pos < w + h) { x = w; y = pos - w; }
        else if (pos < 2 * w + h) { x = 2 * w + h - pos; y = h; }
        else { x = 0; y = perimeter - pos; }

        _cam.particles.push({
            x, y, baseX: x, baseY: y,
            size: 1 + Math.random() * 2.5,
            speed: 0.3 + Math.random() * 0.8,
            offset: Math.random() * Math.PI * 2,
            drift: 8 + Math.random() * 20,
            alpha: 0.3 + Math.random() * 0.6,
        });
    }

    let time = 0;
    function animate() {
        if (!_cam.active) return;
        time += 0.012;
        ctx.clearRect(0, 0, w, h);

        for (const p of _cam.particles) {
            const dx = Math.sin(time * p.speed + p.offset) * p.drift;
            const dy = Math.cos(time * p.speed * 0.7 + p.offset) * p.drift;
            p.x = p.baseX + dx;
            p.y = p.baseY + dy;

            const alpha = p.alpha * (0.5 + 0.5 * Math.sin(time * 2 + p.offset));
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(60,140,255,${alpha})`;
            ctx.fill();

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size * 3, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(60,140,255,${alpha * 0.15})`;
            ctx.fill();
        }

        // Draw connecting lines between nearby particles
        for (let i = 0; i < _cam.particles.length; i++) {
            for (let j = i + 1; j < _cam.particles.length; j++) {
                const a = _cam.particles[i], b = _cam.particles[j];
                const dist = Math.hypot(a.x - b.x, a.y - b.y);
                if (dist < 80) {
                    ctx.beginPath();
                    ctx.moveTo(a.x, a.y);
                    ctx.lineTo(b.x, b.y);
                    ctx.strokeStyle = `rgba(60,140,255,${0.08 * (1 - dist / 80)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }

        _cam.animFrame = requestAnimationFrame(animate);
    }
    animate();
}

document.addEventListener('DOMContentLoaded', () => {
    // Dock panel clicks → full-page panel view
    document.querySelectorAll('.dock-panel[data-dock]').forEach(tile => {
        tile.addEventListener('click', () => openExpandPanels(tile.dataset.dock));
    });
    // Panel viewport close button
    const panelCloseBtn = document.getElementById('panel-close-btn');
    if (panelCloseBtn) panelCloseBtn.addEventListener('click', () => closeExpandPanels());
    // ESC key
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && activeDock) closeExpandPanels();
        if (e.key === 'Escape' && _cam.active) _camClose();
    });
    // Browser back/forward navigation
    window.addEventListener('popstate', (e) => {
        if (e.state && e.state.panel) {
            openExpandPanels(e.state.panel, false);
        } else if (activeDock) {
            closeExpandPanels(false);
        }
    });
    // On initial load, check if URL has a panel path
    const pathMatch = window.location.pathname.match(/^\/panel\/(\w+)$/);
    if (pathMatch && DOCK_EXPAND[pathMatch[1]]) {
        // Delay to let boot animation finish
        setTimeout(() => openExpandPanels(pathMatch[1], false), 2500);
    }
    // Todo list: add button & enter key
    const todoAddBtn = document.getElementById('todo-add-btn');
    const todoInput = document.getElementById('todo-input');
    if (todoAddBtn) todoAddBtn.addEventListener('click', _addTodo);
    if (todoInput) todoInput.addEventListener('keydown', e => { if (e.key === 'Enter') _addTodo(); });
    // Init todo dock badge + reminders
    _updateTodoDock();
    _initTodoReminders();
    // Init deadlines
    refreshDeadlines();

    // Camera vision toggle (dock button + exit button)
    const camBtn = document.getElementById('dock-cam-btn');
    if (camBtn) camBtn.addEventListener('click', _camToggle);
    const camExitBtn = document.getElementById('cam-exit-btn');
    if (camExitBtn) camExitBtn.addEventListener('click', _camClose);
});

// ── Master refresh ───────────────────────────────────────────────
let _refreshing = false;
async function refreshAll() {
    // Guard against re-entrant calls (if previous refresh errored, countdown stays <=0)
    if (_refreshing) return;
    _refreshing = true;
    countdown = REFRESH_INTERVAL / 1000;  // Reset FIRST to prevent re-trigger on error
    try {
        // Trigger radar scan on the globe
        if (gcpGlobe) gcpGlobe.triggerScan();
        appendLog('Refreshing all systems...', '');
        await Promise.all([
            refreshStatus().catch(e => console.warn('refreshStatus error:', e)),
            refreshEmail().catch(e => console.warn('refreshEmail error:', e)),
            refreshBulletins().catch(e => console.warn('refreshBulletins error:', e)),
            refreshAgents().catch(e => console.warn('refreshAgents error:', e)),
            refreshGCP().catch(e => console.warn('refreshGCP error:', e)),
            refreshRevenue().catch(e => console.warn('refreshRevenue error:', e)),
            refreshServiceHealth().catch(e => console.warn('refreshServiceHealth error:', e)),
            refreshActiveAgents().catch(e => console.warn('refreshActiveAgents error:', e)),
            refreshOrgTeamCount().catch(e => console.warn('refreshOrgTeamCount error:', e)),
            refreshCICD().catch(e => console.warn('refreshCICD error:', e)),
            refreshClaudeUsage().catch(e => console.warn('refreshClaudeUsage error:', e)),
            refreshLLMStatus().catch(e => console.warn('refreshLLMStatus error:', e)),
            refreshSystemInfo().catch(e => console.warn('refreshSystemInfo error:', e)),
            refreshGCPPods().catch(e => console.warn('refreshGCPPods error:', e)),
        ]);
        refreshDeadlines();
        appendLog('All systems refreshed', '');
    } catch (err) {
        console.error('refreshAll error:', err);
        appendLog('Refresh error — retrying next cycle', '');
    } finally {
        _refreshing = false;
        countdown = REFRESH_INTERVAL / 1000;  // Always reset even on error
    }
}

// ── Splash Screen Boot Sequence ──────────────────────────────────
// Ties splash progress to REAL data fetches so the dashboard is fully
// populated before the slide-in reveal.
async function _runBootSequence() {
    const splash = document.getElementById('splash-overlay');
    const splashStatus = document.getElementById('splash-status');
    const splashBar = document.getElementById('splash-bar-fill');
    if (!splash) return;

    const _setProgress = (pct, text) => {
        if (splashBar) splashBar.style.width = pct + '%';
        if (splashStatus) splashStatus.textContent = text;
    };

    // Helper: run a batch of fetches, catch errors silently
    const _batch = (fns) => Promise.all(fns.map(fn => fn().catch(e => {
        console.warn('[BOOT]', fn.name || 'fetch', 'error:', e);
    })));

    try {
        // ── Stage 0: Load business profiles ──
        _setProgress(5, 'LOADING BUSINESS PROFILES');
        await _loadBusinesses();

        // ── Stage 1: Core status ──
        _setProgress(10, 'CONNECTING TO CORE');
        await _batch([refreshStatus, refreshLLMStatus]);

        // ── Stage 2: System metrics ──
        _setProgress(25, 'LOADING SYSTEM METRICS');
        await _batch([refreshSystemInfo, refreshServiceHealth]);

        // ── Stage 3: Infrastructure ──
        _setProgress(45, 'MAPPING INFRASTRUCTURE');
        await _batch([refreshGCP, refreshGCPPods]);
        if (typeof gcpGlobe !== 'undefined' && gcpGlobe) gcpGlobe.triggerScan();

        // ── Stage 4: Data feeds ──
        _setProgress(65, 'SYNCING DATA FEEDS');
        await _batch([refreshEmail, refreshBulletins, refreshRevenue]);

        // ── Stage 5: Remaining panels ──
        _setProgress(82, 'LOADING DASHBOARDS');
        await _batch([refreshCICD, refreshClaudeUsage, refreshAgents, refreshDeadlines, refreshActiveAgents, refreshOrgTeamCount]);

        // ── Stage 6: Done ──
        _setProgress(100, 'SYSTEMS ONLINE');

    } catch (err) {
        console.error('[BOOT] Boot sequence error:', err);
        _setProgress(100, 'PARTIAL BOOT — ENTERING');
    }

    // Brief hold at 100% so the user sees "SYSTEMS ONLINE"
    await new Promise(r => setTimeout(r, 600));

    // ── Dismiss splash & reveal dashboard ──
    splash.classList.add('dismissed');
    document.body.classList.add('boot-animate');
    void document.body.offsetHeight; // force reflow
    document.body.classList.remove('booting');
    setTimeout(() => { splash.remove(); }, 1200);

    // Mark first refresh as done so the countdown doesn't re-trigger immediately
    _refreshing = false;
    countdown = REFRESH_INTERVAL / 1000;
    console.log('[BOOT] Dashboard revealed — all data loaded');

    // ── Morning Briefing Prompt ──────────────────────────────────────
    // After boot, offer the user a daily briefing. Business summary only
    // appears if they accept. Prompt auto-dismisses after 20 seconds.
    setTimeout(() => _offerMorningBriefing(), 2200);
}

function _offerMorningBriefing() {
    const container = document.getElementById('dialogue-options');
    if (!container) return;

    // Flag so voice pipeline can intercept yes/no
    window._briefingPromptActive = true;

    // Time-aware greeting
    const _hour = new Date().getHours();
    const _tod = _hour < 12 ? 'morning' : _hour < 18 ? 'afternoon' : 'evening';
    const _greetLine = `Good ${_tod}, Sir. Shall I run the daily briefing?`;

    // Show briefing prompt as dialogue options below the orb
    container.innerHTML = '';
    const prompt = document.createElement('div');
    prompt.className = 'briefing-prompt';
    prompt.innerHTML = `
        <div class="briefing-prompt-text">${_greetLine}</div>
        <div class="briefing-prompt-btns">
            <button class="dialogue-opt briefing-yes" id="briefing-accept">YES — RUN BRIEFING</button>
            <button class="dialogue-opt briefing-no" id="briefing-decline">NO — SKIP</button>
        </div>
    `;
    container.appendChild(prompt);

    // Speak the prompt — only if not already speaking or processing
    // Pass a no-op onDone so _speak does NOT open a follow-up listen window
    if (typeof voice !== 'undefined' && voice._speak) {
        const busy = voice._processingQuery || voice.speaking || voice._chatMode;
        if (!busy) {
            voice._speak(_greetLine, () => {});
        }
    }

    // Auto-dismiss after 20s
    const autoDismiss = setTimeout(() => {
        _dismissBriefingPrompt();
    }, 20000);

    document.getElementById('briefing-accept').onclick = () => {
        clearTimeout(autoDismiss);
        window._briefingPromptActive = false;
        _dismissBriefingPrompt();
        _runMorningBriefing();
    };
    document.getElementById('briefing-decline').onclick = () => {
        clearTimeout(autoDismiss);
        window._briefingPromptActive = false;
        _dismissBriefingPrompt();
        if (typeof logConvo === 'function') logConvo('Briefing declined', 'system');
        if (typeof voice !== 'undefined') {
            // Stop any speech immediately (greeting may still be playing)
            if (voice.speaking) voice.stopSpeaking();
            // Clear dialogue options
            voice._clearDialogueOptions();
            // Kill recognition — prevent onend from restarting
            voice._suppressRestart = true;
            voice._pendingStart = null;
            voice._mode = 'off';
            voice._processingQuery = false;
            if (voice.recognition) {
                try { voice.recognition.abort(); } catch {}
            }
            voice.orb.setState('idle');
            // Resume passive standby after a long delay
            setTimeout(() => voice._requestStart('passive'), 3000);
        }
    };
}

function _dismissBriefingPrompt() {
    window._briefingPromptActive = false;
    const container = document.getElementById('dialogue-options');
    if (container) container.innerHTML = '';
}

function _runMorningBriefing() {
    // Show the business summary box
    const revBox = document.getElementById('revenue-summary-bar');
    if (revBox) {
        revBox.style.display = '';
        // Auto-hide after 60 seconds
        setTimeout(() => { revBox.style.display = 'none'; }, 60000);
    }

    // Send the briefing query through the normal chat pipeline
    // Specific to Sir Luke's systems — no generic market/stock data
    if (typeof voice !== 'undefined') {
        voice.history.push({ role: 'user', content: 'Give me the daily briefing' });
        voice._sendMessage(
            'Run my daily briefing. Cover ONLY these topics in a concise spoken summary: '
            + '1) Grow with Freya app — GCP pod health, replica status, any deployment issues. '
            + '2) Revenue — MRR, subscriber count, trial conversions from RevenueCat. '
            + '3) CI/CD — recent build pass/fail status. '
            + '4) Service uptime — any services currently down or degraded. '
            + '5) Upcoming deadlines from the roadmap. '
            + '6) Available workflow pipelines and recent runs. '
            + 'Do NOT include stock markets, S&P 500, crypto, or any financial markets. This is a personal project briefing only.'
        );
    }
    if (typeof logConvo === 'function') logConvo('Daily briefing requested', 'system');
}

// ── Boot ─────────────────────────────────────────────────────────
console.log('[BOOT] Creating Orb...');
const orb = new Orb('orb-canvas');
console.log('[BOOT] Orb created. Creating VoiceEngine...');
try {
    var voice = new VoiceEngine(orb);
    console.log('[BOOT] VoiceEngine created successfully');
} catch (bootErr) {
    console.error('[BOOT] VoiceEngine failed:', bootErr);
    const clog = document.getElementById('convo-log');
    if (clog) {
        const el = document.createElement('div');
        el.className = 'convo-line system';
        el.textContent = 'VOICE ENGINE BOOT FAILED: ' + bootErr.message;
        clog.appendChild(el);
    }
}

updateClock();
setInterval(updateClock, 1000);
setInterval(() => {
    countdown--;
    document.getElementById('refresh-timer').textContent = `Next refresh: ${countdown}s`;
    if (countdown <= 0) refreshAll();
}, 1000);

// Boot sequence fetches all data behind the splash screen, then reveals UI.
// No separate refreshAll() needed — the splash handles the initial load.
_refreshing = true; // prevent countdown from triggering refreshAll during boot
_runBootSequence();

// ── SSE delivery (global — used by queue drain and SSE handler) ──
function _deliverSSEDirect(data) {
    // Show panel — if wings are already active, show notification banner instead
    if (data.panel && typeof voice !== 'undefined' && voice._renderAnalysisPanel) {
        const wingL = document.getElementById('analysis-wing-left');
        const panelActive = wingL && wingL.classList.contains('active');
        if (panelActive) {
            _showPanelNotif(data.panel, voice);
        } else {
            voice._renderAnalysisPanel(data.panel, true);
        }
    }
    // Speak the message if requested — but never talk over an active conversation
    if (data.speak && data.message && typeof voice !== 'undefined') {
        const busy = voice._processingQuery || voice.speaking || voice._chatMode;
        if (!busy) {
            voice._speak(data.message);
        }
    }
    // Log it
    if (typeof logConvo === 'function') {
        logConvo(data.message || data.title, 'arbiter');
    }
    // Flash notification in title bar
    const origTitle = document.title;
    document.title = `[!] ${data.title}`;
    setTimeout(() => { document.title = origTitle; }, 10000);
}

// ── SSE: Proactive Notifications from Scheduler ─────────────────
(function initSSE() {
    let retryDelay = 1000;
    function connect() {
        const es = new EventSource('/api/events');
        es.onopen = () => {
            console.log('[SSE] Connected to event stream');
            retryDelay = 1000;
        };
        // Queue for deferred SSE notifications (while a query is processing or speaking)
        let _sseQueue = [];

        es.onmessage = (evt) => {
            try {
                const data = JSON.parse(evt.data);
                if (data.type === 'connected') {
                    console.log('[SSE] Scheduler jobs:', data.jobs);
                    return;
                }
                if (data.type === 'briefing' || data.type === 'notification') {
                    console.log(`[SSE] ${data.type}: ${data.title}`);

                    // Don't interrupt an active query, speech, or hands-on mode — queue it
                    const busy = typeof voice !== 'undefined' && (voice._processingQuery || voice.speaking || voice._chatMode);
                    if (busy) {
                        console.log('[SSE] Queued notification (busy/chat):', data.title);
                        _sseQueue.push(data);
                        return;
                    }

                    _deliverSSE(data);
                }
            } catch (e) {
                console.warn('[SSE] Parse error:', e);
            }
        };

        function _deliverSSE(data) {
            // Queue if a dock panel is open — never overlay CEO or other panels
            if (typeof activeDock !== 'undefined' && activeDock) {
                _queueUpdate({ type: 'sse', data });
                return;
            }
            _deliverSSEDirect(data);
        }

        // Drain queued SSE notifications after voice goes idle
        setInterval(() => {
            if (_sseQueue.length === 0) return;
            const busy = typeof voice !== 'undefined' && (voice._processingQuery || voice.speaking);
            if (!busy && _sseQueue.length > 0) {
                const next = _sseQueue.shift();
                _deliverSSE(next);
            }
        }, 2000);
        es.onerror = () => {
            console.warn('[SSE] Connection lost, retrying in', retryDelay, 'ms');
            es.close();
            setTimeout(connect, retryDelay);
            retryDelay = Math.min(retryDelay * 2, 30000);
        };
    }
    connect();
})();
