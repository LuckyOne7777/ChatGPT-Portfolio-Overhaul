// Simple portfolio vs benchmark chart using Canvas API
// Generates dummy data and allows timeframe toggling.

document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('portfolioChart');
    const ctx = canvas.getContext('2d');
    const buttons = document.querySelectorAll('.timeframe-buttons button');

    // Generate dummy data for different ranges
    const data = {
        '1W': generateData(7),
        '1M': generateData(30),
        'Max': generateData(100)
    };

    // Produce simple random walk data for demonstration purposes
    function generateData(points) {
        const portfolio = [];
        const benchmark = [];
        let p = 100;
        let b = 100;
        for (let i = 0; i < points; i++) {
            p += Math.random() * 4 - 2; // simulate changes
            b += Math.random() * 3 - 1.5;
            portfolio.push(p);
            benchmark.push(b);
        }
        return { portfolio, benchmark };
    }

    // Draw line chart for selected timeframe
    function drawChart(range) {
        const { portfolio, benchmark } = data[range];
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const maxVal = Math.max(...portfolio, ...benchmark);
        const minVal = Math.min(...portfolio, ...benchmark);
        const xScale = canvas.width / (portfolio.length - 1);
        const yScale = canvas.height / (maxVal - minVal);

        // Draw portfolio line
        ctx.beginPath();
        ctx.strokeStyle = '#007bff';
        ctx.lineWidth = 2;
        portfolio.forEach((val, i) => {
            const x = i * xScale;
            const y = canvas.height - (val - minVal) * yScale;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // Draw benchmark line
        ctx.beginPath();
        ctx.strokeStyle = '#ff5733';
        benchmark.forEach((val, i) => {
            const x = i * xScale;
            const y = canvas.height - (val - minVal) * yScale;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
    }

    // Initial chart
    drawChart('Max');

    // Update chart on timeframe selection
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            drawChart(btn.dataset.range);
        });
    });

    loadPortfolio();
    loadTradeLog();

    async function loadPortfolio() {
        try {
            const res = await fetch('/api/portfolio');
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
        } catch (err) {
            console.error(err);
        }
    }

    async function loadTradeLog() {
        try {
            const res = await fetch('/api/trade-log');
            if (!res.ok) throw new Error('Failed to load trade log');
            const data = await res.json();
            const tbody = document.getElementById('tradeLogBody');
            tbody.innerHTML = '';
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
            });
            document.getElementById('numTrades').textContent = data.length;
        } catch (err) {
            console.error(err);
        }
    }
});
