document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('equityChart');
    const ctx = canvas ? canvas.getContext('2d') : null;

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

    function showGraphMessage(message) {
        const el = document.getElementById('graphMessage');
        if (el) {
            el.textContent = message;
            el.classList.remove('visually-hidden');
        }
    }

    function hideGraphMessage() {
        const el = document.getElementById('graphMessage');
        if (el) {
            el.classList.add('visually-hidden');
        }
    }

    async function loadSampleEquityHistory() {
        try {
            const res = await fetch('/api/sample-equity-history');
            if (!res.ok) throw new Error('Failed to load sample equity history');
            const data = await res.json();
            const values = data
                .map(d => parseFloat(d['Total Equity']))
                .filter(v => !isNaN(v));
            if (values.length < 2) {
                showGraphMessage('Not enough data for graph');
                return;
            }
            hideGraphMessage();
            drawChart(values);
        } catch (err) {
            console.error(err);
            showGraphMessage('Failed to load equity history');
        }
    }

    function drawChart(values) {
        if (!ctx) return;
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

    loadSamplePortfolio();
    if (canvas && ctx) {
        loadSampleEquityHistory();
    } else {
        showGraphMessage('Not enough data for graph');
    }
});
