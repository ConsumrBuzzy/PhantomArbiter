/**
 * API Health Component
 * ====================
 * Displays a grid of API status cards in the Config view.
 */
export class APIHealth {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.apis = [];

        // Render initial loading state
        this.render();
    }

    /**
     * Update with new API health data
     */
    update(healthData) {
        if (!Array.isArray(healthData)) return;
        this.apis = healthData;
        this.render();
    }

    /**
     * Get status icon and color
     */
    getStatusInfo(status) {
        switch (status) {
            case 'ok':
                return { icon: '✓', color: 'var(--neon-green)', label: 'OK' };
            case 'slow':
                return { icon: '⚠', color: 'var(--neon-yellow, #FFD700)', label: 'SLOW' };
            case 'error':
                return { icon: '✗', color: 'var(--neon-red)', label: 'ERROR' };
            case 'unconfigured':
                return { icon: '○', color: 'var(--text-dim)', label: 'N/A' };
            default:
                return { icon: '?', color: 'var(--text-dim)', label: 'UNKNOWN' };
        }
    }

    render() {
        if (!this.container) return;

        if (this.apis.length === 0) {
            this.container.innerHTML = `
                <div class="api-health-loading">
                    <span>Checking APIs...</span>
                </div>
            `;
            return;
        }

        const cards = this.apis.map(api => {
            const { icon, color, label } = this.getStatusInfo(api.status);
            const latency = api.latency_ms > 0 ? `${api.latency_ms.toFixed(0)}ms` : '--';

            return `
                <div class="api-health-card" title="${api.message || ''}">
                    <div class="api-name">${api.name}</div>
                    <div class="api-status" style="color: ${color};">
                        <span class="status-icon">${icon}</span>
                        <span class="status-label">${label}</span>
                    </div>
                    <div class="api-latency">${latency}</div>
                </div>
            `;
        }).join('');

        this.container.innerHTML = `
            <div class="api-health-grid">
                ${cards}
            </div>
            <div class="api-health-legend">
                <span><span style="color: var(--neon-green);">✓</span> OK</span>
                <span><span style="color: var(--neon-yellow, #FFD700);">⚠</span> Slow</span>
                <span><span style="color: var(--neon-red);">✗</span> Error</span>
                <span><span style="color: var(--text-dim);">○</span> Not Configured</span>
            </div>
        `;
    }
}

export default APIHealth;
