document.addEventListener('DOMContentLoaded', () => {
    async function loadSampleTradeLog() {
        try {
            const res = await fetch('/api/sample-trade-log');
            if (!res.ok) throw new Error('Failed to load sample trade log');
            const data = await res.json();
            const tbody = document.getElementById('tradeLogTableBody');
            tbody.innerHTML = '';
            data.trades.forEach(t => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${t.Date}</td>
                    <td>${t.Ticker}</td>
                    <td>${t['Shares Bought']}</td>
                    <td>${t['Buy Price']}</td>
                    <td>${t['Cost Basis']}</td>
                    <td>${t['PnL']}</td>
                    <td>${t.Reason}</td>
                    <td>${t['Shares Sold']}</td>
                    <td>${t['Sell Price']}</td>`;
                tbody.appendChild(tr);
            });
        } catch (err) {
            console.error(err);
            const el = document.getElementById('errorMessage');
            if (el) {
                el.textContent = 'Failed to load sample trade log';
                el.classList.remove('visually-hidden');
            }
        }
    }

    loadSampleTradeLog();
});

