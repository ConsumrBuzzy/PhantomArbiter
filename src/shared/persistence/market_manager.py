"""
Market/Pool Persistence Bridge
==============================
Phase 23: Market Map

Manages the bidirectional flow of Pool Graphs between:
1. "Hot" SQLite Cache (MarketRepository)
2. "Cold" JSON Registry (archives/pool_registry.json)
"""

import json
import os
import time
from typing import List, Dict, Optional
from src.shared.system.logging import Logger
from src.shared.system.database.core import DatabaseCore
from src.shared.system.database.repositories.market_repo import MarketRepository
from src.shared.schemas.graph_protocol import (
    GraphSnapshot, GraphDiff, GraphNode, GraphLink, GraphPayload,
    create_snapshot, create_diff
)


class MarketManager:
    """Cartographer for the Liquidity Map."""

    REGISTRY_PATH = "archives/pool_registry.json"

    def __init__(self):
        self.db = DatabaseCore()
        self.repo = MarketRepository(DatabaseCore())
        self.last_snapshot: Optional[GraphSnapshot] = None
        
    def dehydrate(self) -> Dict[str, int]:
        """
        Loads pool graph from JSON archive into SQLite.
        """
        if not os.path.exists(self.REGISTRY_PATH):
            Logger.info("   ℹ️ No Pool Registry found. Discovery required.")
            return 0

        try:
            with open(self.REGISTRY_PATH, "r") as f:
                data = json.load(f)

            pools = data.get("pools", [])
            if not pools:
                return 0

            count = 0
            # Use transaction for speed
            with self.repo.db.cursor(commit=True) as c:
                for p in pools:
                    # Direct insert faster than repo wrapper if doing bulk,
                    # but let's stick to repo for cleaner abstraction if possible.
                    # Actually, repo uses single commits. Let's use direct SQL here for bulk speed
                    # OR optimize repo. For now, just call repo method.

                    self.repo.save_pool(
                        address=p["address"],
                        token_a=p["token_a"],
                        token_b=p["token_b"],
                        dex_label=p.get("dex_label"),
                        liquidity_usd=p.get("liquidity_usd", 0),
                        vol_24h=p.get("vol_24h", 0),
                    )
                    count += 1

            Logger.info(f"   🗺️ Market Map: Restored {count} pools from registry.")
            return count

        except Exception as e:
            Logger.error(f"❌ Pool Rehydration Failed: {e}")
            return 0

    def dehydrate(self) -> bool:
        """
        Saves current SQLite pool data to JSON.
        Implements 'Smart Pruning' to avoid bloat.
        """
        try:
            pools = self.repo.get_all_pools()

            # Smart Pruning / Quality Filter
            # 1. Must have > $X Liquidity (e.g. $500) OR recent volume
            # 2. Must distinguish between "Trash" and "Gems"

            valid_pools = []
            min_liquidity = 500.0  # USD

            for p in pools:
                liq = p.get("liquidity_usd", 0) or 0
                vol = p.get("vol_24h", 0) or 0

                # Keep if: Liquidity > $500 OR Volume > $1000
                if liq > min_liquidity or vol > 1000:
                    valid_pools.append(p)

            data = {
                "meta": {
                    "timestamp": time.time(),
                    "count": len(valid_pools),
                    "version": "1.0",
                    "filter": f"min_liq=${min_liquidity}",
                },
                "pools": valid_pools,
            }

            tmp_path = self.REGISTRY_PATH + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)

            if os.path.exists(self.REGISTRY_PATH):
                os.remove(self.REGISTRY_PATH)
            os.rename(tmp_path, self.REGISTRY_PATH)

            Logger.info(
                f"   💾 Market Map: Archived {len(valid_pools)} pools (Pruned {len(pools) - len(valid_pools)} dust pools)."
            )
            return True

        except Exception as e:
            Logger.error(f"❌ Pool Dehydration Failed: {e}")
            return False

    def get_graph_data(self) -> GraphSnapshot:
        """
        Generates the visual graph data structure (Nodes/Links).
        Returns a strictly typed GraphSnapshot.
        """
        pools = self.repo.get_all_pools()
        
        nodes: Dict[str, GraphNode] = {}
        links: List[GraphLink] = []
        
        # Color mapping
        # SOL = Purple, USDC = Blue, USDT = Green, Others = Gray
        COLOR_SOL = "#9945FF"
        COLOR_USDC = "#2775CA"
        COLOR_USDT = "#26A17B"
        COLOR_DEFAULT = "#808080"
        
        for p in pools:
            pool_addr = p['address']
            mint_a = p['token_a']
            mint_b = p['token_b']
            liq = p.get('liquidity_usd', 0) or 0
            vol = p.get('vol_24h', 0) or 0
            
            # Filter noise
            if liq < 100 and vol < 100:
                continue
                
            # Identify Ecosystem Color
            edge_color = COLOR_DEFAULT
            if "So11111111111111111111111111111111111111112" in [mint_a, mint_b]:
                edge_color = COLOR_SOL
            elif "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" in [mint_a, mint_b]:
                edge_color = COLOR_USDC
            elif "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB" in [mint_a, mint_b]:
                edge_color = COLOR_USDT
                
            # Add Nodes (Idempotent)
            if mint_a not in nodes:
                nodes[mint_a] = {
                    "id": mint_a, 
                    "label": mint_a[:4], # Short label for now
                    "color": edge_color, 
                    "size": 1.0, 
                    "meta": {"type": "token"}
                }
            if mint_b not in nodes:
                nodes[mint_b] = {
                    "id": mint_b, 
                    "label": mint_b[:4],
                    "color": edge_color, 
                    "size": 1.0, 
                    "meta": {"type": "token"}
                }
                
            # Add Link
            links.append({
                "source": mint_a,
                "target": mint_b,
                "weight": vol,
                "color": edge_color,
                "label": p.get('dex_label', 'Unknown')
            })
            
            # Increment Node Size (Degree/Liq proxy)
            nodes[mint_a]['size'] += (liq / 1000.0) 
            nodes[mint_b]['size'] += (liq / 1000.0)

        return create_snapshot(list(nodes.values()), links, seq=int(time.time()))

    def get_graph_diff(self) -> GraphPayload:
        """
        Returns a Differential Update (GraphDiff) if possible, 
        otherwise returns a full GraphSnapshot (first run).
        """
        # 1. Generate Current State
        current_snapshot = self.get_graph_data()
        
        # 2. Check if we have a baseline
        if not self.last_snapshot:
            self.last_snapshot = current_snapshot
            return current_snapshot
            
        # 3. Calculate Diff
        diff = self._calculate_diff(self.last_snapshot, current_snapshot)
        
        # 4. Update Baseline
        self.last_snapshot = current_snapshot
        
        return diff
        
    def _calculate_diff(self, old: GraphSnapshot, new: GraphSnapshot) -> GraphDiff:
        """
        Compares two snapshots and returns the delta.
        """
        # Maps for O(1) Lookup
        old_nodes = {n['id']: n for n in old['nodes']}
        new_nodes = {n['id']: n for n in new['nodes']}
        
        upserted_nodes = []
        removed_node_ids = []
        
        # 1. Detect Upserts (New or Changed)
        for nid, n_node in new_nodes.items():
            o_node = old_nodes.get(nid)
            
            # If new or different, add to upsert list
            # Simple inequality check covers all fields (color, size, label)
            if not o_node or n_node != o_node:
                upserted_nodes.append(n_node)
                
        # 2. Detect Removals
        for nid in old_nodes:
            if nid not in new_nodes:
                removed_node_ids.append(nid)
        
        # 3. Links (Same logic, simple for V1)
        # Ideally check links too, but for V1 let's just trigger updates
        # If links changed, we send them. 
        # Making simple link list comparison:
        # (Optimizing links requires Map{(source,target): params})
        
        # For this phase, we just send ALL links if ANY node changed? No.
        # We need true link diff.
        
        old_links = {(l['source'], l['target']): l for l in old['links']}
        new_links = {(l['source'], l['target']): l for l in new['links']}
        
        upserted_links = []
        removed_links = []
        
        for k, n_link in new_links.items():
            o_link = old_links.get(k)
            if not o_link or n_link != o_link:
                upserted_links.append(n_link)
                
        for k in old_links:
            if k not in new_links:
                removed_links.append({"source": k[0], "target": k[1]})

        return create_diff(
            nodes=upserted_nodes, 
            links=upserted_links, 
            removed_nodes=removed_node_ids, 
            removed_links=removed_links, 
            seq=new['sequence']
        )


    def export_graph_data(self, output_dir: str = "data/viz") -> bool:
        """
        Exports persistent pool data to visual JSON for WebGL rendering.
        """
        try:
            os.makedirs(output_dir, exist_ok=True)

            graph_data = self.get_graph_data()

            with open(f"{output_dir}/nodes.json", "w") as f:
                json.dump(graph_data["nodes"], f, indent=2)

            with open(f"{output_dir}/links.json", "w") as f:
                json.dump(graph_data["links"], f, indent=2)

            Logger.info(
                f"   🎨 Market Map Exported: {len(graph_data['nodes'])} nodes, {len(graph_data['links'])} links to {output_dir}"
            )
            return True

        except Exception as e:
            Logger.error(f"❌ Graph Export Failed: {e}")
            return False
