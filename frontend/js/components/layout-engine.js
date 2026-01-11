/**
 * Layout Engine
 * =============
 * Manages the customizable dashboard grid.
 * Handles:
 * - LocalStorage persistence of widget positions
 * - "Edit Mode" toggling
 * - Drag & Drop logic (Gridstack-lite approach)
 */

export class LayoutEngine {
    constructor(gridId = 'dashboard-grid') {
        this.grid = document.getElementById(gridId);
        this.isEditMode = false;
        this.widgets = [];
        this.STORAGE_KEY = 'phantom_layout_v1';

        // Bind methods
        this.toggleEditMode = this.toggleEditMode.bind(this);
        this.saveLayout = this.saveLayout.bind(this);
        this.resetLayout = this.resetLayout.bind(this);

        this.init();
    }

    init() {
        if (!this.grid) return;

        // Load saved layout or default
        this.loadLayout();

        // Setup Drag & Drop Listeners (Delegate to grid)
        this.setupDragDrop();
    }

    /**
     * Load layout from storage or discover DOM widgets
     */
    loadLayout() {
        const saved = localStorage.getItem(this.STORAGE_KEY);
        if (saved) {
            try {
                const config = JSON.parse(saved);
                this.applyLayout(config);
            } catch (e) {
                console.error('Failed to load layout:', e);
                this.discoverWidgets();
            }
        } else {
            this.discoverWidgets();
        }
    }

    /**
     * Scan DOM for .dashboard-widget elements
     */
    discoverWidgets() {
        this.widgets = Array.from(this.grid.querySelectorAll('.dashboard-widget'));
    }

    /**
     * Apply saved layout positions
     * Simple Order-based approach for now (Flex/Grid Order)
     */
    applyLayout(config) {
        if (!config.order || !Array.isArray(config.order)) return;

        config.order.forEach(id => {
            const widget = document.getElementById(id);
            if (widget && this.grid) {
                this.grid.appendChild(widget); // Re-append to change order
            }
        });

        this.discoverWidgets();
    }

    /**
     * Save current DOM order to storage
     */
    saveLayout() {
        this.discoverWidgets();
        const order = this.widgets.map(w => w.id).filter(id => id);

        const config = {
            version: '1.0',
            order: order
        };

        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(config));

        // Visual feedback
        if (window.tradingOS?.toast) {
            window.tradingOS.toast.show('Layout Saved', 'success');
        }
    }

    /**
     * Reset to factory default
     */
    resetLayout() {
        localStorage.removeItem(this.STORAGE_KEY);
        window.location.reload();
    }

    /**
     * Toggle Edit Mode visuals
     */
    toggleEditMode() {
        this.isEditMode = !this.isEditMode;

        if (this.isEditMode) {
            document.body.classList.add('layout-edit-mode');
            this.grid.classList.add('grid-editing');
        } else {
            document.body.classList.remove('layout-edit-mode');
            this.grid.classList.remove('grid-editing');
            this.saveLayout(); // Auto-save on exit
        }
    }

    /**
     * Setup HTML5 Drag & Drop
     */
    setupDragDrop() {
        let draggedItem = null;

        this.grid.addEventListener('dragstart', (e) => {
            if (!this.isEditMode) {
                e.preventDefault();
                return;
            }

            // Only allow dragging via header/handle if desired, 
            // but for now allow whole widget if in edit mode
            const widget = e.target.closest('.dashboard-widget');
            if (!widget) return;

            draggedItem = widget;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', widget.id);
            widget.classList.add('dragging');
        });

        this.grid.addEventListener('dragend', (e) => {
            if (draggedItem) {
                draggedItem.classList.remove('dragging');
                draggedItem = null;
            }
            // Save on drop? Or wait for Edit Mode exit?
            // Let's save continuously for better UX
            this.saveLayout();
        });

        this.grid.addEventListener('dragover', (e) => {
            if (!this.isEditMode || !draggedItem) return;
            e.preventDefault(); // Allow drop
            e.dataTransfer.dropEffect = 'move';

            const targetWidget = e.target.closest('.dashboard-widget');
            if (targetWidget && targetWidget !== draggedItem) {
                // Calculate position to determine if insert before or after
                const rect = targetWidget.getBoundingClientRect();
                const next = (e.clientY - rect.top) / (rect.bottom - rect.top) > 0.5;

                if (next) {
                    this.grid.insertBefore(draggedItem, targetWidget.nextSibling);
                } else {
                    this.grid.insertBefore(draggedItem, targetWidget);
                }
            }
        });
    }
}
