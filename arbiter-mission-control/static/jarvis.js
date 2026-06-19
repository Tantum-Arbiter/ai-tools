/* ================================================================
   ARBITER — Jarvis HUD Controller
   Orb animation + Voice I/O + Dashboard polling
   ================================================================ */

const REFRESH_INTERVAL = 60_000;
let countdown = REFRESH_INTERVAL / 1000;

// ── SVG Icon Library (replaces emojis) ──────────────────────────
const _SVG = (name, size = 16) => {
    const icons = {
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

        // Audio analyser for real-time mic level → orb waveform
        this._audioCtx = null;
        this._analyser = null;
        this._micStream = null;
        this._levelRAF = null;

        this._initRecognition();
        this._initUI();
        this._initLock();

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

                        // ── Interrupt speech if currently speaking ──
                        if (this.speaking) {
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

            // While speaking, only allow passive wake-word listening (for interrupt)
            if (this.speaking) {
                if (this._pendingStart === 'passive') {
                    setTimeout(() => this._doStart('passive'), 50);
                    return;
                }
                // Passive mode timed out during speech — restart it
                if (this._mode === 'passive') {
                    setTimeout(() => this._doStart('passive'), 200);
                    return;
                }
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
            weather:   [/\b(weather|forecast|temperature|rain)\b/],
            deadlines: [/\b(deadline|roadmap|milestone)\b/],
            bulletins: [/\b(bulletin|news|feed)\b/],
            todo:      [/\b(todo|to.do|tasks?|list)\b/],
            cicd:      [/\b(ci\s*cd|deploy|build|pipeline|freya)\b/],
            claude:    [/\b(claude|api\s*usage|token)\b/],
            ceo:       [/\b(ceo|orchestrat|agents?)\b/],
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

        // Click orb to toggle chat mode
        const orbCanvas = document.getElementById('orb-canvas');
        if (orbCanvas) orbCanvas.addEventListener('click', () => {
            if (_cam.active) return; // no chat mode during vision
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
        // Stop any current speech immediately when user sends a new message
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
            this._chatAddMessage(navResult.speak, 'assistant');
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
        this.history.push({ role: 'user', content: text });
        logConvo(text, 'user');

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
                    });
                    d = await r.json();
                    _camScanStop();
                } else {
                    r = await fetch('/api/jarvis/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: text, history: this.history }),
                    });
                    d = await r.json();
                }
            } else {
                r = await fetch('/api/jarvis/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, history: this.history }),
                });
                d = await r.json();
            }
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

            // Cache this exchange for session report
            this._cacheExchange(text, spokenText, d.panel || null);

            // Render vision panels if camera is active
            if (_cam.active && spokenText) {
                _camRenderVisionPanels(spokenText, text);
            }

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
            _camScanStop();
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
        this.history.push({ role: 'user', content: text });
        logConvo(text, 'user');
        logConvo('Processing...', 'system');

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
                    });
                    d = await r.json();
                    _camScanStop();
                } else {
                    r = await fetch('/api/jarvis/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: text, history: this.history }),
                    });
                    d = await r.json();
                }
            } else {
                r = await fetch('/api/jarvis/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, history: this.history }),
                });
                d = await r.json();
            }

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

            // Cache this exchange for session report
            this._cacheExchange(text, spokenText, d.panel || null);

            // Render vision panels if camera is active
            if (_cam.active && spokenText) {
                _camRenderVisionPanels(spokenText, text);
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
            _camScanStop();
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
    _renderAnalysisPanel(panel) {
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

        // Check if wings are already open (content swap vs fresh open)
        const alreadyOpen = wingL.classList.contains('active') || wingR.classList.contains('active');

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

        // ── Keep passive wake-word listening alive during speech so user can interrupt ──
        // The mic stays open in 'passive' mode — only the wake word triggers action.
        // This allows "Arbiter" to interrupt speech and start a new query.
        this._stopLevelPump();  // stop mic level pump (we're using playback level now)
        if (!this._running || this._mode !== 'passive') {
            this._requestStart('passive');
        }

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

// ── Claude Token Usage ──────────────────────────────────────────
async function refreshClaudeUsage() {
    const d = await api('/api/claude-usage');
    if (!d) return;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    // Expanded panel
    set('cl-model', d.model ? d.model.toUpperCase() : '—');
    set('cl-cost', d.daily_cost_usd != null ? `$${Number(d.daily_cost_usd).toFixed(4)}` : '—');
    set('cl-budget', d.daily_budget_usd != null ? `$${Number(d.daily_budget_usd).toFixed(2)}` : '—');
    set('cl-input-tok', d.daily_input_tokens != null ? Number(d.daily_input_tokens).toLocaleString() : '—');
    set('cl-output-tok', d.daily_output_tokens != null ? Number(d.daily_output_tokens).toLocaleString() : '—');
    set('cl-reqs', d.session_requests != null ? `${d.session_requests} / ${d.session_limit || '—'}` : '—');
    set('cl-rpm', d.rpm_limit || '—');
    const cbState = d.circuit_breaker === 'open' ? 'OPEN ⚠' : 'CLOSED ✓';
    set('cl-circuit', cbState);
    // Budget bar
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
    // Dock stats
    const dockCost = document.getElementById('dock-claude-cost');
    const dockReqs = document.getElementById('dock-claude-reqs');
    if (dockCost) {
        dockCost.textContent = d.daily_cost_usd != null ? `$${Number(d.daily_cost_usd).toFixed(3)}` : '—';
        dockCost.className = 'dp-val' + (pct > 80 ? ' alert' : pct > 50 ? ' caution' : ' nominal');
    }
    if (dockReqs) {
        dockReqs.textContent = d.session_requests != null ? d.session_requests : '—';
    }
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
const WMO_ICONS = (() => {
    const s = _SVG('sun',20), cs = _SVG('cloud-sun',20), c = _SVG('cloud',20),
          cr = _SVG('cloud-rain',20), sn = _SVG('snowflake',20),
          fg = _SVG('cloud-fog',20), z = _SVG('zap',20);
    return {
        0:s,1:cs,2:cs,3:c,45:fg,48:fg,51:cr,53:cr,55:cr,
        56:sn,57:sn,61:cr,63:cr,65:cr,66:sn,67:sn,71:sn,73:sn,
        75:sn,77:sn,80:cr,81:cr,82:z,85:sn,86:sn,95:z,96:z,99:z,
    };
})();
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
    const icon = WMO_ICONS[wc] || _SVG('thermometer',20);
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
        <span>${_SVG('droplet',12)} ${c.relative_humidity_2m || 0}%</span>
        <span>${_SVG('wind',12)} ${Math.round(c.wind_speed_10m || 0)} km/h</span>
    </div>`;
    const daily = data.daily || {};
    if (daily.time && daily.time.length) {
        html += '<div class="weather-forecast">';
        for (let i = 0; i < Math.min(3, daily.time.length); i++) {
            const d = new Date(daily.time[i]);
            const dn = DAY_NAMES[d.getDay()];
            const dIcon = WMO_ICONS[daily.weather_code?.[i]] || _SVG('thermometer',18);
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

// ── Full-Page Panel Routing ──────────────────────────────────────
// Each dock tile maps to a title and a panel ID; clicking opens a full-page view
const DOCK_EXPAND = {
    email:     { title: 'EMAIL INTELLIGENCE',       panel: 'dock-panel-email' },
    revenue:   { title: 'REVENUE OVERVIEW',          panel: 'dock-panel-revenue' },
    content:   { title: 'CONTENT PIPELINE',          panel: 'dock-panel-content' },
    engage:    { title: 'ENGAGEMENT HUB',            panel: 'dock-panel-engage' },
    weather:   { title: 'WEATHER — UK',              panel: 'dock-panel-weather' },
    deadlines: { title: 'DEADLINES & ROADMAP',       panel: 'dock-panel-deadlines' },
    bulletins: { title: 'BULLETINS',                 panel: 'dock-panel-bulletins' },
    todo:      { title: 'TODO LIST',                 panel: 'dock-panel-todo' },
    cicd:      { title: 'CI/CD — GROW WITH FREYA',   panel: 'dock-panel-cicd' },
    claude:    { title: 'CLAUDE API USAGE',           panel: 'dock-panel-claude' },
    ceo:       { title: 'CEO ORCHESTRATION',           panel: 'dock-panel-ceo' },
};

let activeDock = null;
let _panelTransitioning = false;

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

    // ── Orb → bottom-right corner (same as camera mode) ──
    const mc = document.querySelector('.mc-center');
    const startRect = mc.getBoundingClientRect();
    const orbCanvas = document.getElementById('orb-canvas');
    const orbW = orbCanvas ? orbCanvas.offsetWidth : startRect.width;
    const scaleFrom = orbW / 130;

    const startCX = startRect.left + startRect.width / 2;
    const startCY = startRect.top + startRect.height / 2;

    if (typeof orb !== 'undefined') orb._resize(130);
    const mcW = mc.offsetWidth;
    const mcH = mc.offsetHeight;

    mc.style.position = 'fixed';
    mc.style.top = (startCY - mcH / 2) + 'px';
    mc.style.left = (startCX - mcW / 2) + 'px';
    mc.style.transformOrigin = 'center center';
    mc.style.transform = `translate(0px, 0px) scale(${scaleFrom})`;
    mc.style.transition = 'none';
    mc.style.zIndex = '600';
    void mc.offsetHeight;

    // Dim dashboard (keeps everything visible)
    document.body.classList.add('panel-mode');

    // Target: bottom-right corner — lift higher so orb clears dock/panels in windowed mode
    const dockEl = document.querySelector('.mc-dock');
    const dockH = dockEl ? dockEl.offsetHeight : 60;
    const bottomPad = dockH + 40;   // clear the dock + breathing room
    const targetTop = window.innerHeight - bottomPad - mcH;
    const targetLeft = window.innerWidth - 32 - mcW;
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
    if (panelKey === 'ceo') _ceoInitPanel();
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

    if (typeof orb !== 'undefined') orb._resize(Math.round(fullSize));
    const mcW = mc.offsetWidth;
    const mcH = mc.offsetHeight;

    const parent = mc.parentElement;
    const parentRect = parent.getBoundingClientRect();
    const targetCX = parentRect.left + parentRect.width / 2;
    const targetCY = parentRect.top + parentRect.height / 2;

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
        mc.style.transition = 'none !important';
        mc.style.cssText = '';
        void mc.offsetHeight;
        _panelTransitioning = false;
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

// ── CEO Orchestration Module ──────────────────────────────────────
let _ceoAgents = null;

async function _ceoInitPanel() {
    const grid = document.getElementById('ceo-agent-grid');
    if (!grid) return;

    // Fetch agent definitions if not cached
    if (!_ceoAgents) {
        try {
            const resp = await fetch('/api/ceo/agents');
            _ceoAgents = await resp.json();
        } catch (e) {
            grid.innerHTML = '<div class="feed-empty">FAILED TO LOAD AGENTS</div>';
            return;
        }
    }

    // Only render if grid is empty (avoid re-render on panel reopen)
    if (grid.children.length > 0 && grid.querySelector('.ceo-agent-card')) return;

    grid.innerHTML = '';
    for (const agent of _ceoAgents) {
        const card = document.createElement('div');
        card.className = 'ceo-agent-card';
        card.style.setProperty('--agent-colour', agent.colour || 'var(--cyan)');
        card.dataset.agentId = agent.id;
        card.innerHTML = `
            <div class="ceo-agent-badge idle"><span class="ceo-dot"></span> idle</div>
            <div class="ceo-agent-icon">${_SVG(agent.icon || 'search', 22)}</div>
            <div class="ceo-agent-name">${agent.name}</div>
            <div class="ceo-agent-role">${agent.role}</div>
            <div class="ceo-agent-desc">${agent.description}</div>
            <div class="ceo-agent-model">MODEL <b>${agent.model}</b></div>
            <div class="ceo-agent-input-row">
                <input type="text" class="ceo-agent-input" placeholder="Task..." autocomplete="off" />
                <button class="ceo-agent-send">▶</button>
            </div>
            <div class="ceo-agent-output"></div>
        `;

        // Wire up send
        const input = card.querySelector('.ceo-agent-input');
        const sendBtn = card.querySelector('.ceo-agent-send');
        const sendFn = () => _ceoDispatch(agent.id, input, card);
        sendBtn.addEventListener('click', sendFn);
        input.addEventListener('keydown', e => { if (e.key === 'Enter' && input.value.trim()) sendFn(); });

        grid.appendChild(card);
    }

    // Wire up broadcast
    const bcastInput = document.getElementById('ceo-broadcast-input');
    const bcastBtn = document.getElementById('ceo-broadcast-btn');
    if (bcastBtn && bcastInput) {
        const bcastFn = () => _ceoBroadcast(bcastInput);
        bcastBtn.onclick = bcastFn;
        bcastInput.onkeydown = e => { if (e.key === 'Enter' && bcastInput.value.trim()) bcastFn(); };
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

function _ceoBadge(cardEl, state, label) {
    const badge = cardEl.querySelector('.ceo-agent-badge');
    if (!badge) return;
    badge.className = `ceo-agent-badge ${state}`;
    badge.innerHTML = `<span class="ceo-dot"></span> ${label}`;
}

async function _ceoDispatch(agentId, inputEl, cardEl) {
    const task = inputEl.value.trim();
    if (!task) return;
    inputEl.value = '';

    const output = cardEl.querySelector('.ceo-agent-output');

    // Set working state
    _ceoBadge(cardEl, 'working', 'working');
    output.classList.add('active');
    output.textContent = 'Processing directive...';
    _ceoRouteCount++;
    _ceoUpdateStats();

    // Set master card to working
    const masterStatus = document.querySelector('#ceo-master-card .ceo-master-status');
    if (masterStatus) { masterStatus.className = 'ceo-master-status working'; masterStatus.innerHTML = '<span class="ceo-dot"></span> ROUTING'; }

    try {
        const resp = await fetch('/api/ceo/dispatch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: agentId, task }),
        });
        const data = await resp.json();
        _ceoReadCount++;
        _ceoUpdateStats();

        if (data.error) {
            _ceoBadge(cardEl, 'error', 'error');
            output.textContent = `Error: ${data.error}`;
        } else {
            _ceoBadge(cardEl, 'ready', 'complete');
            output.textContent = data.response || 'No response';
        }
    } catch (e) {
        _ceoBadge(cardEl, 'error', 'error');
        output.textContent = `Network error: ${e.message}`;
    }

    // Reset master card
    if (masterStatus) { masterStatus.className = 'ceo-master-status ready'; masterStatus.innerHTML = '<span class="ceo-dot"></span> ONLINE'; }
}

async function _ceoBroadcast(inputEl) {
    const task = inputEl.value.trim();
    if (!task) return;
    inputEl.value = '';

    const grid = document.getElementById('ceo-agent-grid');
    if (!grid) return;

    // Set master to working
    const masterStatus = document.querySelector('#ceo-master-card .ceo-master-status');
    if (masterStatus) { masterStatus.className = 'ceo-master-status working'; masterStatus.innerHTML = '<span class="ceo-dot"></span> BROADCASTING'; }

    // Set all cards to working
    grid.querySelectorAll('.ceo-agent-card').forEach(card => {
        const output = card.querySelector('.ceo-agent-output');
        _ceoBadge(card, 'working', 'working');
        output.classList.add('active');
        output.textContent = 'Processing directive...';
    });
    _ceoRouteCount += _ceoAgents ? _ceoAgents.length : 5;
    _ceoUpdateStats();

    try {
        const resp = await fetch('/api/ceo/broadcast', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task }),
        });
        const data = await resp.json();

        if (data.results) {
            data.results.forEach(result => {
                const card = grid.querySelector(`.ceo-agent-card[data-agent-id="${result.agent_id}"]`);
                if (!card) return;
                const output = card.querySelector('.ceo-agent-output');
                _ceoReadCount++;

                if (result.error) {
                    _ceoBadge(card, 'error', 'error');
                    output.textContent = `Error: ${result.error}`;
                } else {
                    _ceoBadge(card, 'ready', 'complete');
                    output.textContent = result.response || 'No response';
                }
            });
            _ceoUpdateStats();
        }
    } catch (e) {
        grid.querySelectorAll('.ceo-agent-card').forEach(card => {
            const output = card.querySelector('.ceo-agent-output');
            _ceoBadge(card, 'error', 'error');
            output.textContent = `Network error: ${e.message}`;
        });
    }

    // Reset master
    if (masterStatus) { masterStatus.className = 'ceo-master-status ready'; masterStatus.innerHTML = '<span class="ceo-dot"></span> ONLINE'; }
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
    // Init todo dock badge
    _updateTodoDock();
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
            refreshWeather().catch(e => console.warn('refreshWeather error:', e)),
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
        await _batch([refreshWeather, refreshCICD, refreshClaudeUsage, refreshAgents, refreshDeadlines]);

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
            + '6) Weather today. '
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
            // Show panel only if user is not already looking at analysis data.
            // SSE notifications must never silently destroy an active panel.
            if (data.panel && typeof voice !== 'undefined' && voice._renderAnalysisPanel) {
                const wingL = document.getElementById('analysis-wing-left');
                const panelActive = wingL && wingL.classList.contains('active');
                if (!panelActive) {
                    voice._renderAnalysisPanel(data.panel);
                }
            }
            // Speak the message if requested — but never talk over an active conversation
            if (data.speak && data.message && typeof voice !== 'undefined') {
                const busy = voice._processingQuery || voice.speaking || voice._chatMode;
                if (!busy) {
                    voice._speak(data.message);
                } else {
                    console.log('[SSE] Skipped speech (busy):', data.message.slice(0, 60));
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
