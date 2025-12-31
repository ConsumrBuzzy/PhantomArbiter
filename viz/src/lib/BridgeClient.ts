import type { GraphPayload, GraphSnapshot, GraphDiff } from "./types";

export type OnPayloadCallback = (payload: GraphPayload) => void;

export class BridgeClient {
    private url: string;
    private socket: WebSocket | null = null;
    private onPayload: OnPayloadCallback;
    private reconnectTimeout: number = 2000;
    private isClosing: boolean = false;

    constructor(url: string, onPayload: OnPayloadCallback) {
        this.url = url;
        this.onPayload = onPayload;
    }

    connect() {
        console.log(`🔌 Connecting to Visual Bridge: ${this.url}`);
        this.socket = new WebSocket(this.url);

        this.socket.onopen = () => {
            console.log("✅ Bridge Connected");
            this.reconnectTimeout = 2000; // Reset backoff
        };

        this.socket.onmessage = (event) => {
            try {
                const payload: GraphPayload = JSON.parse(event.data);
                this.onPayload(payload);
            } catch (e) {
                console.error("❌ Failed to parse bridge payload:", e);
            }
        };

        this.socket.onclose = () => {
            if (!this.isClosing) {
                console.warn(`⚠️ Bridge Disconnected. Retrying in ${this.reconnectTimeout / 1000}s...`);
                setTimeout(() => this.connect(), this.reconnectTimeout);
                this.reconnectTimeout = Math.min(this.reconnectTimeout * 2, 30000); // Exponential backoff
            }
        };

        this.socket.onerror = (err) => {
            console.error("❌ Bridge WebSocket Error:", err);
        };
    }

    close() {
        this.isClosing = true;
        this.socket?.close();
    }
}
