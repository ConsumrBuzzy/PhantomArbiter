export class ScanTable {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.opportunities = [];
        this.init();
    }

    init() {
        this.container.innerHTML = `
            <div class="scan-table-container" style="margin-top: 20px; background: rgba(0, 20, 0, 0.7); border: 1px solid #0f0; padding: 10px; backdrop-filter: blur(5px);">
                <div style="font-weight: bold; border-bottom: 1px solid #0f0; margin-bottom: 5px; font-size: 12px; color: #0f0;">ACTIVE OPPORTUNITIES</div>
                <table style="width: 100%; border-collapse: collapse; color: #0f0; font-size: 11px; font-family: monospace;">
                    <thead>
                        <tr style="border-bottom: 1px solid #040; text-align: left;">
                            <th style="padding: 4px;">TOKEN</th>
                            <th style="padding: 4px;">ROUTE</th>
                            <th style="padding: 4px;">SPREAD</th>
                        </tr>
                    </thead>
                    <tbody id="scan-table-body">
                    </tbody>
                </table>
            </div>
        `;
        this.tbody = document.getElementById('scan-table-body');
    }

    update(opportunities) {
        // Expected format: [{token, route, profit_pct, ...}]
        this.opportunities = opportunities || [];
        this.render();
    }

    render() {
        this.tbody.innerHTML = this.opportunities.map(opp => `
            <tr style="border-bottom: 1px solid #020;">
                <td style="padding: 4px;">${opp.token}</td>
                <td style="padding: 4px; color: #aaa;">${opp.route}</td>
                <td style="padding: 4px; color: ${opp.profit_pct > 0.02 ? '#0f0' : '#ff0'};">${(opp.profit_pct * 100).toFixed(2)}%</td>
            </tr>
        `).join('');
    }
}
