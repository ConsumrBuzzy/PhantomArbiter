"""
Graph Protocol
==============
Phase 27: The Contract

Defines the JSON Schema for the Visual Bridge.
Strict typing ensures the Backend (Rust/Python) and Frontend (JS)
speak the same language.
"""

from typing import List, Dict, Union, TypedDict, Optional
import time

# -------------------------------------------------------------------------
# PRIMITIVES
# -------------------------------------------------------------------------

class GraphNode(TypedDict):
    id: str             # Mint Address
    label: str          # Ticker / Symbol
    color: str          # Hex Code (Ecosystem Color)
    size: float         # Visual Weight (Liquidity/Degree)
    
    # Optional Metadata for "Hover" Inspector
    meta: Optional[Dict[str, Union[str, float, int]]]

class GraphLink(TypedDict):
    source: str         # Mint A
    target: str         # Mint B
    weight: float       # Visual Thickness (Volume/Liquidity)
    color: str          # Hex Code
    label: Optional[str]# Edge Label (DEX Name)

# -------------------------------------------------------------------------
# PAYLOADS
# -------------------------------------------------------------------------

class GraphSnapshot(TypedDict):
    """Full State Dump (On Connect / Reset)"""
    type: str # "snapshot"
    timestamp: float
    sequence: int
    nodes: List[GraphNode]
    links: List[GraphLink]
    
class GraphDiff(TypedDict):
    """
    Incremental Update (Bandwidth Optimized).
    Uses 'Upsert' logic:
    - If ID exists: Update fields.
    - If ID missing: Create new.
    """
    type: str # "diff"
    timestamp: float
    sequence: int
    
    # Upserts (Add or Update)
    nodes: List[GraphNode] 
    links: List[GraphLink]
    
    # Explicit Removals
    removed_node_ids: List[str]
    removed_links: List[Dict[str, str]] # List of {source, target} pairs

# Union for Type Hinting
GraphPayload = Union[GraphSnapshot, GraphDiff]

def create_snapshot(nodes: List[GraphNode], links: List[GraphLink], seq: int = 0) -> GraphSnapshot:
    return {
        "type": "snapshot",
        "timestamp": time.time(),
        "sequence": seq,
        "nodes": nodes,
        "links": links
    }

def create_diff(nodes: List[GraphNode], links: List[GraphLink], removed_nodes: List[str], removed_links: List[Dict[str, str]], seq: int) -> GraphDiff:
    return {
        "type": "diff",
        "timestamp": time.time(),
        "sequence": seq,
        "nodes": nodes,
        "links": links,
        "removed_node_ids": removed_nodes,
        "removed_links": removed_links
    }
