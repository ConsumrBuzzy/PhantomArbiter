/**
 * Toast Notification Component
 * ============================
 * Glassmorphism notifications for system feedback.
 * Used for Safety Gate rejections, engine responses, etc.
 */

export class Toast {
    constructor() {
        this.container = this.createContainer();
        this.queue = [];
        this.isShowing = false;
    }

    createContainer() {
        const existing = document.getElementById('toast-container');
        if (existing) return existing;

        const container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
        return container;
    }

    /**
     * Show a toast notification
     * @param {string} message - The message to display
     * @param {'info'|'success'|'warning'|'error'} severity - Toast severity level
     * @param {number} duration - Auto-dismiss duration in ms (default 4000)
     */
    show(message, severity = 'info', duration = 4000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${severity}`;

        const icon = this.getIcon(severity);
        toast.innerHTML = `
            <span class="toast-icon">${icon}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close">✕</button>
        `;

        // Close button handler
        toast.querySelector('.toast-close').addEventListener('click', () => {
            this.dismiss(toast);
        });

        this.container.appendChild(toast);

        // Trigger entrance animation
        requestAnimationFrame(() => {
            toast.classList.add('toast-visible');
        });

        // Auto-dismiss
        if (duration > 0) {
            setTimeout(() => this.dismiss(toast), duration);
        }
    }

    dismiss(toast) {
        toast.classList.remove('toast-visible');
        toast.classList.add('toast-exit');

        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300); // Match CSS transition duration
    }

    getIcon(severity) {
        const icons = {
            'info': 'ℹ️',
            'success': '✅',
            'warning': '⚠️',
            'error': '🚫'
        };
        return icons[severity] || icons.info;
    }
}

export default Toast;
