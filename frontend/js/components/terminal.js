/**
 * Terminal Log Component
 * ======================
 * Manages the terminal log display and formatting.
 */

export class Terminal {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.maxLogs = options.maxLogs || 50;
        this.logs = [];
    }

    /**
     * Add a log entry
     */
    addLog(source, level, message, timestamp = null) {
        if (!this.container) return;

        const time = timestamp
            ? new Date(timestamp * 1000).toLocaleTimeString()
            : new Date().toLocaleTimeString();

        const levelColors = {
            'INFO': 'var(--text-primary)',
            'SUCCESS': 'var(--neon-green)',
            'WARNING': 'var(--neon-gold)',
            'ERROR': 'var(--neon-red)',
            'DEBUG': 'var(--text-dim)'
        };

        const color = levelColors[level] || 'var(--text-primary)';

        const entry = document.createElement('div');
        entry.className = 'log-entry';
        entry.innerHTML = `
            <span style="color: var(--text-dim)">[${time}]</span>
            <span style="color: var(--neon-blue)">[${source}]</span>
            <span style="color: ${color}">${this.escapeHtml(message)}</span>
        `;

        this.container.appendChild(entry);
        this.logs.push(entry);

        // Trim old logs
        while (this.logs.length > this.maxLogs) {
            const old = this.logs.shift();
            old.remove();
        }

        // Auto-scroll to bottom
        this.container.scrollTop = this.container.scrollHeight;
    }

    /**
     * Clear all logs
     */
    clear() {
        if (this.container) {
            this.container.innerHTML = '';
            this.logs = [];
        }
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

export default Terminal;
