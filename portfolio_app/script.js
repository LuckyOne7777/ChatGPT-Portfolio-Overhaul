// Render portfolio information for the logged-in user.

document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('token');

    if (!token) {
        window.location.href = '/login';
        return;
    }

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

    init();

    async function init() {
        await checkStartingCash();
        await loadPortfolio();
        loadTradeLog();
        loadEquityChart();
    }

    async function checkStartingCash() {
        try {
            const res = await fetch('/api/needs-cash', {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to check starting cash');
            const data = await res.json();
            if (data.needs_cash) {
                let amount;
                do {
                    const input = prompt('Enter starting cash (0 - 10,000):');
                    if (input === null) return; // user cancelled
                    const trimmed = input.trim();
                    if (/^\d+(\.\d+)?$/.test(trimmed)) {
                        amount = Number(trimmed);
                    } else {
                        amount = NaN;
                    }
                } while (!Number.isFinite(amount) || amount < 0 || amount > 10000);

                const setRes = await fetch('/api/set-cash', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${token}`
                    },
                    body: JSON.stringify({ cash: amount })
                });
                if (!setRes.ok) throw new Error('Failed to set starting cash');
            }
        } catch (err) {
            showError('Failed to check starting cash', err);
        }
    }

    async function loadPortfolio() {
        try {
            const res = await fetch('/api/portfolio', {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to load portfolio');
            const data = await res.json();
            const tbody = document.getElementById('portfolioTableBody');
            tbody.innerHTML = '';
            data.positions.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${p.Ticker}</td>
                    <td>${p.Shares}</td>
                    <td>$${p.Cost_Basis}</td>
                    <td>$${p.Current_Price}</td>
                    <td>${p.PnL}</td>
                    <td>$${p.Stop_Loss}</td>`;
                tbody.appendChild(tr);
            });
            if (data.total_equity) {
                document.getElementById('totalEquity').textContent = `$${data.total_equity}`;
                if (data.starting_capital) {
                    const total = parseFloat(String(data.total_equity).replace(/,/g, ''));
                    const start = parseFloat(String(data.starting_capital).replace(/,/g, ''));
                    if (!isNaN(total) && !isNaN(start) && start !== 0) {
                        const change = ((total - start) / start) * 100;
                        document.getElementById('equityChange').textContent = `(${change.toFixed(2)}%)`;
                    } else {
                        document.getElementById('equityChange').textContent = '';
                    }
                }
            }
            if (data.cash) {
                document.getElementById('cashBalance').textContent = `$${data.cash}`;
            }
            if (data.deployed_capital) {
                document.getElementById('deployedCapital').textContent = `$${data.deployed_capital}`;
            }
            return data.positions.length > 0;
        } catch (err) {
            showError('Failed to load portfolio', err);
            return false;
        }
    }

    async function loadTradeLog() {
        try {
            const res = await fetch('/api/trade-log', {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to load trade log');
            const data = await res.json();
            const tbody = document.getElementById('tradeLogBody');
            tbody.innerHTML = '';
            let wins = 0;
            let sells = 0;
            data.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${item.Date}</td>
                    <td>${item.Ticker}</td>
                    <td>${item.Action}</td>
                    <td>$${item.Price}</td>
                    <td>${item.Quantity}</td>
                    <td>${item.Reason}</td>`;
                tbody.appendChild(tr);
                if (item.Action === 'Sell') {
                    sells++;
                    if (parseFloat(item.PnL) > 0) wins++;
                }
            });
            document.getElementById('numTrades').textContent = data.length;
            document.getElementById('winRate').textContent = sells ? `${Math.round((wins / sells) * 100)}%` : '0%';
            return data.length > 0;
        } catch (err) {
            showError('Failed to load trade log', err);
            return false;
        }
    }

    async function loadEquityChart() {
        const chart = document.getElementById('equityChart');
        if (!chart) return;
        try {
            const res = await fetch('/api/equity-chart.png', {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to load equity chart');
            const blob = await res.blob();
            chart.src = URL.createObjectURL(blob);
        } catch (err) {
            showError('Failed to load equity chart', err);
        }
    }

    const tradeForm = document.getElementById('tradeForm');
    if (tradeForm) {
        tradeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const tradeErrorEl = document.getElementById('tradeErrorMessage');
            if (tradeErrorEl) tradeErrorEl.classList.add('visually-hidden');
            const payload = {
                ticker: document.getElementById('trade-ticker').value.trim().toUpperCase(),
                action: document.getElementById('trade-action').value,
                price: parseFloat(document.getElementById('trade-price').value),
                shares: parseFloat(document.getElementById('trade-shares').value),
                reason: document.getElementById('trade-reason').value.trim(),
            };
            const stopLossInput = document.getElementById('trade-stop-loss').value.trim();
            if (stopLossInput) {
                payload.stop_loss = stopLossInput;
            }
            try {
                const res = await fetch('/api/trade', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify(payload),
                });
                if (!res.ok) {
                    let msg = 'Trade failed';
                    try {
                        const errData = await res.json();
                        if (errData && errData.message) {
                            msg = errData.message;
                        }
                    } catch (_) {
                        try {
                            msg = await res.text();
                        } catch (_) {
                            /* ignore */
                        }
                    }
                    showError(msg, undefined, 'tradeErrorMessage');
                    return;
                }
                tradeForm.reset();
                await loadPortfolio();
                await loadTradeLog();
                await loadEquityChart();
            } catch (err) {
                showError('Trade failed', err, 'tradeErrorMessage');
            }
        });
    }

    const processBtn = document.getElementById('processPortfolioBtn');
    if (processBtn) {
        processBtn.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/process-portfolio', {
                    method: 'POST',
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!res.ok) throw new Error('Failed to process portfolio');
                alert('Portfolio processed successfully');
                await loadPortfolio();
                await loadEquityChart();
            } catch (err) {
                showError('Failed to process portfolio', err);
            }
        });
    }
});
