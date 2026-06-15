/* ================================================================
   ARBITER — Jarvis HUD Controller
   Orb animation + Voice I/O + Dashboard polling
   ================================================================ */

const REFRESH_INTERVAL = 60_000;
let countdown = REFRESH_INTERVAL / 1000;

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

    _resize() {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        const size = Math.min(rect.width, rect.height, 740);
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

        // Active follow-up options (for voice command selection)
        this._activeFollowups = null;

        // Audio analyser for real-time mic level → orb waveform
        this._audioCtx = null;
        this._analyser = null;
        this._micStream = null;
        this._levelRAF = null;

        this._initRecognition();
        this._initUI();

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
        // Suppress while a query is being processed
        if (this._processingQuery) return;
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
            if (this.speaking) return; // don't listen while Arbiter is talking
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
                logConvo('Microphone access denied. Check browser permissions.', 'system');
                this._mode = 'off';
                this._running = false;
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

            // NEVER restart recognition while speaking — mic would hear the output
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

            // Default: restart passive
            if (this._mode === 'off' && !this.speaking) {
                setTimeout(() => this._requestStart('passive'), 1000);
            }
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

        // Click orb to toggle chat mode
        const orbCanvas = document.getElementById('orb-canvas');
        if (orbCanvas) orbCanvas.addEventListener('click', () => this._toggleChatMode());

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
        // Align the chat panel's bottom edge with the business summary box's bottom edge
        const revBox = document.getElementById('revenue-summary-bar');
        const panel = document.getElementById('chat-panel');
        if (!revBox || !panel) return;

        requestAnimationFrame(() => {
            const revRect = revBox.getBoundingClientRect();
            const viewH = window.innerHeight;
            // Distance from bottom of viewport to bottom of revenue box
            const bottomGap = viewH - revRect.bottom;
            panel.style.bottom = Math.max(bottomGap, 16) + 'px';

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
        this._clearDialogueOptions();
        // Add user message to chat panel
        this._chatAddMessage(text, 'user');

        // Show thinking indicator
        const thinkEl = document.createElement('div');
        thinkEl.className = 'chat-msg thinking';
        thinkEl.id = 'chat-thinking';
        thinkEl.textContent = 'Analysing';
        const container = document.getElementById('chat-messages');
        if (container) { container.appendChild(thinkEl); container.scrollTop = container.scrollHeight; }

        // Also send through the normal pipeline (updates history, panels, etc.)
        this.orb.setState('thinking');
        this.history.push({ role: 'user', content: text });
        logConvo(text, 'user');

        try {
            const r = await fetch('/api/jarvis/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, history: this.history }),
            });
            const d = await r.json();
            const rawReply = d.reply || 'No response.';

            // Remove thinking indicator
            const think = document.getElementById('chat-thinking');
            if (think) think.remove();

            if (d.error) {
                this._chatAddMessage(rawReply, 'system');
                logConvo(rawReply, 'system');
                this.orb.setState('idle');
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

            // Add response to chat panel (no speech in hands-on mode)
            this._chatAddMessage(spokenText, 'assistant');
            logConvo(spokenText, 'arbiter');
            this.orb.setState('idle');

            // Show dialogue follow-up options (chat panel only in hands-on mode)
            console.log('[ARBITER] followups:', d.followups);
            if (d.followups && Array.isArray(d.followups) && d.followups.length > 0) {
                // In hands-on mode, only show in chat panel — NOT in background #dialogue-options
                this._chatRenderFollowups(d.followups);
            }
        } catch (e) {
            console.error('[ARBITER] Chat error:', e);
            const think = document.getElementById('chat-thinking');
            if (think) think.remove();
            this._chatAddMessage('Connection error. Backend may be offline.', 'system');
            logConvo('Connection error. Backend may be offline.', 'system');
            this.orb.setState('idle');
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

        const hintLabels = { deeper: '🔍 DEEPER', compare: '⚖ COMPARE', action: '▶ ACTION', broader: '🌐 BROADER' };

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

        // ── Voice intercepts — handle UI commands before hitting the LLM ──
        const lower = text.toLowerCase().trim();
        const dismissPatterns = [
            /^(dismiss|close|hide|clear)\s*(panel|panels|view|views|that|it|this)?$/,
            /^(thank\s*you|thanks|cheers|ta)\s*(arbiter)?[.!]?$/,
            /^that['']?s?\s*(all|enough|it|fine|good)\s*(arbiter)?[.!]?$/,
            /^(go\s*away|never\s*mind|cancel)\s*(arbiter)?[.!]?$/,
        ];
        if (dismissPatterns.some(p => p.test(lower))) {
            this._closeAnalysisWings();
            logConvo(text, 'user');
            logConvo('Panels dismissed.', 'system');
            this.orb.setState('idle');
            this._speak('Dismissed, Sir.');
            this._processingQuery = false;
            setTimeout(() => this._requestStart('passive'), 500);
            return;
        }

        this._clearDialogueOptions();
        this.orb.setState('thinking');
        this.orb.setAudioLevel(0);
        this.history.push({ role: 'user', content: text });
        logConvo(text, 'user');
        logConvo('Processing...', 'system');

        try {
            const r = await fetch('/api/jarvis/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, history: this.history }),
            });
            const d = await r.json();

            const rawReply = d.reply || 'No response.';

            // If the backend flagged an error, show it and return to idle
            if (d.error) {
                logConvo(rawReply, 'system');
                this.orb.setState('idle');
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

            logConvo(spokenText, 'arbiter');
            this._speak(spokenText);

            // Show dialogue follow-up options
            console.log('[ARBITER] followups (voice):', d.followups);
            if (d.followups && Array.isArray(d.followups) && d.followups.length > 0) {
                this._renderDialogueOptions(d.followups);
            }
        } catch (e) {
            console.error('[ARBITER] Chat error:', e);
            this.orb.setState('idle');
            logConvo('Connection error. Backend may be offline.', 'system');
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
            default:
                console.log('[ARBITER] Unknown action:', action.action);
        }
    }

    // ── Analysis Wing Panel Renderer (dual inline panels) ───────
    _renderAnalysisPanel(panel) {
        const wingL = document.getElementById('analysis-wing-left');
        const wingR = document.getElementById('analysis-wing-right');
        const bodyL = document.getElementById('analysis-body-left');
        const bodyR = document.getElementById('analysis-body-right');
        const titleL = document.getElementById('analysis-title-left');
        const titleR = document.getElementById('analysis-title-right');
        if (!wingL || !wingR || !bodyL || !bodyR) return;

        // Close existing panels first — clean slate for new content
        this._closeAnalysisWings();

        // Destroy previous charts
        if (this._analysisCharts) { this._analysisCharts.forEach(c => c.destroy()); }
        this._analysisCharts = [];
        if (this._analysisChart) { this._analysisChart.destroy(); this._analysisChart = null; }

        bodyL.innerHTML = '';
        bodyR.innerHTML = '';

        // Split content: left wing = charts/tables/images, right wing = stats/summary/hero/status_grid
        const sections = panel.sections || [panel];

        // Collect left-side and right-side content from all sections
        const leftData = { chart: null, table: null, image_url: null, comparison_matrix: null, title: panel.title || 'ANALYSIS' };
        const rightData = { stats: [], hero: null, status_grid: null, summary: null,
            insights: [], recommendations: [], scorecard: null, trend_indicators: null, title: 'INSIGHTS' };

        for (const section of sections) {
            if (section.chart && !leftData.chart) leftData.chart = section.chart;
            if (section.table && !leftData.table) leftData.table = section.table;
            if (section.image_url && !leftData.image_url) leftData.image_url = section.image_url;
            if (section.comparison_matrix && !leftData.comparison_matrix) leftData.comparison_matrix = section.comparison_matrix;
            if (section.hero && !rightData.hero) rightData.hero = section.hero;
            if (section.status_grid) rightData.status_grid = section.status_grid;
            if (section.stats && section.stats.length) rightData.stats = rightData.stats.concat(section.stats);
            if (section.summary) rightData.summary = section.summary;
            if (section.insights && section.insights.length) rightData.insights = rightData.insights.concat(section.insights);
            if (section.recommendations && section.recommendations.length) rightData.recommendations = rightData.recommendations.concat(section.recommendations);
            if (section.scorecard && !rightData.scorecard) rightData.scorecard = section.scorecard;
            if (section.trend_indicators && !rightData.trend_indicators) rightData.trend_indicators = section.trend_indicators;
        }

        // If there's a section title from the panel, use it
        if (panel.title) {
            leftData.title = panel.title;
            rightData.title = panel.title + ' — INSIGHTS';
        }

        titleL.textContent = leftData.title;
        titleR.textContent = rightData.title;

        // Determine what goes where
        const hasLeft = leftData.chart || leftData.table || leftData.image_url || leftData.comparison_matrix;
        const hasRight = rightData.stats.length || rightData.hero || rightData.status_grid || rightData.summary
            || rightData.insights.length || rightData.recommendations.length || rightData.scorecard || rightData.trend_indicators;

        if (hasLeft) {
            this._renderSection(bodyL, {
                chart: leftData.chart,
                table: leftData.table,
                image_url: leftData.image_url,
                comparison_matrix: leftData.comparison_matrix,
            });
        } else {
            // No chart/table — put stats on left, keep right for analysis
            const halfStats = rightData.stats.splice(0, Math.ceil(rightData.stats.length / 2));
            this._renderSection(bodyL, { stats: halfStats, hero: rightData.hero, status_grid: rightData.status_grid,
                trend_indicators: rightData.trend_indicators });
            rightData.hero = null;
            rightData.status_grid = null;
            rightData.trend_indicators = null;
        }

        if (hasRight || rightData.stats.length || rightData.summary) {
            this._renderSection(bodyR, {
                hero: rightData.hero,
                status_grid: rightData.status_grid,
                stats: rightData.stats,
                trend_indicators: rightData.trend_indicators,
                scorecard: rightData.scorecard,
                insights: rightData.insights,
                recommendations: rightData.recommendations,
                summary: rightData.summary,
            });
        } else {
            for (const section of sections) {
                this._renderSection(bodyR, section);
            }
        }

        // Show both wings
        wingL.classList.add('active');
        wingR.classList.add('active');

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

        // ── Chart (bar, hbar, line, area, doughnut, pie) ──
        if (section.chart) {
            const wrap = document.createElement('div');
            wrap.className = 'analysis-chart';
            const canvas = document.createElement('canvas');
            wrap.appendChild(canvas);
            container.appendChild(wrap);

            const c = section.chart;
            const isHbar = c.type === 'hbar';
            const isArea = c.type === 'area';
            const chartType = isHbar ? 'bar' : isArea ? 'line' : (c.type || 'bar');

            let datasets;
            if (c.datasets) {
                datasets = c.datasets.map((ds, i) => ({
                    label: ds.label || '',
                    data: ds.data || [],
                    borderColor: colors[i % colors.length],
                    backgroundColor: (chartType === 'line' || isArea) ? bgColors[i % bgColors.length] : colors.map((_, j) => colors[j % colors.length]),
                    borderWidth: (chartType === 'line') ? 2 : 0,
                    pointRadius: (chartType === 'line') ? 3 : 0,
                    fill: (chartType === 'line'),
                    tension: 0.4,
                    yAxisID: ds.yAxisID || undefined,
                }));
            } else {
                // Single dataset from labels/values
                const barColors = isHbar
                    ? (c.values || []).map(v => v >= 0 ? 'rgba(0,255,136,0.75)' : 'rgba(255,51,85,0.75)')
                    : (c.values || []).map((_, i) => colors[i % colors.length]);
                datasets = [{
                    label: c.label || '',
                    data: c.values || [],
                    backgroundColor: barColors,
                    borderWidth: 0,
                }];
            }

            const opts = {
                responsive: true, maintainAspectRatio: false,
                indexAxis: isHbar ? 'y' : 'x',
                animation: { duration: 600 },
                plugins: {
                    legend: {
                        display: !!(c.datasets && c.datasets.length > 1),
                        labels: { color: '#7a9aaa', font: { size: 11, family: "'Courier New'" } }
                    }
                },
            };

            if (chartType === 'doughnut' || chartType === 'pie') {
                opts.scales = {};
            } else {
                opts.scales = {
                    x: { ticks: { color: '#5a7a8a', font: { size: 10 } }, grid: { color: 'rgba(60,220,255,0.06)' } },
                    y: { ticks: { color: '#5a7a8a', font: { size: 10 } }, grid: { color: 'rgba(60,220,255,0.06)' } },
                };
                // Support dual y-axis (e.g. precipitation on weather chart)
                if (c.datasets && c.datasets.some(ds => ds.yAxisID === 'y1')) {
                    opts.scales.y1 = {
                        position: 'right', grid: { drawOnChartArea: false },
                        ticks: { color: '#5a7a8a', font: { size: 10 } },
                    };
                }
            }

            const chart = new Chart(canvas, { type: chartType, data: { labels: c.labels || [], datasets }, options: opts });
            this._analysisCharts.push(chart);
            this._analysisChart = chart;
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
            const table = document.createElement('table');
            table.className = 'analysis-table';
            if (t.headers) {
                const thead = document.createElement('thead');
                const tr = document.createElement('tr');
                for (const h of t.headers) { const th = document.createElement('th'); th.textContent = h; tr.appendChild(th); }
                thead.appendChild(tr);
                table.appendChild(thead);
            }
            if (t.rows) {
                const tbody = document.createElement('tbody');
                for (const row of t.rows) {
                    const tr = document.createElement('tr');
                    for (const cell of row) {
                        const td = document.createElement('td');
                        const str = String(cell);
                        if (str.startsWith('+') || str.includes('↑')) td.className = 'at-positive';
                        else if (str.startsWith('-') || str.includes('↓')) td.className = 'at-negative';
                        td.textContent = str;
                        tr.appendChild(td);
                    }
                    tbody.appendChild(tr);
                }
                table.appendChild(tbody);
            }
            container.appendChild(table);
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
        text = this._cleanForTTS(text);             // strip formatting before TTS
        this.orb.setState('speaking');
        this.speaking = true;
        this._currentAudio = null;

        // Show stop button
        const stopBtn = document.getElementById('btn-stop');
        if (stopBtn) stopBtn.style.display = '';

        // ── Kill mic recognition while speaking so it doesn't hear the output ──
        this._mode = 'off';
        this._pendingStart = null;
        try { this.recognition.stop(); } catch (_) {}
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
        'system': '⚙ SYSTEM',
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
}

// ── API helper ───────────────────────────────────────────────────
async function api(path) {
    try {
        const r = await fetch(path);
        if (!r.ok) return null;
        return await r.json();
    } catch { return null; }
}

// ── System Status ────────────────────────────────────────────────
let firstStatusCheck = true;
async function refreshStatus() {
    const d = await api('/api/status');
    if (!d) return;
    const s = d.systems;
    setDot('s-content-db', s.content_db.status);
    setDot('s-engage-db', s.engagement_db.status);

    const badge = document.getElementById('system-badge');
    const allOnline = s.content_db.status === 'online' && s.engagement_db.status === 'online';
    const allOffline = s.content_db.status !== 'online' && s.engagement_db.status !== 'online';
    badge.textContent = allOnline ? '● ALL SYSTEMS NOMINAL' : allOffline ? '● SYSTEMS OFFLINE' : '● DEGRADED';
    badge.className = 'system-status ' + (allOnline ? 'online' : allOffline ? 'offline' : 'degraded');

    // Show startup guide on first check if any system is offline
    if (firstStatusCheck && !allOnline) {
        firstStatusCheck = false;
        showStartupGuide(s);
    } else {
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
        { name: 'Content DB', status: systems.content_db.status, hint: 'Content Database' },
        { name: 'Engage DB', status: systems.engagement_db.status, hint: 'Engagement Database' },
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
    if (systems.content_db.status !== 'online') {
        instr += `<p>Content DB will populate automatically when content is created via the CMS.</p>`;
    }
    if (systems.engagement_db.status !== 'online') {
        instr += `<p>Engagement DB will populate automatically when user interactions are tracked.</p>`;
    }
    instrEl.innerHTML = instr;

    overlay.classList.add('active');

    document.getElementById('startup-dismiss').addEventListener('click', () => {
        overlay.classList.remove('active');
    });
}

// ── CI/CD — Grow with Freya ─────────────────────────────────────
const CICD_JOBS = [
    { name: 'CMS Upload', key: 'cms_upload', url: '#' },
    { name: 'App Build & Release', key: 'app_build', url: '#' },
    { name: 'Backend API', key: 'backend_api', url: '#' },
    { name: 'EAS Build', key: 'eas_build', url: '#' },
];

async function refreshCICD() {
    // Try fetching from backend; fall back to mock
    let data = null;
    try {
        const resp = await fetch('/api/cicd');
        if (resp.ok) data = await resp.json();
    } catch (e) { /* no endpoint yet */ }

    const grid = document.getElementById('cicd-grid');
    if (!grid) return;

    let passCount = 0, failCount = 0;
    let html = '';
    CICD_JOBS.forEach(job => {
        const status = data && data[job.key] ? data[job.key].status : 'unknown';
        const time = data && data[job.key] ? data[job.key].time || '' : '';
        const url = data && data[job.key] && data[job.key].url ? data[job.key].url : job.url;
        if (status === 'success') passCount++;
        if (status === 'failure') failCount++;
        html += `<div class="cicd-job">
            <span class="cicd-status ${status}"></span>
            <span class="cicd-name">${job.name}</span>
            ${time ? `<span class="cicd-time">${time}</span>` : ''}
            ${url !== '#' ? `<a class="cicd-link" href="${url}" target="_blank">VIEW</a>` : `<span class="cicd-time">NO BUILD</span>`}
        </div>`;
    });
    grid.innerHTML = html;

    // Update dock badge
    const dockPass = document.getElementById('dock-cicd-pass');
    const dockFail = document.getElementById('dock-cicd-fail');
    if (dockPass) dockPass.textContent = passCount;
    if (dockFail) dockFail.textContent = failCount;
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
}

// ── Urgent Bulletins ─────────────────────────────────────────────
async function refreshBulletins() {
    const d = await api('/api/bulletins');
    // Update both: hidden dock panel and live top-left panel
    const els = [document.getElementById('bulletin-feed'), document.getElementById('bulletin-feed-live')];
    if (!d || d.length === 0) {
        els.forEach(el => { if (el) el.innerHTML = '<div class="feed-empty">All systems nominal.</div>'; });
        return;
    }
    const html = d.map(b => `
        <div class="bulletin-item">
            <span class="bull-level ${b.level}">${b.level.toUpperCase()}</span>
            <span class="bull-source">${b.source}</span>
            <span class="bull-msg">${b.message}</span>
        </div>`).join('');
    els.forEach(el => { if (el) el.innerHTML = html; });
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
    'AI':      ['OpenAI', 'Claude'],
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

// ── Weather ─────────────────────────────────────────────────────
const WMO_ICONS = {
    0:'☀️',1:'🌤',2:'⛅',3:'☁️',45:'🌫',48:'🌫',51:'🌦',53:'🌧',55:'🌧',
    56:'🌨',57:'🌨',61:'🌧',63:'🌧',65:'🌧',66:'🌨',67:'🌨',71:'❄️',73:'❄️',
    75:'❄️',77:'🌨',80:'🌦',81:'🌧',82:'⛈',85:'❄️',86:'❄️',95:'⛈',96:'⛈',99:'⛈',
};
const WMO_DESC = {
    0:'Clear',1:'Mostly Clear',2:'Partly Cloudy',3:'Overcast',45:'Fog',48:'Rime Fog',
    51:'Light Drizzle',53:'Drizzle',55:'Heavy Drizzle',61:'Light Rain',63:'Rain',
    65:'Heavy Rain',71:'Light Snow',73:'Snow',75:'Heavy Snow',80:'Showers',
    81:'Heavy Showers',82:'Violent Showers',95:'Thunderstorm',96:'Hail Storm',99:'Severe Storm',
};
const DAY_NAMES = ['SUN','MON','TUE','WED','THU','FRI','SAT'];

async function refreshWeather() {
    const data = await api('/api/weather');
    const card = document.getElementById('weather-card');
    if (!card || !data || !data.current) return;
    const c = data.current;
    const wc = c.weather_code ?? 0;
    const icon = WMO_ICONS[wc] || '🌡';
    const desc = WMO_DESC[wc] || 'Unknown';
    let html = `<div class="weather-main">
        <span class="weather-icon">${icon}</span>
        <div>
            <div class="weather-temp">${Math.round(c.temperature_2m || 0)}°C</div>
            <div class="weather-desc">${desc}</div>
        </div>
    </div>
    <div class="weather-details">
        <span>Feels ${Math.round(c.apparent_temperature || 0)}°C</span>
        <span>💧 ${c.relative_humidity_2m || 0}%</span>
        <span>💨 ${Math.round(c.wind_speed_10m || 0)} km/h</span>
    </div>`;
    const daily = data.daily || {};
    if (daily.time && daily.time.length) {
        html += '<div class="weather-forecast">';
        for (let i = 0; i < Math.min(3, daily.time.length); i++) {
            const d = new Date(daily.time[i]);
            const dn = DAY_NAMES[d.getDay()];
            const dIcon = WMO_ICONS[daily.weather_code?.[i]] || '🌡';
            html += `<div class="weather-day">
                <div>${dn}</div>
                <div class="wd-icon">${dIcon}</div>
                <div class="wd-temp">${Math.round(daily.temperature_2m_max?.[i] || 0)}° / ${Math.round(daily.temperature_2m_min?.[i] || 0)}°</div>
            </div>`;
        }
        html += '</div>';
    }
    card.innerHTML = html;
    // Dock stats
    const wTemp = document.getElementById('dock-wx-temp');
    const wDesc = document.getElementById('dock-wx-desc');
    if (wTemp) wTemp.textContent = `${Math.round(c.temperature_2m || 0)}°`;
    if (wDesc) wDesc.textContent = c.is_day ? 'DAY' : 'NIGHT';
}

// ── Expand Panels (left + right flanking orb) ───────────────────
// Each dock tile maps to a LEFT panel (primary data) and RIGHT panel (secondary/chart)
const DOCK_EXPAND = {
    email:     { left: 'EMAIL INTELLIGENCE',    right: 'EMAIL ANALYTICS',     leftPanel: 'dock-panel-email',     rightPanel: null },
    revenue:   { left: 'REVENUE OVERVIEW',      right: 'REVENUE ANALYTICS',   leftPanel: 'dock-panel-revenue',   rightPanel: null },
    content:   { left: 'CONTENT PIPELINE',      right: 'CONTENT QUEUE',       leftPanel: 'dock-panel-content',   rightPanel: null },
    engage:    { left: 'ENGAGEMENT HUB',        right: 'ENGAGEMENT DATA',     leftPanel: 'dock-panel-engage',    rightPanel: null },
    weather:   { left: 'WEATHER — UK',          right: null,                  leftPanel: 'dock-panel-weather',   rightPanel: null },
    deadlines: { left: 'DEADLINES & ROADMAP',   right: null,                  leftPanel: 'dock-panel-deadlines', rightPanel: null },
    bulletins: { left: 'BULLETINS',             right: 'LIVE FEED',           leftPanel: 'dock-panel-bulletins', rightPanel: 'dock-panel-activity' },
    activity:  { left: 'LIVE FEED',             right: 'INTELLIGENCE',        leftPanel: 'dock-panel-activity',  rightPanel: 'dock-panel-intelligence' },
    cicd:      { left: 'CI/CD — GROW WITH FREYA', right: null,                leftPanel: 'dock-panel-cicd',    rightPanel: null },
};

let activeDock = null;
let _panelTransitioning = false;

function openExpandPanels(panelKey) {
    const cfg = DOCK_EXPAND[panelKey];
    if (!cfg) return;
    if (_panelTransitioning) return;

    // Toggle off if same
    if (activeDock === panelKey) { closeExpandPanels(); return; }

    // If another panel is open, close it first then open the new one after transition
    if (activeDock) {
        _panelTransitioning = true;
        closeExpandPanels();
        setTimeout(() => {
            _panelTransitioning = false;
            openExpandPanels(panelKey);
        }, 350); // match CSS transition duration
        return;
    }

    const leftEl = document.getElementById('expand-left');
    const rightEl = document.getElementById('expand-right');
    const leftBody = document.getElementById('expand-left-body');
    const rightBody = document.getElementById('expand-right-body');
    const leftTitle = document.getElementById('expand-left-title');
    const rightTitle = document.getElementById('expand-right-title');
    const floatRight = document.getElementById('float-right');
    if (!leftEl || !rightEl || !leftBody || !rightBody) return;

    // Move left panel content
    const leftSrc = cfg.leftPanel ? document.getElementById(cfg.leftPanel) : null;
    if (leftSrc) {
        leftBody.innerHTML = '';
        leftBody.appendChild(leftSrc);
        leftSrc.style.display = 'block';
        leftTitle.textContent = cfg.left || '';
        leftEl.classList.add('active');
    } else {
        leftEl.classList.remove('active');
        leftBody.innerHTML = '';
        leftTitle.textContent = '';
    }

    // Move right panel content
    const rightSrc = cfg.rightPanel ? document.getElementById(cfg.rightPanel) : null;
    if (rightSrc) {
        rightBody.innerHTML = '';
        rightBody.appendChild(rightSrc);
        rightSrc.style.display = 'block';
        rightTitle.textContent = cfg.right || '';
        rightEl.classList.add('active');
    } else {
        rightEl.classList.remove('active');
        rightBody.innerHTML = '';
        rightTitle.textContent = '';
    }

    // Hide floating panels to make room (fade out, not display:none)
    if (floatRight) floatRight.classList.add('hidden');
    const floatLeft = document.getElementById('float-left');
    if (floatLeft) floatLeft.classList.add('hidden');

    activeDock = panelKey;

    // Highlight active dock tile
    document.querySelectorAll('.dock-panel[data-dock]').forEach(t => t.classList.remove('active'));
    const tile = document.querySelector(`.dock-panel[data-dock="${panelKey}"]`);
    if (tile) tile.classList.add('active');
}

function closeExpandPanels() {
    const leftEl = document.getElementById('expand-left');
    const rightEl = document.getElementById('expand-right');
    const leftBody = document.getElementById('expand-left-body');
    const rightBody = document.getElementById('expand-right-body');
    const panels = document.getElementById('dock-panels');

    // Move content back to hidden container
    [leftBody, rightBody].forEach(body => {
        if (!body) return;
        const child = body.querySelector('.dock-panel-inner');
        if (child && panels) {
            child.style.display = 'none';
            panels.appendChild(child);
        }
        body.innerHTML = ''; // clear to prevent stale content flashing
    });

    // Remove active state from both panels
    if (leftEl) leftEl.classList.remove('active');
    if (rightEl) rightEl.classList.remove('active');

    // Clear titles
    const leftTitle = document.getElementById('expand-left-title');
    const rightTitle = document.getElementById('expand-right-title');
    if (leftTitle) leftTitle.textContent = '';
    if (rightTitle) rightTitle.textContent = '';

    // Restore floating side panels (fade in)
    const floatRight = document.getElementById('float-right');
    const floatLeft = document.getElementById('float-left');
    if (floatRight) floatRight.classList.remove('hidden');
    if (floatLeft) floatLeft.classList.remove('hidden');

    // Force globe to recalculate size after being re-shown
    if (gcpGlobe) {
        gcpGlobe.W = 0;
        gcpGlobe.H = 0;
    }

    activeDock = null;
    document.querySelectorAll('.dock-panel[data-dock]').forEach(t => t.classList.remove('active'));
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
    const catIcons = { launch: '🚀', milestone: '📌', campaign: '📣', review: '📋' };
    const statusCls = { planned: 'upcoming', in_progress: 'soon', completed: 'completed',
                        at_risk: 'overdue', blocked: 'overdue' };

    // Sort by date
    const sorted = [..._roadmapData].sort((a, b) => new Date(a.date) - new Date(b.date));

    // ── Year-view timeline ──
    let html = '<div class="roadmap-timeline">';

    // Group by quarter
    const quarters = {};
    sorted.forEach(m => {
        const q = m.quarter || 'Other';
        if (!quarters[q]) quarters[q] = [];
        quarters[q].push(m);
    });

    for (const [quarter, items] of Object.entries(quarters)) {
        html += `<div class="rm-quarter">
            <div class="rm-quarter-label">${quarter}</div>
            <div class="rm-quarter-items">`;

        items.forEach(m => {
            const target = new Date(m.date);
            const diffDays = Math.ceil((target - now) / (1000 * 60 * 60 * 24));
            const icon = catIcons[m.category] || '📌';
            const urgency = m.status === 'completed' ? 'completed'
                : diffDays < 0 ? 'overdue'
                : diffDays <= 30 ? 'soon' : 'upcoming';
            const dateStr = target.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

            let countdownText = '';
            if (m.status === 'completed') countdownText = '✓ DONE';
            else if (diffDays < 0) countdownText = `${Math.abs(diffDays)}d OVER`;
            else countdownText = `${diffDays}d`;

            if (!nextDeadline && diffDays >= 0 && m.status !== 'completed') {
                nextDeadline = { ...m, days: diffDays };
            }

            const priorityBadge = m.priority === 'critical' ? ' <span class="rm-priority critical">CRIT</span>'
                : m.priority === 'high' ? ' <span class="rm-priority high">HIGH</span>' : '';

            const statusBadge = m.status === 'in_progress' ? ' <span class="rm-status active">ACTIVE</span>'
                : m.status === 'at_risk' ? ' <span class="rm-status at-risk">AT RISK</span>'
                : m.status === 'completed' ? ' <span class="rm-status done">DONE</span>' : '';

            html += `<div class="deadline-item ${urgency}" data-id="${m.id}" title="${m.description || ''}">
                <span class="dl-icon">${icon}</span>
                <span class="dl-date">${dateStr}</span>
                <span class="dl-title">${m.title}${priorityBadge}${statusBadge}</span>
                <span class="dl-countdown ${urgency}">${countdownText}</span>
            </div>`;
        });
        html += '</div></div>';
    }
    html += '</div>';

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

document.addEventListener('DOMContentLoaded', () => {
    // Dock panel clicks
    document.querySelectorAll('.dock-panel[data-dock]').forEach(tile => {
        tile.addEventListener('click', () => openExpandPanels(tile.dataset.dock));
    });
    // Close button
    const closeBtn = document.getElementById('expand-close');
    if (closeBtn) closeBtn.addEventListener('click', closeExpandPanels);
    // ESC key
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && activeDock) closeExpandPanels();
    });
    // Init deadlines
    refreshDeadlines();
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
            refreshWeather().catch(e => console.warn('refreshWeather error:', e)),
            refreshCICD().catch(e => console.warn('refreshCICD error:', e)),
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
refreshAll();

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
            // Show panel if provided
            if (data.panel && typeof voice !== 'undefined' && voice._renderAnalysisPanel) {
                voice._renderAnalysisPanel(data.panel);
            }
            // Speak the message if requested
            if (data.speak && data.message && typeof voice !== 'undefined') {
                voice._speak(data.message);
            }
            // Log it
            if (typeof logConvo === 'function') {
                logConvo(data.message || data.title, 'arbiter');
            }
            // Flash notification in title bar
            const origTitle = document.title;
            document.title = `🔔 ${data.title}`;
            setTimeout(() => { document.title = origTitle; }, 10000);
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
