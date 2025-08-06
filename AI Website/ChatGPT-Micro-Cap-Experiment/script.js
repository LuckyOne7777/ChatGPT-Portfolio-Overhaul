// Render portfolio information for the logged-in user.

document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('portfolioChart');
    const ctx = canvas.getContext('2d');
    const token = localStorage.getItem('token');

    init();

    async function init() {
        let hasPositions = await loadPortfolio();
        if (!hasPositions) {
            await checkStartingCash();
            await loadPortfolio();
        }
        loadEquityHistory();
        loadTradeLog();
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
                    amount = prompt('Enter starting cash (max 100000):');
                    if (amount === null) return; // user cancelled
                    amount = parseFloat(amount);
                } while (isNaN(amount) || amount < 0 || amount > 100000);

                await fetch('/api/set-cash', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${token}`
                    },
                    body: JSON.stringify({ cash: amount })
                });
            }
        } catch (err) {
            console.error(err);
        }
    }

    async function loadEquityHistory() {
        try {
            const res = await fetch('/api/equity-history', {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to load equity history');
            const data = await res.json();
            drawChart(data.map(d => parseFloat(d['Total Equity'])));
        } catch (err) {
            console.error(err);
        }
    }

    function drawChart(values) {
        if (values.length === 0) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const maxVal = Math.max(...values);
        const minVal = Math.min(...values);
        const xScale = canvas.width / (values.length - 1);
        const yScale = canvas.height / (maxVal - minVal || 1);

        ctx.beginPath();
        ctx.strokeStyle = '#007bff';
        ctx.lineWidth = 2;
        values.forEach((val, i) => {
            const x = i * xScale;
            const y = canvas.height - (val - minVal) * yScale;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
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
            }
            return data.positions.length > 0;
        } catch (err) {
            console.error(err);
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
            console.error(err);
            return false;
        }
    }
});
