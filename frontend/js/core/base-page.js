/**
 * Base Page Component
 * ===================
 * Abstract class for all "Spoke" and "Hub" pages.
 * Enforces strict lifecycle management to ensure performance.
 */
export class BasePage {
    constructor(id) {
        this.id = id;
        this.container = null;
        this.isActive = false;
    }

    /**
     * Called when the page enters the viewport.
     * @param {HTMLElement} container - The DOM element to render into
     */
    async mount(container) {
        this.container = container;
        this.isActive = true;
        console.log(`[Router] Mounting ${this.id}...`);

        // 1. Render HTML
        const html = await this.render();
        this.container.innerHTML = html;

        // 2. Attach Event Listeners & Initialize Components
        await this.init();
    }

    /**
     * Called when the user navigates away.
     * CRITICAL: Must clean up all intervals, sockets, and listeners here.
     */
    async unmount() {
        console.log(`[Router] Unmounting ${this.id}...`);
        this.isActive = false;
        this.container.innerHTML = ''; // Clear DOM
        this.destroy(); // Subclass cleanup
    }

    /**
     * @returns {string} HTML string for the page
     */
    async render() {
        return `<h1>${this.id}</h1>`;
    }

    /**
     * Initialize logic (Charts, Sockets)
     */
    async init() {
        // Override me
    }

    /**
     * Cleanup logic (ClearInterval, RemoveEventListener)
     */
    async destroy() {
        // Override me
    }
}
