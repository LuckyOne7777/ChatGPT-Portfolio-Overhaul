// script.js — Render portfolio info for the logged-in user with robust errors.

document.addEventListener('DOMContentLoaded', () => {
  const token = localStorage.getItem('token');
  if (window.Chart && window.ChartZoom) {
    Chart.register(window.ChartZoom);
  }
  let equityChartInstance;

  function upsertChartPoint(dateStr, equity) {
    // dateStr is 'YYYY-MM-DD' in ET
    const y = Number(equity);
    if (!Number.isFinite(y)) return;

    // Ensure chart exists; if not, call loadEquityChart() and return early
    if (!equityChartInstance) { loadEquityChart(); return; }

    const data = equityChartInstance.data.datasets[0].data || [];

    // Find existing point for that calendar day and replace it
    const idx = data.findIndex(p =>
      typeof p.x === 'string' ? p.x === dateStr : new Date(p.x).toISOString().slice(0,10) === dateStr
    );

    if (idx !== -1) {
      data[idx] = { x: dateStr, y };
    } else {
      data.push({ x: dateStr, y });
    }

    // Keep points sorted by date
    data.sort((a, b) => new Date(a.x) - new Date(b.x));

    equityChartInstance.data.datasets[0].data = data;
    equityChartInstance.update('none');
  }

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
  async function fetchJson(url, { method = 'GET', body, expect = 'application/json', timeoutMs = 15000 } = {}) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs); // configurable timeout
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
            <td>${p.Ticker ?? ''}</td>
            <td>${p.Shares ?? ''}</td>
            <td>$${p.Cost_Basis ?? ''}</td>
            <td>$${p.Current_Price ?? ''}</td>
            <td>${p.PnL ?? ''}</td>
            <td>$${p.Stop_Loss ?? ''}</td>`;
          tbody.appendChild(tr);
        });
      }

      // Totals
      if (data.total_equity != null) {
        const totalEl = document.getElementById('totalEquity');
        if (totalEl) totalEl.textContent = `$${data.total_equity}`;

        // Percent change based on starting capital
        const start = parseFloat(String(data.starting_capital ?? '').replace(/,/g, ''));
        const total = parseFloat(String(data.total_equity ?? '').replace(/,/g, ''));
        const eqChangeEl = document.getElementById('equityChange');
        if (eqChangeEl) {
          if (Number.isFinite(start) && start !== 0 && Number.isFinite(total)) {
            const change = ((total - start) / start) * 100;
            eqChangeEl.textContent = `(${change.toFixed(2)}%)`;
          } else {
            eqChangeEl.textContent = '';
          }
        }
      }

      if (data.cash != null) {
        const el = document.getElementById('cashBalance');
        if (el) el.textContent = `$${data.cash}`;
      }

      if (data.deployed_capital != null) {
        const el = document.getElementById('deployedCapital');
        if (el) el.textContent = `$${data.deployed_capital}`;
      }

      return (data.positions || []).length > 0;
    } catch (err) {
      showError(err.message || 'Failed to load portfolio', err);
      return false;
    }
  }

  async function loadTradeLog() {
    try {
      hideError();
      const data = await fetchJson('/api/trade-log', { method: 'GET' });

      const tbody = document.getElementById('tradeLogBody');
      if (tbody) {
        tbody.innerHTML = '';
        let wins = 0;
        let sells = 0;

        (data || []).forEach(item => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${item.Date ?? ''}</td>
            <td>${item.Ticker ?? ''}</td>
            <td>${item.Action ?? ''}</td>
            <td>$${item.Price ?? ''}</td>
            <td>${item.Quantity ?? ''}</td>
            <td>${item.Reason ?? ''}</td>`;
          tbody.appendChild(tr);

          if (item.Action === 'Sell') {
            sells++;
            const pnl = parseFloat(item.PnL);
            if (Number.isFinite(pnl) && pnl > 0) wins++;
          }
        });

        const nEl = document.getElementById('numTrades');
        if (nEl) nEl.textContent = (data || []).length;

        const wrEl = document.getElementById('winRate');
        if (wrEl) wrEl.textContent = sells ? `${Math.round((wins / sells) * 100)}%` : '0%';
      }

      return (data || []).length > 0;
    } catch (err) {
      showError(err.message || 'Failed to load trade log', err);
      return false;
    }
  }

  async function loadEquityChart() {
    const canvas = document.getElementById('equityChart');
    const resetBtn = document.getElementById('resetZoom');
    if (!canvas) return;

    try {
      hideError();
      const raw = await fetchJson('/api/portfolio-history');

      const byDay = new Map(); // key: day string, value: equity number (last wins)
      for (const d of Array.isArray(raw) ? raw : []) {
        const day = typeof d.date === 'string' ? d.date.slice(0,10) : '';
        const val = Number(d.equity);
        if (day && Number.isFinite(val)) byDay.set(day, val);
      }
      const points = Array.from(byDay.entries())
        .map(([day, eq]) => ({ x: day, y: eq }))
        .sort((a, b) => new Date(a.x) - new Date(b.x));

      if (points.length === 0) {
        const msgEl = document.createElement('p');
        msgEl.textContent = 'No data available';
        canvas.replaceWith(msgEl);
        if (resetBtn) resetBtn.remove();
        return;
      }

      if (equityChartInstance) equityChartInstance.destroy();

      equityChartInstance = new Chart(canvas, {
        type: 'line',
        data: {
          datasets: [{
            label: 'Equity',
            data: points,
            borderColor: '#1f77b4',
            backgroundColor: '#1f77b4',
            pointRadius: 3,
            pointHoverRadius: 5,
            pointBackgroundColor: '#1f77b4',
            pointHoverBackgroundColor: '#1f77b4',
            fill: false,
            tension: 0,
          }]
        },
        options: {
          responsive: true,
          interaction: { mode: 'nearest', intersect: true },
          plugins: {
            tooltip: {
              callbacks: {
                label: ctx => `$${ctx.parsed.y.toFixed(2)}`
              }
            },
            zoom: {
              zoom: {
                wheel: { enabled: true, modifierKey: 'alt' },
                mode: 'x'
              },
              pan: {
                enabled: true,
                modifierKey: 'shift',
                mode: 'x'
              }
            }
          },
          onClick: (evt, elements) => {
            if (elements.length > 0) {
              const p = equityChartInstance.data.datasets[0].data[elements[0].index];
              console.log({ date: p.x, equity: p.y });
            }
          },
          scales: {
            x: {
              type: 'time',
              time: {
                parser: 'yyyy-MM-dd',
                unit: 'day',
                tooltipFormat: 'MMM d',
                displayFormats: { day: 'MMM d' }
              },
              ticks: { color: '#000' },
              grid: { color: '#e0e0e0' }
            },
            y: {
              ticks: {
                color: '#000',
                callback: v => `$${v}`
              },
              grid: { color: '#e0e0e0' }
            }
          }
        }
      });

      if (resetBtn) {
        resetBtn.onclick = () => equityChartInstance.resetZoom();
      }
    } catch (err) {
      showError(err.message || 'Failed to load equity history', err);
      const msgEl = document.createElement('p');
      msgEl.textContent = 'No data available';
      canvas.replaceWith(msgEl);
      if (resetBtn) resetBtn.remove();
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

    async function handleProcess() {
      try {
        const data = await fetchJson('/api/process-portfolio', { method: 'POST' });
        await loadPortfolio();
        if (data?.as_of_date_et && data?.totals?.total_equity != null) {
          upsertChartPoint(data.as_of_date_et, data.totals.total_equity);
        } else {
          await loadEquityChart();
        }
      } catch (err) {
        showError(err.message || 'Failed to process portfolio', err);
      }
    }

    const processBtn = document.getElementById('processPortfolioBtn');
    if (processBtn) {
      processBtn.addEventListener('click', handleProcess);
    }
  }
});
