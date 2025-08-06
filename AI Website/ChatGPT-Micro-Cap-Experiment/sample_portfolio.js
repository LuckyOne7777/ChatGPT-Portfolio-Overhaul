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
});
