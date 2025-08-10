// script.js — Render portfolio info for the logged-in user with robust errors.

document.addEventListener('DOMContentLoaded', () => {
  const token = localStorage.getItem('token');
  let startingCapital = null;
  if (window.Chart && window.Chart.register && window.ChartZoom) {
    Chart.register(window.ChartZoom);
  }
  let equityChartInstance = null;

  // ----- UI helpers ----------------------------------------------------------
  function showError(message, err, elementId = 'errorMessage') {
    if (err) console.error(err);
    const el = document.getElementById(elementId);
    if (el) {
      el.textContent = message;
      el.classList.remove('visually-hidden');
    } else {
      alert(message);
    }
  }

  function hideError(elementId = 'errorMessage') {
    const el = document.getElementById(elementId);
    if (el) el.classList.add('visually-hidden');
  }

  function showStatus(message, elementId = 'processMessage') {
    const el = document.getElementById(elementId);
    if (el) {
      el.textContent = message;
      el.classList.remove('visually-hidden');
    } else {
      alert(message);
    }
  }

  function requireAuthOrRedirect() {
    if (!token) {
      window.location.href = '/login';
      return false;
    }
    return true;
  }

  // ----- Network helpers -----------------------------------------------------
  async function getErrorMessage(res, fallback, { expectContentType } = {}) {
    if (!res || typeof res.ok !== 'boolean') return fallback;

    const ct = res.headers.get('content-type') || '';

    // If we expected a specific content type (e.g., image/png) but got something else
    if (expectContentType && res.ok && !ct.includes(expectContentType)) {
      return `Unexpected response type. Expected ${expectContentType}, got ${ct || 'none'} (status ${res.status}).`;
    }

    // Try to extract a server-provided message
    let serverMsg = '';
    try {
      const data = await res.clone().json();
      if (data && data.message) serverMsg = data.message;
    } catch {
      try {
        const text = await res.clone().text();
        if (text) serverMsg = text.slice(0, 300);
      } catch { /* ignore */ }
    }

    const base = serverMsg || fallback;

    // Map common HTTP statuses to friendly messages
    switch (res.status) {
      case 400: return `${base} — Your request was invalid (400). Check inputs.`;
      case 401: return `${base || 'Session expired'} — Please sign in again (401).`;
      case 403: return `${base || 'Not allowed'} — You don’t have access (403).`;
      case 404: return `${base || 'Not found'} — Endpoint or resource missing (404).`;
      case 415: return `${base || 'Unsupported media type'} (415).`;
      case 429: return `${base || 'Too many requests'} — Slow down (429).`;
      case 500: return `${base || 'Server error'} — Check server logs (500).`;
      case 502:
      case 503:
      case 504: return `${base || 'Server unavailable'} — Try again shortly (${res.status}).`;
      default:  return `${base} (status ${res.status})`;
    }
  }

  async function ensureOk(res, fallback, opts) {
    if (res.ok) return;
    const msg = await getErrorMessage(res, fallback, opts);
    if (res.status === 401) {
      // Token likely expired — clear and redirect
      localStorage.removeItem('token');
      showError('Your session expired. Please sign in again.', null);
      setTimeout(() => (window.location.href = '/login'), 800);
    }
    throw new Error(msg);
  }

  // JSON fetch wrapper with Authorization header and timeout
  async function fetchJson(
    url,
    { method = 'GET', body, expect = 'application/json', timeoutMs = 15000 } = {}
  ) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(url, {
        method,
        headers: {
          ...(body ? { 'Content-Type': 'application/json' } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
      await ensureOk(res, `Request failed for ${url}`, { expectContentType: expect });
      return await res.json();
    } catch (err) {
      if (err.name === 'AbortError') {
        throw new Error(`Request timed out for ${url}`);
      }
      // Reframe generic network errors with likely causes
      const msg = String(err.message || err);
      if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) {
        throw new Error('Could not reach the server. If your backend is running, check CORS/HTTPS settings and the route.');
      }
      throw err;
    } finally {
      clearTimeout(t);
    }
  }

  // ----- App init ------------------------------------------------------------
  if (!requireAuthOrRedirect()) return;

  init().catch(err => {
    showError(err.message || 'Initialization failed', err);
  });

  async function init() {
    await checkStartingCash();
    await loadPortfolio();
    loadTradeLog();      // don’t await to parallelize
    loadEquityChart();   // don’t await to parallelize
    wireEvents();
  }

  // ----- Features ------------------------------------------------------------
  async function checkStartingCash() {
    try {
      const data = await fetchJson('/api/needs-cash', { method: 'GET' });
      if (data.needs_cash) {
        let amount;
        do {
          const input = prompt('Enter starting cash (0 - 10,000):');
          if (input === null) return; // user cancelled
          const trimmed = input.trim();
          amount = /^\d+(\.\d+)?$/.test(trimmed) ? Number(trimmed) : NaN;
        } while (!Number.isFinite(amount) || amount < 0 || amount > 10000);

        await fetchJson('/api/set-cash', {
          method: 'POST',
          body: { cash: amount },
        });
      }
    } catch (err) {
      showError(err.message || 'Failed to check starting cash', err);
    }
  }

  async function loadPortfolio() {
    try {
      hideError();
      const data = await fetchJson('/api/portfolio', { method: 'GET' });

      // Table
      const tbody = document.getElementById('portfolioTableBody');
      if (tbody) {
        tbody.innerHTML = '';
        (data.positions || []).forEach(p => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${p.ticker ?? ''}</td>
            <td>${p.shares ?? ''}</td>
            <td>$${p.buy_price?.toFixed ? p.buy_price.toFixed(2) : p.buy_price ?? ''}</td>
            <td>-</td>
            <td>-</td>
            <td>-</td>`;
          tbody.appendChild(tr);
        });
      }

      startingCapital = parseFloat(String(data.starting_capital ?? '').replace(/,/g, ''));

      if (data.cash != null) {
        const el = document.getElementById('cashBalance');
        if (el) el.textContent = `$${data.cash}`;
      }

      if (data.deployed_capital != null) {
        const el = document.getElementById('deployedCapital');
        if (el) el.textContent = `$${data.deployed_capital}`;
      }

      if (data.total_equity != null) {
        const totalEl = document.getElementById('totalEquity');
        if (totalEl) totalEl.textContent = `$${data.total_equity}`;

        const eqChangeEl = document.getElementById('equityChange');
        if (eqChangeEl && Number.isFinite(startingCapital) && startingCapital !== 0) {
          const total = parseFloat(String(data.total_equity ?? '').replace(/,/g, ''));
          if (Number.isFinite(total)) {
            const change = ((total - startingCapital) / startingCapital) * 100;
            eqChangeEl.textContent = `(${change.toFixed(2)}%)`;
          }
        }
      }

      return (data.positions || []).length > 0;
    } catch (err) {
      showError(err.message || 'Failed to load portfolio', err);
      return false;
    }
  }

  function renderProcessedPortfolio(data) {
    const positions = data.positions || [];
    const tbody = document.getElementById('portfolioTableBody');
    if (tbody) {
      tbody.innerHTML = '';
      positions.forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${p.ticker ?? ''}</td>
          <td>${p.shares ?? ''}</td>
          <td>$${Number(p.buy_price ?? 0).toFixed(2)}</td>
          <td>$${Number(p.current_price ?? 0).toFixed(2)}</td>
          <td>$${Number(p.position_value ?? 0).toFixed(2)}</td>
          <td>$${Number(p.pnl ?? 0).toFixed(2)}</td>`;
        tbody.appendChild(tr);
      });
    }

    const totals = data.totals || {};
    const cash = Number(totals.cash ?? 0);
    const posVal = Number(totals.total_positions_value ?? 0);
    const pnl = Number(totals.total_pnl ?? 0);
    const totalEq = Number(totals.total_equity ?? 0);

    const cashEl = document.getElementById('totalsCash');
    if (cashEl) cashEl.textContent = `$${cash.toFixed(2)}`;
    const posValEl = document.getElementById('totalsPositionsValue');
    if (posValEl) posValEl.textContent = `$${posVal.toFixed(2)}`;
    const pnlEl = document.getElementById('totalsPnl');
    if (pnlEl) pnlEl.textContent = `$${pnl.toFixed(2)}`;
    const totalEqEl = document.getElementById('totalsTotalEquity');
    if (totalEqEl) totalEqEl.textContent = `$${totalEq.toFixed(2)}`;

    const totalTop = document.getElementById('totalEquity');
    if (totalTop) totalTop.textContent = `$${totalEq.toFixed(2)}`;
    const cashTop = document.getElementById('cashBalance');
    if (cashTop) cashTop.textContent = `$${cash.toFixed(2)}`;
    const depTop = document.getElementById('deployedCapital');
    if (depTop) depTop.textContent = `$${posVal.toFixed(2)}`;

    const eqChangeEl = document.getElementById('equityChange');
    if (eqChangeEl && Number.isFinite(startingCapital) && startingCapital !== 0) {
      const change = ((totalEq - startingCapital) / startingCapital) * 100;
      eqChangeEl.textContent = `(${change.toFixed(2)}%)`;
    }

    const caption = document.getElementById('asOfCaption');
    if (caption) caption.textContent = `As of ${data.as_of_date_et}${data.forced ? ' (forced)' : ''}`;
  }

  async function loadTradeLog() {
    try {
      hideError();
      const data = await fetchJson('/api/trade-log', { method: 'GET' });
      const trades = data.trades || [];

      const tbody = document.getElementById('tradeLogBody');
      if (tbody) {
        tbody.innerHTML = '';
        trades.forEach(item => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${item.date ?? ''}</td>
            <td>${item.ticker ?? ''}</td>
            <td>${item.side ?? ''}</td>
            <td>$${item.price ?? ''}</td>
            <td>${item.shares ?? ''}</td>
            <td>${item.reason ?? ''}</td>`;
          tbody.appendChild(tr);
        });

        const nEl = document.getElementById('numTrades');
        if (nEl) nEl.textContent = trades.length;

        const wrEl = document.getElementById('winRate');
        if (wrEl) wrEl.textContent = '0%';
      }

      return trades.length > 0;
    } catch (err) {
      showError(err.message || 'Failed to load trade log', err);
      return false;
    }
  }

  async function loadEquityChart() {
    const canvas = document.getElementById('equityChart');
    const msgEl = document.getElementById('noDataMessage');
    const resetBtn = document.getElementById('resetZoomBtn');
    if (!canvas) return;

    try {
      const raw = await fetchJson('/api/portfolio-history', { method: 'GET', timeoutMs: 30000 });

      const points = (Array.isArray(raw) ? raw : [])
        .map(d => {
          const x = new Date(d.date + 'T00:00:00');
          const y = Number(d.equity);
          return { x, y };
        })
        .filter(p => Number.isFinite(p.y) && !Number.isNaN(p.x.getTime()))
        .sort((a, b) => a.x - b.x);

      console.log('equity points', points.length, points.at?.(0), points.at?.(-1));
      if (!points.length) {
        canvas.classList.add('visually-hidden');
        if (resetBtn) resetBtn.classList.add('visually-hidden');
        if (msgEl) { msgEl.textContent = 'No data available'; msgEl.classList.remove('visually-hidden'); }
        if (equityChartInstance) { equityChartInstance.destroy(); equityChartInstance = null; }
        console.log('equity raw payload', raw);
        return;
      }

      if (msgEl) msgEl.classList.add('visually-hidden');
      canvas.classList.remove('visually-hidden');
      if (resetBtn) resetBtn.classList.remove('visually-hidden');

      if (equityChartInstance) {
        equityChartInstance.data.datasets[0].data = points;
        equityChartInstance.update('none');
        return;
      }

      equityChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
          datasets: [{
            data: points,
            borderColor: '#1f77b4',
            backgroundColor: '#1f77b4',
            pointRadius: 3,
            pointHoverRadius: 4,
            fill: false,
            tension: 0
          }]
        },
        options: {
          parsing: false,
          responsive: true,
          maintainAspectRatio: true,
          interaction: { mode: 'nearest', intersect: false },
          scales: {
            x: {
              type: 'time',
              time: { tooltipFormat: 'MMM d, yyyy' },
              grid: { color: '#e0e0e0' },
              ticks: { color: '#000' }
            },
            y: {
              grid: { color: '#e0e0e0' },
              ticks: { color: '#000' },
              title: { display: true, text: 'Equity ($)', color: '#000' }
            }
          },
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: ctx => `$${ctx.parsed.y.toFixed(2)}` } },
            zoom: {
              zoom: { wheel: { enabled: true, modifierKey: 'alt' }, mode: 'x' },
              pan: { enabled: true, modifierKey: 'shift', mode: 'x' }
            }
          }
        }
      });

      if (resetBtn) resetBtn.onclick = () => equityChartInstance.resetZoom();

    } catch (err) {
      if (equityChartInstance) { equityChartInstance.destroy(); equityChartInstance = null; }
      canvas.classList.add('visually-hidden');
      if (resetBtn) resetBtn.classList.add('visually-hidden');
      if (msgEl) { msgEl.textContent = 'No data available'; msgEl.classList.remove('visually-hidden'); }
      console.error('Failed to load equity chart', err);
    }
  }

  // ----- Events --------------------------------------------------------------
  function wireEvents() {
    const tradeForm = document.getElementById('tradeForm');
    if (tradeForm) {
      tradeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const tradeErrorEl = document.getElementById('tradeErrorMessage');
        if (tradeErrorEl) tradeErrorEl.classList.add('visually-hidden');

        const ticker = document.getElementById('trade-ticker')?.value?.trim().toUpperCase();
        const action = document.getElementById('trade-action')?.value;
        const price = parseFloat(document.getElementById('trade-price')?.value);
        const shares = parseFloat(document.getElementById('trade-shares')?.value);
        const reason = document.getElementById('trade-reason')?.value?.trim();
        const stopLossInput = (document.getElementById('trade-stop-loss')?.value || '').trim();

        // Basic client-side validation
        if (!ticker || !action || !Number.isFinite(price) || price <= 0 || !Number.isFinite(shares) || shares <= 0) {
          showError('Please provide a valid ticker, action, price (>0), and shares (>0).', undefined, 'tradeErrorMessage');
          return;
        }

        const payload = { ticker, action, price, shares, reason };

        // Stop loss validation
        if (stopLossInput) {
          let valid = false;
          if (stopLossInput.endsWith('%')) {
            const val = parseFloat(stopLossInput.slice(0, -1));
            if (Number.isFinite(val) && val >= 0) valid = true;
          } else {
            const val = parseFloat(stopLossInput);
            if (Number.isFinite(val) && val >= 0) {
              if (val >= price && action === 'buy') {
                showError('Stop loss must be below the buy price.', undefined, 'tradeErrorMessage');
                return;
              }
              valid = true;
            }
          }
          if (!valid) {
            showError('Invalid stop loss value.', undefined, 'tradeErrorMessage');
            return;
          }
          payload.stop_loss = stopLossInput;
        }

        try {
          await fetchJson('/api/trade', {
            method: 'POST',
            body: payload,
          });
          tradeForm.reset();
          await loadPortfolio();
          await loadTradeLog();
          await loadEquityChart();
        } catch (err) {
          showError(err.message || 'Trade failed', err, 'tradeErrorMessage');
        }
      });
    }

    const processBtn = document.getElementById('processPortfolioBtn');
    const forceBtn = document.getElementById('forceProcessPortfolioBtn');
    if (processBtn && forceBtn) {
      const handle = async (force = false) => {
        const buttons = [processBtn, forceBtn];
        buttons.forEach(b => b.disabled = true);
        hideError('processMessage');
        try {
          const body = force ? { force: true } : undefined;
          const data = await fetchJson('/api/process-portfolio', { method: 'POST', body });
          renderProcessedPortfolio(data);
          showStatus(data.message || 'Portfolio processed successfully', 'processMessage');
          await loadEquityChart();
        } catch (err) {
          showStatus(err.message || 'Failed to process portfolio', 'processMessage');
        } finally {
          buttons.forEach(b => b.disabled = false);
        }
      };

      processBtn.addEventListener('click', () => handle(false));
      forceBtn.addEventListener('click', () => handle(true));
    }
  }
});