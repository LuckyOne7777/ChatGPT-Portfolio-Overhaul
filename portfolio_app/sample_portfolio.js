document.addEventListener('DOMContentLoaded', () => {
    async function loadSamplePortfolio() {
        try {
            const res = await fetch('/api/sample-portfolio');
            if (!res.ok) throw new Error('Failed to load sample portfolio');
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
                    <td>${p.PnL}</td>`;
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
        } catch (err) {
            console.error(err);
            const el = document.getElementById('errorMessage');
            if (el) {
                el.textContent = 'Failed to load sample portfolio';
                el.classList.remove('visually-hidden');
            }
        }
    }

    loadSamplePortfolio();

    const token = localStorage.getItem('token');
    const processBtn = document.getElementById('processPortfolioBtn');
    if (processBtn) {
        processBtn.addEventListener('click', async () => {
            if (!token) {
                alert('Please log in to process the portfolio');
                return;
            }
            try {
                const res = await fetch('/api/process-portfolio', {
                    method: 'POST',
                    headers: { Authorization: `Bearer ${token}` }
                });
                if (!res.ok) throw new Error('Failed to process portfolio');
                alert('Portfolio processed successfully');
                await loadSamplePortfolio();
            } catch (err) {
                console.error(err);
                alert('Failed to process portfolio');
            }
        });
    }
});
