/**
 * WebSocket Connection Manager
 * ============================
 * Handles WebSocket connection lifecycle, reconnection, and message routing.
 */

export class WebSocketManager {
    constructor(options = {}) {
        this.ws = null;
        this.port = options.port || 8765;
        this.reconnectDelay = options.reconnectDelay || 3000;
        this.maxReconnectDelay = options.maxReconnectDelay || 30000;
        this.currentDelay = this.reconnectDelay;

        // Callbacks
        this.onConnect = options.onConnect || (() => { });
        this.onDisconnect = options.onDisconnect || (() => { });
        this.onMessage = options.onMessage || (() => { });
        this.onError = options.onError || (() => { });

        // State
        this.isConnected = false;
        this.reconnecting = false;
    }

    /**
     * Connect to WebSocket server
     */
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname || 'localhost';
        const url = `${protocol}//${host}:${this.port}`;

        try {
            this.ws = new WebSocket(url);
            this.bindEvents();
        } catch (err) {
            this.onError(err);
            this.scheduleReconnect();
        }

        return url;
    }

    /**
     * Bind WebSocket events
     */
    bindEvents() {
        this.ws.onopen = () => {
            this.isConnected = true;
            this.reconnecting = false;
            this.currentDelay = this.reconnectDelay;
            this.onConnect();
        };

        this.ws.onmessage = (event) => {
            try {
                const packet = JSON.parse(event.data);
                this.onMessage(packet);
            } catch (e) {
                console.error("[WS] Parse error:", e);
            }
        };

        this.ws.onclose = () => {
            this.isConnected = false;
            this.onDisconnect();
            this.scheduleReconnect();
        };

        this.ws.onerror = (err) => {
            this.onError(err);
        };
    }

    /**
     * Schedule reconnection with exponential backoff
     */
    scheduleReconnect() {
        if (this.reconnecting) return;

        this.reconnecting = true;
        setTimeout(() => {
            this.reconnecting = false;
            this.connect();
        }, this.currentDelay);

        // Exponential backoff
        this.currentDelay = Math.min(this.currentDelay * 1.5, this.maxReconnectDelay);
    }

    /**
     * Send command to backend
     */
    send(action, payload = {}) {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ action, ...payload }));
            return true;
        }
        return false;
    }

    /**
     * Disconnect
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

export default WebSocketManager;
