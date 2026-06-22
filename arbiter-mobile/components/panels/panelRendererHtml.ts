// HTML payload for the PanelWebView fallback renderer. Inlined as a
// template literal so the bundle works without metro asset config.
//
// Wire-protocol (host -> webview): {type: 'panel', payload: Panel}
// Wire-protocol (webview -> host): {type: 'ready'|'height'|'error', payload: any}
//
// The renderer mirrors enough of the desktop _renderAnalysisPanel to
// cover chart/table/heatmap/quadrant/calendar_heatmap/comparison_matrix
// sections that the native panel components don't yet support.

/* eslint-disable @typescript-eslint/no-unused-vars */

export const PANEL_RENDERER_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no" />
  <title>Arbiter panel</title>
  <style>
    :root {
      --bg: #080f1e;
      --panel-bg: rgba(6,12,28,0.94);
      --border: rgba(0,240,255,0.16);
      --divider: rgba(32,244,255,0.12);
      --cyan: #20f4ff;
      --cyan-soft: #80dfff;
      --text-bright: #e8f4ff;
      --text-dim: #9fc4dc;
      --text-muted: #5a7a8a;
      --green: #00ff88;
      --red: #ff5454;
      --amber: #ffb454;
    }
    html, body { margin: 0; padding: 0; background: transparent; color: var(--text-bright);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
      -webkit-text-size-adjust: 100%; overflow: hidden; }
    body { padding: 8px 0; }
    .section { padding: 4px 0; }
    .chart-wrap { width: 100%; min-height: 200px; max-height: 280px; }
    canvas { display: block; max-width: 100%; }
    .heading { color: var(--cyan); font-size: 11px; letter-spacing: 1.1px;
      text-transform: uppercase; font-family: ui-monospace, Menlo, monospace; margin-bottom: 6px; }
    .summary { color: var(--text-bright); font-size: 14px; line-height: 1.45; }
    .matrix { width: 100%; border-collapse: collapse; font-family: ui-monospace, Menlo, monospace;
      font-size: 12px; color: var(--text-bright); }
    .matrix th, .matrix td { border-bottom: 1px solid var(--divider); padding: 6px 8px; text-align: left; }
    .matrix th { color: var(--cyan); text-transform: uppercase; letter-spacing: 1px; font-size: 11px; }
    .json-fallback { font-family: ui-monospace, Menlo, monospace; font-size: 11px;
      color: var(--text-dim); white-space: pre-wrap; word-break: break-word; }
    .empty { color: var(--text-muted); font-size: 12px; font-style: italic; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <script>
    (function () {
      const ROOT = document.getElementById('root');
      const CHARTS = [];
      function post(name, payload) {
        const msg = JSON.stringify({ type: name, payload: payload == null ? null : payload });
        if (window.ReactNativeWebView && window.ReactNativeWebView.postMessage) {
          window.ReactNativeWebView.postMessage(msg);
        }
      }
      function destroyCharts() {
        while (CHARTS.length) { try { CHARTS.pop().destroy(); } catch (e) {} }
      }
      function el(tag, cls, text) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
      }
      function reportHeight() {
        const h = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
        post('height', { height: h });
      }
      function renderHeading(parent, text) { if (text) parent.appendChild(el('div','heading',String(text))); }
      function renderSummary(parent, text) { if (text) parent.appendChild(el('div','summary',String(text))); }
      function renderChart(parent, spec) {
        if (!spec || !window.Chart) return;
        const wrap = el('div','chart-wrap');
        const canvas = document.createElement('canvas');
        wrap.appendChild(canvas); parent.appendChild(wrap);
        const labels = Array.isArray(spec.labels) ? spec.labels : [];
        const palette = ['#20f4ff','#00ff88','#ffb454','#ff66a8','#80dfff'];
        const datasets = Array.isArray(spec.datasets) ? spec.datasets.map(function(d,i){
          const color = d.color || palette[i % palette.length];
          return Object.assign({ borderColor: color, backgroundColor: color + '33',
            borderWidth: 1.5, tension: 0.25, pointRadius: 2 }, d);
        }) : [];
        try {
          const chart = new Chart(canvas, {
            type: (spec.type === 'hbar') ? 'bar' : (spec.type || 'line'),
            data: { labels: labels, datasets: datasets },
            options: { responsive: true, maintainAspectRatio: false, animation: false,
              plugins: { legend: { labels: { color: '#bfe6ff' } } },
              indexAxis: spec.type === 'hbar' ? 'y' : 'x',
              scales: { x: { ticks: { color: '#9fc4dc' }, grid: { color: 'rgba(32,244,255,0.08)' } },
                        y: { ticks: { color: '#9fc4dc' }, grid: { color: 'rgba(32,244,255,0.08)' } } } },
          });
          CHARTS.push(chart);
        } catch (e) { parent.appendChild(el('div','json-fallback','chart render failed: ' + e.message)); }
      }
      function renderMatrix(parent, table, caption) {
        if (!table || !Array.isArray(table.columns) || !Array.isArray(table.rows)) return;
        renderHeading(parent, caption);
        const tbl = el('table','matrix');
        const thead = el('thead'); const trh = el('tr');
        table.columns.forEach(function(c){ trh.appendChild(el('th',null,String(c))); });
        thead.appendChild(trh); tbl.appendChild(thead);
        const tbody = el('tbody');
        table.rows.slice(0,50).forEach(function(row){
          const tr = el('tr');
          (Array.isArray(row) ? row : []).forEach(function(cell){
            tr.appendChild(el('td',null,cell == null ? '' : String(cell)));
          });
          tbody.appendChild(tr);
        });
        tbl.appendChild(tbody); parent.appendChild(tbl);
      }
      function renderUnsupported(parent, label, data) {
        const sect = el('div','section'); renderHeading(sect, label);
        sect.appendChild(el('pre','json-fallback', JSON.stringify(data, null, 2)));
        parent.appendChild(sect);
      }
      function renderSection(parent, section) {
        const wrap = el('div','section');
        renderHeading(wrap, section.title);
        if (section.chart) renderChart(wrap, section.chart);
        if (section.table) renderMatrix(wrap, section.table, section.table.title);
        if (section.heatmap) renderUnsupported(wrap, 'Heatmap', section.heatmap);
        if (section.comparison_matrix) renderUnsupported(wrap, 'Comparison matrix', section.comparison_matrix);
        if (section.quadrant) renderUnsupported(wrap, 'Quadrant', section.quadrant);
        if (section.calendar_heatmap) renderUnsupported(wrap, 'Calendar heatmap', section.calendar_heatmap);
        if (section.image_url) {
          const img = document.createElement('img');
          img.src = String(section.image_url); img.style.maxWidth = '100%';
          img.onload = reportHeight; wrap.appendChild(img);
        }
        if (section.summary) renderSummary(wrap, section.summary);
        parent.appendChild(wrap);
      }
      function render(panel) {
        destroyCharts(); ROOT.innerHTML = '';
        if (!panel || typeof panel !== 'object') { ROOT.appendChild(el('div','empty','no panel data')); return; }
        const sections = Array.isArray(panel.sections) ? panel.sections : [panel];
        sections.forEach(function(s){ renderSection(ROOT, s); });
        if (!ROOT.children.length) ROOT.appendChild(el('div','empty','empty panel'));
        setTimeout(reportHeight, 60); setTimeout(reportHeight, 240);
      }
      function handle(evt) {
        try { const msg = typeof evt.data === 'string' ? JSON.parse(evt.data) : evt.data;
          if (msg && msg.type === 'panel') render(msg.payload);
        } catch (e) { post('error', { message: e.message }); }
      }
      window.addEventListener('message', handle);
      document.addEventListener('message', handle);
      post('ready', null);
    })();
  </script>
</body>
</html>`;
