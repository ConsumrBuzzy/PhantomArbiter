/**
 * Graph Protocol Types
 * -------------------
 * Mirrors src/shared/schemas/graph_protocol.py
 */

export interface GraphNode {
    id: string;
    label: string;
    color: string;
    size: number;
    meta?: Record<string, any>;
}

export interface GraphLink {
    source: string;
    target: string;
    weight: number;
    color: string;
    label?: string;
}

export interface GraphSnapshot {
    type: 'snapshot';
    timestamp: number;
    sequence: number;
    nodes: GraphNode[];
    links: GraphLink[];
}

export interface GraphDiff {
    type: 'diff';
    timestamp: number;
    sequence: number;
    nodes: GraphNode[]; // Upserts
    links: GraphLink[]; // Upserts
    removed_node_ids: string[];
    removed_links: { source: string; target: string }[];
}

export type GraphPayload = GraphSnapshot | GraphDiff;
