# Arbiter Mobile — Delivery Plan

React Native / Expo adaptation of `arbiter-mission-control`, re-using only the
front-end orb, hands-on chat, and panel visualisations. The Python server
(`arbiter-mission-control/server.py`) is reused as-is, with minimal additions.

---

## 1. Scope

In-scope:
- Centre orb (idle / listening / thinking / speaking, audio-reactive) — visual only.
- Hands-on chat: text input, send, expandable/collapsible scrollable history.
- Result rendering: re-use the existing panel schema (`hero`, `stats`,
  `key_metrics`, `chart`, `table`, `status_grid`, `trend_indicators`, `gauges`,
  `funnel`, `insights`, `recommendations`, `pros_cons`, `swot`, `risk_matrix`,
  `timeline`, `summary`, `comparison_matrix`, `heatmap`, `quadrant`,
  `calendar_heatmap`, `image_url`, `candlestick`) laid out as a vertical scroll
  feed tuned for phone & tablet.
- Secure connection to the dev machine on LAN; iOS + Android via Expo.

Out of scope (web-only stays web):
- Wake word / clap detector, voice TTS/STT, camera vision, ComfyUI, dock bar,
  briefings, pipelines, settings UI, business switcher, dialogue-options
  sidebar, system charts (CPU/MEM), email widgets, dialogue overlays.

---

## 2. Target architecture

```
┌──────────── Expo app (iOS / Android) ─────────────┐
│  React Native + TypeScript + expo-router          │
│  ├─ <Orb/>          react-native-skia (canvas)    │
│  ├─ <ChatDrawer/>   react-native-reanimated       │
│  └─ <PanelFeed/>    FlashList of <PanelCard/>     │
│         └─ Native panels (victory-native/Skia)    │
│            + WebView fallback for complex panels  │
│  Auth: expo-secure-store (ARBITER_API_KEY)        │
│  Net : fetch w/ Bearer; AbortController; retry    │
└────────────────────┬──────────────────────────────┘
                     │ HTTPS (Tailscale Funnel) or
                     │ HTTPS (uvicorn self-signed)
                     ▼
        existing FastAPI server.py (unchanged endpoints)
        /api/jarvis/chat   /api/jarvis/vision   /api/auth/check
```

Two reuse strategies for visualisations — both will be used:
- **MVP (fast):** WebView host page loading a stripped-down
  `panel-renderer.html` (Chart.js + the existing `_renderAnalysisPanel` /
  `_renderReportPanel` code, extracted). One WebView per panel inside a native
  scroll list. Zero re-implementation.
- **Polish (incremental):** Replace the highest-traffic panel types with native
  equivalents (`hero`, `stats`, `key_metrics`, `status_grid`, `table`, `chart`)
  using `victory-native` for charts and plain RN for cards. Keeps native
  scrolling, accessibility, dark-mode, copy-paste.

---

## 3. Tech stack

| Concern         | Choice                                  | Why |
|-----------------|------------------------------------------|-----|
| Framework       | Expo SDK (managed)                       | OTA, EAS Build, one repo for iOS/Android |
| Language        | TypeScript                               | safety + future shared types |
| Navigation      | `expo-router`                            | file-based, push/modal works on tablet |
| Orb             | `@shopify/react-native-skia`             | canvas-equivalent, 60 fps; port `jarvis.js` `Orb` class line-for-line |
| Animations      | `react-native-reanimated` v3             | chat-drawer expand/collapse, orb state cross-fades |
| Lists           | `@shopify/flash-list`                    | smooth scrolling for long chat + many panels |
| Charts (native) | `victory-native` (Skia)                  | matches bar/line/area/donut/radar/scatter used in `_renderAnalysisPanel` |
| Charts (fallback) | `react-native-webview` + Chart.js      | reuses existing renderer verbatim |
| Markdown        | `react-native-markdown-display`          | `mdToHtml` in chat bubbles |
| Storage         | `expo-secure-store` (token), `AsyncStorage` (history) | Keychain/Keystore-backed for the API key |
| Networking      | `fetch` + `expo-network`                 | streaming-friendly later |
| Audio level (v1.1) | `expo-av`                             | drives orb amplitude when user holds-to-talk |

---

## 4. Secure connectivity to the laptop

Pick **one**; recommendation in bold.

| Option | Effort | Security | iOS ATS pass | Notes |
|---|---|---|---|---|
| **Tailscale + Funnel** | Low | Strong (WireGuard + TLS) | ✅ HTTPS | Mac runs `tailscale funnel 8000`, phone hits `https://laptop.tailXXXX.ts.net`. No ATS exception. Best fit. |
| Self-signed TLS on uvicorn + trusted root on device | Med | Strong | ✅ once cert installed | `mkcert` cert, install via MDM profile on iOS |
| Plain HTTP on LAN + ATS exception for one host | Low | Weak (LAN only) | ❌ unless exception | Emulator-only |
| Cloudflare Tunnel | Low | Strong | ✅ | Public DNS name; still gated by `ARBITER_API_KEY` |

App-layer auth stays as-is: every request sends
`Authorization: Bearer <ARBITER_API_KEY>`; key is entered once on first launch
and stored in `expo-secure-store`. `/api/auth/check` validates it at startup.

---

## 5. Repo layout

New sibling project (keeps Python server clean):

```
ai-tools/
├── arbiter-mission-control/        # unchanged
└── arbiter-mobile/                 # new
    ├── app/                        # expo-router screens
    │   ├── _layout.tsx
    │   ├── index.tsx               # Orb + chat overlay
    │   └── settings.tsx            # API key + host URL
    ├── components/
    │   ├── Orb/                    # ported from jarvis.js
    │   ├── ChatDrawer/
    │   ├── panels/                 # native panel components
    │   └── PanelWebView.tsx        # WebView fallback host
    ├── lib/
    │   ├── api.ts                  # fetch wrapper + auth
    │   ├── storage.ts              # SecureStore helpers
    │   └── types.ts                # Panel/Action/Followup schema
    ├── assets/panel-renderer/      # static HTML + extracted JS for WebView
    └── eas.json, app.json, package.json
```

`assets/panel-renderer/` is built by extracting `_renderAnalysisPanel` +
dependencies (`mdToHtml`, candlestick renderer, the Chart.js setup) into a
single self-contained HTML that accepts a panel JSON via `window.postMessage`.

---

## 6. Server-side changes (minimal)

Most of `server.py` is untouched. Required tweaks:

1. **CORS** — add the Expo dev origin only if we ever debug in web mode;
   native fetches don't need it.
2. **`/api/jarvis/chat`** — confirm response shape
   `{ raw|reply, spokenText, panel?, actions?, followups? }` is stable; add an
   explicit `client: "mobile"` request field so the LLM can be told to skip TTS
   markers / desktop-automation actions the phone can't run.
3. **Reject mobile-incompatible actions** server-side (e.g. `desktop_*`) when
   `client=mobile`, to keep mobile responses clean.
4. *Optional*: gzip middleware for large panels.
5. *Optional*: SSE `/api/jarvis/chat/stream` for token streaming (v1.1).

No DB changes. No new auth. No new Python dependencies.


---

## 7. Milestones & deliverables

Each milestone ends in something runnable on a real device.

### M0 — Project bootstrap (0.5 day)
- `npx create-expo-app arbiter-mobile -t expo-template-blank-typescript`
- Add Skia, Reanimated, FlashList, SecureStore, WebView, victory-native,
  markdown-display.
- EAS init; create dev build profile (Skia/WebView need a dev client; Expo Go
  is too limited).
- Settings screen: host URL + API key + `/api/auth/check` round-trip.

**Exit:** app installs on iPhone via EAS dev build; auth check returns ✅.

### M1 — Orb port (1–2 days)
- Translate the `Orb` class from `jarvis.js` to a Skia component:
  - particle nebula, orbital ring, compass ticks, state colours
  - `setState('idle' | 'listening' | 'thinking' | 'speaking')`
  - `setAudioLevel(0..1)` hook (driven later by mic; static for now)
- Verify 60 fps on iPhone 12 / mid-range Android.

**Exit:** orb cycles through all 4 states via debug buttons.

### M2 — Hands-on chat (1–2 days)
- `<ChatDrawer/>` Reanimated panel:
  - collapsed: input bar pinned above keyboard
  - expanded: full-height history scroll with smooth drag handle
  - swipe-down / tap-outside to collapse
- Persist last N exchanges to AsyncStorage (mirror the web 20-message cap).
- Send → `POST /api/jarvis/chat` with `{message, history, client:"mobile"}`.
- Render assistant markdown + system messages.
- Orb state syncs (`thinking` while in-flight, `idle` on reply).

**Exit:** can hold a conversation against the laptop; history scrolls and
hides nicely.

### M3 — Panel feed (WebView fast path) (1 day)
- `<PanelFeed/>` is a FlashList below the chat history (or in a tabbed second
  screen on phone, side-by-side on tablet).
- For every assistant reply with `d.panel`, push a `<PanelWebView panel={…}/>`
  card.
- Each WebView loads the bundled `panel-renderer.html` and `postMessage`s the
  panel JSON.
- Auto-size height via `postMessage` back from the page; native scrolling owns
  the outer list.

**Exit:** every web visualisation appears, correctly, in a phone-suitable
vertical feed.

### M4 — Native panel set (2–3 days)
Re-implement the most-used panel types natively, falling back to WebView for
the rest:
- `hero`, `stats`, `key_metrics`, `status_grid`, `summary`, `insights`,
  `recommendations`, `table` → plain RN
- `chart` (bar / hbar / line / area / doughnut / pie / radar) →
  `victory-native`
- Keep WebView for `candlestick`, `heatmap`, `calendar_heatmap`, `quadrant`,
  `comparison_matrix` until/if needed.

**Exit:** common queries render natively with no WebView flicker.

### M5 — Tablet layout (0.5 day)
- Two-pane on `min-width: 768`: orb + chat left, panel feed right.
- Phone stays single-pane with bottom-sheet chat.

**Exit:** iPad / large Android renders proper split layout.

### M6 — Secure transport + release builds (1 day)
- Document and script the chosen connectivity path (recommendation: Tailscale
  Funnel) in `arbiter-mobile/README.md`.
- EAS internal-distribution build for iOS (ad-hoc) and Android APK.
- Smoke test against laptop from 4G/5G with Tailscale on.

**Exit:** signed dev builds on personal devices, hitting the laptop securely.

### M7 (optional, v1.1) — Streaming + voice
- SSE token streaming with `EventSource` polyfill.
- Hold-to-talk: `expo-av` recording → existing voice flow (or local STT) → orb
  amplitude drives Skia.
- Push notifications via Expo for completed long-running pipelines.

---

## 8. Total estimate

~6–9 working days for M0–M6 (single developer). M7 is a separate beat.

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Skia orb port underperforms vs canvas | Profile early in M1; reduce particle count on lower-tier devices; drop ring blur first |
| WebView height jitter for panels | Use `ResizeObserver` in the renderer page → `postMessage` height → setState on RN side; cap min-height |
| iOS ATS blocking dev HTTP | Use Tailscale Funnel (HTTPS) from day one — avoid plaintext exceptions |
| API key leakage | Store only in `expo-secure-store`; never in AsyncStorage; never log; mask in settings UI |
| Panel schema drift | Lock a `types.ts` mirror of the panel JSON; CI check that compares against a JSON sample exported from `server.py` |
| Desktop-only actions reaching the phone (e.g. `desktop_*`) | Server gate behind `client=="mobile"`; client also ignores unknown action types silently |

---

## 10. Decisions needed before M0

1. **Connectivity**: Tailscale Funnel (recommended) vs self-signed TLS vs
   Cloudflare Tunnel?
2. **Panel strategy**: ship MVP as 100% WebView (fastest), or skip M3 and go
   native-first (longer, nicer)?
3. **Voice on mobile**: defer to M7 (recommended) or in scope for v1?
4. **Repo**: keep `arbiter-mobile/` as a sibling folder in this same git repo,
   or stand up a new repo?
