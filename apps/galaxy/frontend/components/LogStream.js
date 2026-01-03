export class LogStream {
    constructor(containerId, maxLogs = 50) {
        this.container = document.getElementById(containerId);
        this.maxLogs = maxLogs;
        this.logs = [];
        this.init();
    }

    init() {
        this.container.style.marginTop = '20px';
        this.container.style.fontSize = '12px';
        this.container.style.color = '#aaa';
        this.container.style.maxHeight = '200px';
        this.container.style.overflowY = 'auto'; // Re-enable scroll if needed
        this.container.style.overflowX = 'hidden';
        this.container.style.fontFamily = 'monospace';
    }

    add(level, message, timestamp) {
        const timeStr = timestamp ? new Date(timestamp * 1000).toLocaleTimeString() : new Date().toLocaleTimeString();
        const logEntry = { level, message, timeStr };
        this.logs.unshift(logEntry);

        if (this.logs.length > this.maxLogs) {
            this.logs.pop();
        }

        this.render();
    }

    render() {
        this.container.innerHTML = this.logs.map(log => {
            const color = this.getLevelColor(log.level);
            return `<div class="log-entry" style="margin-bottom: 2px;">
                <span style="color: #666;">[${log.timeStr}]</span> 
                <span style="color: ${color}; font-weight: bold;">[${log.level}]</span> 
                ${log.message}
            </div>`;
        }).join('');
    }

    getLevelColor(level) {
        switch (level) {
            case 'SUCCESS': return '#0f0';
            case 'WARNING': return '#ff0';
            case 'ERROR': return '#f00';
            case 'CRITICAL': return '#f0f';
            default: return '#0ff';
        }
    }
}
