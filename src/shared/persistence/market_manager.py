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
from typing import List, Dict
from src.shared.system.logging import Logger
from src.shared.system.database.core import DatabaseCore
from src.shared.system.database.repositories.market_repo import MarketRepository

class MarketManager:
    """Cartographer for the Liquidity Map."""
    
    REGISTRY_PATH = "archives/pool_registry.json"
    
    def __init__(self):
        self.db = DatabaseCore()
        self.repo = MarketRepository(self.db)
        
    def rehydrate(self) -> int:
        """
        Loads pool graph from JSON archive into SQLite.
        """
        if not os.path.exists(self.REGISTRY_PATH):
            Logger.info("   ℹ️ No Pool Registry found. Discovery required.")
            return 0
            
        try:
            with open(self.REGISTRY_PATH, 'r') as f:
                data = json.load(f)
                
            pools = data.get('pools', [])
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
                        address=p['address'],
                        token_a=p['token_a'],
                        token_b=p['token_b'],
                        dex_label=p.get('dex_label'),
                        liquidity_usd=p.get('liquidity_usd', 0),
                        vol_24h=p.get('vol_24h', 0)
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
            min_liquidity = 500.0 # USD
            
            for p in pools:
                liq = p.get('liquidity_usd', 0) or 0
                vol = p.get('vol_24h', 0) or 0
                
                # Keep if: Liquidity > $500 OR Volume > $1000
                if liq > min_liquidity or vol > 1000:
                    valid_pools.append(p)
            
            data = {
                "meta": {
                    "timestamp": time.time(),
                    "count": len(valid_pools),
                    "version": "1.0",
                    "filter": f"min_liq=${min_liquidity}"
                },
                "pools": valid_pools
            }
            
            tmp_path = self.REGISTRY_PATH + ".tmp"
            with open(tmp_path, 'w') as f:
                json.dump(data, f, indent=2)
                
            if os.path.exists(self.REGISTRY_PATH):
                os.remove(self.REGISTRY_PATH)
            os.rename(tmp_path, self.REGISTRY_PATH)
            
            Logger.info(f"   💾 Market Map: Archived {len(valid_pools)} pools (Pruned {len(pools) - len(valid_pools)} dust pools).")
            return True
            
        except Exception as e:
            Logger.error(f"❌ Pool Dehydration Failed: {e}")
            return False

    def get_graph_data(self) -> Dict:
        """
        Generates the visual graph data structure (Nodes/Links).
        Returns a dictionary with 'nodes' and 'links' lists.
        """
        pools = self.repo.get_all_pools()
        
        nodes = {}
        links = []
        
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
                nodes[mint_a] = {"id": mint_a, "color": edge_color, "size": 1}
            if mint_b not in nodes:
                nodes[mint_b] = {"id": mint_b, "color": edge_color, "size": 1}
                
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

        return {
            "nodes": list(nodes.values()),
            "links": links
        }

    def export_graph_data(self, output_dir: str = "data/viz") -> bool:
        """
        Exports persistent pool data to visual JSON for WebGL rendering.
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            graph_data = self.get_graph_data()
            
            with open(f"{output_dir}/nodes.json", 'w') as f:
                json.dump(graph_data['nodes'], f, indent=2)
                
            with open(f"{output_dir}/links.json", 'w') as f:
                json.dump(graph_data['links'], f, indent=2)
                
            Logger.info(f"   🎨 Market Map Exported: {len(graph_data['nodes'])} nodes, {len(graph_data['links'])} links to {output_dir}")
            return True
            
        except Exception as e:
            Logger.error(f"❌ Graph Export Failed: {e}")
            return False
