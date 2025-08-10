document.addEventListener('DOMContentLoaded', () => {
    if (window.Chart && window.ChartZoom) {
        Chart.register(window.ChartZoom);
    }
    let equityChart;

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

    async function loadSampleEquityChart() {
        const canvas = document.getElementById('equityChart');
        const resetBtn = document.getElementById('resetZoom');
        if (!canvas) return;
        try {
            const res = await fetch('/api/sample-equity-history');
            if (!res.ok) throw new Error('Failed to load equity history');
            const data = await res.json();
            if (!Array.isArray(data) || data.length === 0) {
                const msg = document.createElement('p');
                msg.textContent = 'No data available';
                canvas.replaceWith(msg);
                if (resetBtn) resetBtn.remove();
                return;
            }
            const points = data.map(d => ({ x: d.date, y: parseFloat(d.equity) }));
            if (equityChart) equityChart.destroy();
            equityChart = new Chart(canvas, {
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
                            const p = equityChart.data.datasets[0].data[elements[0].index];
                            console.log({ date: p.x, equity: p.y });
                        }
                    },
                    scales: {
                        x: {
                            type: 'time',
                            time: { parser: 'yyyy-MM-dd', tooltipFormat: 'PP' },
                            ticks: { color: '#000' },
                            grid: { color: '#e0e0e0' }
                        },
                        y: {
                            ticks: { color: '#000', callback: v => `$${v}` },
                            grid: { color: '#e0e0e0' }
                        }
                    }
                }
            });
            if (resetBtn) resetBtn.onclick = () => equityChart.resetZoom();
        } catch (err) {
            console.error(err);
            const el = document.getElementById('errorMessage');
            if (el) {
                el.textContent = 'Failed to load equity chart';
                el.classList.remove('visually-hidden');
            }
            const msg = document.createElement('p');
            msg.textContent = 'No data available';
            canvas.replaceWith(msg);
            if (resetBtn) resetBtn.remove();
        }
    }

    loadSamplePortfolio();
    loadSampleEquityChart();

});
