/**
 * Modular Router
 * ==============
 * Manages the "Hub-and-Spoke" navigation.
 * Handles deep linking and page transitions.
 */
export class Router {
    constructor(rootId) {
        this.rootId = rootId;
        this.routes = new Map();
        this.currentPage = null;

        // Bind navigation
        window.addEventListener('hashchange', () => this._handleHashChange());
        window.addEventListener('load', () => this._handleHashChange());
    }

    /**
     * Register a route
     * @param {string} path - e.g., '/dashboard'
     * @param {BasePage} pageInstance - Instance of a page class
     */
    register(path, pageInstance) {
        this.routes.set(path, pageInstance);
    }

    navigate(path) {
        window.location.hash = path;
    }

    async _handleHashChange() {
        let hash = window.location.hash.slice(1) || '/dashboard'; // Default to dashboard

        // Handle Params (simple implementation)
        // e.g. /engine/arb -> match /engine/arb
        // For now, exact match. Future: Regex.

        const page = this.routes.get(hash);

        if (!page) {
            console.warn(`[Router] No route for ${hash}`);
            if (hash !== '/dashboard') this.navigate('/dashboard');
            return;
        }

        if (this.currentPage === page) return;

        // 1. Unmount current
        if (this.currentPage) {
            await this.currentPage.unmount();
        }

        // 2. Mount new
        this.currentPage = page;
        const container = document.getElementById(this.rootId);
        if (container) {
            await page.mount(container);

            // Highlight Sidebar
            this._updateSidebar(hash);
        }
    }

    _updateSidebar(hash) {
        document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
        // logic to find nav item with data-link corresponding to hash
        const activeLink = document.querySelector(`.nav-item[data-link="${hash}"]`);
        if (activeLink) activeLink.classList.add('active');
    }
}
