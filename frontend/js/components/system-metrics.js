export class SystemMetrics {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
    }

    update(metrics) {
        if (!this.container || !metrics) return;

        // Render if empty
        if (!this.container.querySelector('.metric-item')) {
            this.renderStructure();
        }

        this.updateBar('cpu', metrics.cpu_percent);
        this.updateBar('ram', metrics.memory_percent);
        this.updateBar('disk', metrics.disk_percent);
    }

    renderStructure() {
        this.container.innerHTML = `
            <div class="metric-item">
                <div class="metric-label">
                    <span>CPU Load</span>
                    <span id="metric-val-cpu">0%</span>
                </div>
                <div class="metric-bar-bg">
                    <div class="metric-bar-fill" id="metric-bar-cpu"></div>
                </div>
            </div>
            <div class="metric-item">
                <div class="metric-label">
                    <span>Memory Usage</span>
                    <span id="metric-val-ram">0%</span>
                </div>
                <div class="metric-bar-bg">
                    <div class="metric-bar-fill" id="metric-bar-ram"></div>
                </div>
            </div>
            <div class="metric-item">
                <div class="metric-label">
                    <span>Disk Space</span>
                    <span id="metric-val-disk">0%</span>
                </div>
                <div class="metric-bar-bg">
                    <div class="metric-bar-fill" id="metric-bar-disk"></div>
                </div>
            </div>
        `;
    }

    updateBar(type, value) {
        const bar = document.getElementById(`metric-bar-${type}`);
        const valText = document.getElementById(`metric-val-${type}`);

        if (bar && valText) {
            bar.style.width = `${value}%`;
            valText.textContent = `${value.toFixed(1)}%`;

            // Color coding
            bar.className = 'metric-bar-fill'; // Reset
            if (value > 90) bar.classList.add('danger');
            else if (value > 70) bar.classList.add('warning');
        }
    }
}
