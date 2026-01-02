export class StatsPanel {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.stats = {
            scan_rate: 0,
            total_scanned: 0,
            batch_size: 0,
            cycles_per_sec: 0,
            pod_status: 'Starting...'
        };
        this.init();
    }

    init() {
        this.container.innerHTML = `
            <div class="stats-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-family: monospace; color: #0f0; font-size: 12px; margin-top: 10px;">
                <div class="stat-item">SCAN RATE: <span id="stat-scan-rate">0</span>/s</div>
                <div class="stat-item">TOTAL SCANNED: <span id="stat-total-scanned">0</span></div>
                <div class="stat-item">BATCH SIZE: <span id="stat-batch-size">0</span></div>
                <div class="stat-item">CPS: <span id="stat-cps">0</span></div>
                <div class="stat-item" style="grid-column: span 2;">PODS: <span id="stat-pods">Starting...</span></div>
            </div>
        `;

        this.els = {
            scanRate: document.getElementById('stat-scan-rate'),
            totalScanned: document.getElementById('stat-total-scanned'),
            batchSize: document.getElementById('stat-batch-size'),
            cps: document.getElementById('stat-cps'),
            pods: document.getElementById('stat-pods')
        };
    }

    update(data) {
        this.stats = { ...this.stats, ...data };
        this.render();
    }

    render() {
        this.els.scanRate.textContent = this.stats.scan_rate.toFixed(1);
        this.els.totalScanned.textContent = this.stats.total_scanned;
        this.els.batchSize.textContent = this.stats.batch_size;
        this.els.cps.textContent = this.stats.cycles_per_sec.toFixed(2);
        this.els.pods.textContent = this.stats.pod_status;
    }
}
