"""
Skimmer Core - Private Investigator
====================================
Singleton class for zombie account scanning and rent reclamation discovery.

ADR-005 Safety Guardrails:
1. MAX_ACCOUNTS_PER_RUN: Prevents unbounded scanning
2. RPC Rate Limiting: 50ms delay between requests
3. LP Position Detection: Prevents closing active liquidity
4. 30-Day Activity Check: Flags recent activity as HIGH risk
5. Priority Fee Gate: Prevents dust loss when fees spike

Architecture:
- Shares RpcConnectionManager with main bot (no resource duplication)
- Writes to ZombieRepository (discovery phase)
- Main bot executes closures during low-gas windows (execution phase)
"""

import time
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from src.shared.infrastructure.rpc_manager import RpcConnectionManager
from src.shared.system.database.core import DatabaseCore
from src.shared.system.database.repositories.zombie_repo import ZombieRepository
from src.shared.system.logging import Logger


@dataclass
class ScanConfig:
    """Configuration for scanning operations."""
    max_accounts_per_run: int = 100
    rpc_request_delay_ms: int = 50
    min_yield_sol: float = 0.001
    activity_window_days: int = 30
    priority_fee_multiplier: float = 2.0  # Min yield must be 2x current priority fee


class SkimmerCore:
    """
    Singleton class for zombie account discovery.
    
    Usage:
        skimmer = SkimmerCore()
        results = skimmer.scan_targets(addresses, dry_run=True)
        stats = skimmer.get_statistics()
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SkimmerCore, cls).__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        """Initialize Skimmer components."""
        self.config = ScanConfig()
        
        # Shared RPC connection (uses existing failover pool)
        self.rpc_manager = RpcConnectionManager()
        
        # Database access
        self.db = DatabaseCore()
        self.repo = ZombieRepository(self.db)
        self.repo.init_table()
        
        Logger.info("🕵️ [Skimmer] Core initialized (Tier 2 Architecture)")
    
    def scan_targets(
        self, 
        addresses: List[str], 
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Scan addresses for zombie account potential.
        
        Args:
            addresses: List of Solana addresses to analyze
            dry_run: If True, logs results but doesn't persist to DB
        
        Returns:
            {
                'total_scanned': int,
                'zombies_found': int,
                'skipped': int,
                'estimated_yield_sol': float,
                'priority_fee_sol': float,
                'results': List[Dict]
            }
        
        Safety:
            - Enforces MAX_ACCOUNTS_PER_RUN limit
            - Rate-limited RPC requests
            - Checks priority fees before flagging targets
        """
        # Safety: Enforce account limit
        if len(addresses) > self.config.max_accounts_per_run:
            Logger.warning(
                f"⚠️ [Skimmer] Truncating scan from {len(addresses)} to "
                f"{self.config.max_accounts_per_run} accounts (safety limit)"
            )
            addresses = addresses[:self.config.max_accounts_per_run]
        
        Logger.info(f"🔍 [Skimmer] Starting scan of {len(addresses)} addresses (dry_run={dry_run})")
        
        # Get current priority fee for dust comparison
        priority_fee_sol = self._get_current_priority_fee()
        min_yield_threshold = max(
            self.config.min_yield_sol,
            priority_fee_sol * self.config.priority_fee_multiplier
        )
        
        Logger.info(
            f"💰 [Skimmer] Priority fee: {priority_fee_sol:.6f} SOL | "
            f"Min yield threshold: {min_yield_threshold:.6f} SOL"
        )
        
        results = []
        zombies_found = 0
        skipped = 0
        total_yield = 0.0
        
        for i, address in enumerate(addresses):
            try:
                # Rate limiting
                if i > 0:
                    time.sleep(self.config.rpc_request_delay_ms / 1000.0)
                
                # Fetch account data
                account_data = self._fetch_account_info(address)
                
                if not account_data:
                    skipped += 1
                    continue
                
                # Analyze account
                analysis = self._analyze_account(account_data, address, min_yield_threshold)
                
                if analysis['is_zombie']:
                    zombies_found += 1
                    total_yield += analysis['estimated_yield_sol']
                    
                    results.append({
                        'address': address,
                        'estimated_yield_sol': analysis['estimated_yield_sol'],
                        'risk_score': analysis['risk_score'],
                        'reason': analysis['reason'],
                        'last_transaction_time': analysis.get('last_transaction_time')
                    })
                    
                    # Persist to DB (unless dry-run)
                    if not dry_run:
                        if analysis['risk_score'] == 'HIGH':
                            # Skip high-risk (needs manual review)
                            self.repo.mark_skipped(address, analysis['reason'])
                            skipped += 1
                        else:
                            self.repo.add_target(
                                address=address,
                                estimated_yield_sol=analysis['estimated_yield_sol'],
                                risk_score=analysis['risk_score'],
                                total_transactions=analysis.get('total_transactions', 0),
                                success_rate=analysis.get('success_rate', 0.0),
                                last_transaction_time=analysis.get('last_transaction_time'),
                                metadata=json.dumps({
                                    'reason': analysis['reason'],
                                    'scan_timestamp': time.time()
                                })
                            )
                else:
                    skipped += 1
                
            except Exception as e:
                Logger.error(f"❌ [Skimmer] Error scanning {address[:8]}...: {e}")
                skipped += 1
                continue
        
        summary = {
            'total_scanned': len(addresses),
            'zombies_found': zombies_found,
            'skipped': skipped,
            'estimated_yield_sol': total_yield,
            'priority_fee_sol': priority_fee_sol,
            'min_yield_threshold': min_yield_threshold,
            'dry_run': dry_run,
            'results': results
        }
        
        Logger.success(
            f"✅ [Skimmer] Scan complete: {zombies_found} zombies found, "
            f"{total_yield:.4f} SOL potential yield"
        )
        
        return summary
    
    def _fetch_account_info(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Fetch account data from RPC.
        
        Returns:
            Account info dict or None if account doesn't exist
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [
                    address,
                    {"encoding": "jsonParsed"}
                ]
            }
            
            response = self.rpc_manager.post(payload, timeout=5)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            result = data.get('result', {})
            
            if not result or result.get('value') is None:
                return None
            
            return result['value']
            
        except Exception as e:
            Logger.debug(f"[Skimmer] RPC error for {address[:8]}...: {e}")
            return None
    
    def _get_current_priority_fee(self) -> float:
        """
        Fetch current priority fee from RPC.
        
        Returns:
            Priority fee in SOL (uses recent prioritization fees API)
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getRecentPrioritizationFees",
                "params": [
                    [{"limit": 20}]  # Last 20 blocks
                ]
            }
            
            response = self.rpc_manager.post(payload, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                fees = data.get('result', [])
                
                if fees:
                    # Get median fee (more stable than max)
                    fee_values = sorted([f.get('prioritizationFee', 0) for f in fees])
                    median_lamports = fee_values[len(fee_values) // 2]
                    return median_lamports / 1e9  # Convert lamports to SOL
            
            # Fallback: Conservative estimate
            return 0.0001  # 0.1 milli-SOL
            
        except Exception as e:
            Logger.debug(f"[Skimmer] Priority fee fetch failed: {e}, using fallback")
            return 0.0001
    
    def _analyze_account(
        self, 
        account_data: Dict[str, Any], 
        address: str,
        min_yield_threshold: float
    ) -> Dict[str, Any]:
        """
        Analyze account to determine if it's a zombie candidate.
        
        Args:
            account_data: RPC account info
            address: Account address
            min_yield_threshold: Minimum profitable yield after fees
        
        Returns:
            {
                'is_zombie': bool,
                'estimated_yield_sol': float,
                'risk_score': str,
                'reason': str,
                'last_transaction_time': float (optional),
                'total_transactions': int (optional)
            }
        
        Safety Checks:
        1. LP position detection (Raydium/Orca programs)
        2. 30-day activity window (recent txns = HIGH risk)
        3. Minimum yield vs priority fee (dust prevention)
        """
        lamports = account_data.get('lamports', 0)
        owner = account_data.get('owner', '')
        
        # Estimate rent-exempt minimum (varies by account size)
        data_len = len(account_data.get('data', []))
        rent_exempt_lamports = self._calculate_rent_exempt_minimum(data_len)
        
        # Potential yield (balance - rent exempt minimum)
        potential_yield_lamports = lamports - rent_exempt_lamports
        estimated_yield_sol = potential_yield_lamports / 1e9
        
        # Default: Not a zombie
        result = {
            'is_zombie': False,
            'estimated_yield_sol': 0.0,
            'risk_score': 'MEDIUM',
            'reason': 'Not profitable'
        }
        
        # Check 1: Insufficient yield
        if estimated_yield_sol < min_yield_threshold:
            result['reason'] = f'Yield {estimated_yield_sol:.6f} < threshold {min_yield_threshold:.6f}'
            return result
        
        # Check 2: LP Position Detection (Raydium, Orca, Meteora)
        lp_programs = [
            '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8',  # Raydium AMM
            '9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP',  # Orca Whirlpool
            'Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB',  # Meteora
        ]
        
        if owner in lp_programs:
            result['reason'] = 'Active LP position detected'
            result['risk_score'] = 'HIGH'
            return result
        
        # Check 3: Recent Activity (30-day window)
        # Note: This requires getSignaturesForAddress which is expensive
        # For now, we'll accept this as a future enhancement
        # and rely on the HIGH risk flag for manual review
        
        last_tx_time = self._get_last_transaction_time(address)
        if last_tx_time:
            result['last_transaction_time'] = last_tx_time
            
            # If activity within last 30 days, flag as HIGH risk
            thirty_days_ago = time.time() - (self.config.activity_window_days * 86400)
            if last_tx_time > thirty_days_ago:
                result['is_zombie'] = True  # Still a candidate
                result['estimated_yield_sol'] = estimated_yield_sol
                result['risk_score'] = 'HIGH'
                result['reason'] = f'Recent activity ({int((time.time() - last_tx_time) / 86400)} days ago)'
                return result
        
        # Passed all checks: LOW risk zombie
        result['is_zombie'] = True
        result['estimated_yield_sol'] = estimated_yield_sol
        result['risk_score'] = 'LOW'
        result['reason'] = f'Dormant account, {estimated_yield_sol:.6f} SOL reclaimable'
        
        return result
    
    def _calculate_rent_exempt_minimum(self, data_len: int) -> int:
        """
        Calculate rent-exempt minimum for account size.
        
        Formula (Solana v1.18+):
            rent_exempt = (account_size + 128) * lamports_per_byte_year * 2 / slots_per_year
        
        Simplified conservative estimate:
            ~0.00089088 SOL per byte
        """
        if data_len == 0:
            return 890880  # Empty account ~0.00089 SOL
        
        # Conservative: 0.001 SOL per byte (accounts for rent increases)
        return int(data_len * 1000000)
    
    def _get_last_transaction_time(self, address: str) -> Optional[float]:
        """
        Fetch last transaction timestamp for address.
        
        Note: This is RPC-intensive. Use sparingly or cache results.
        
        Returns:
            Unix timestamp of last transaction or None
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    address,
                    {"limit": 1}  # Only need most recent
                ]
            }
            
            response = self.rpc_manager.post(payload, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                signatures = data.get('result', [])
                
                if signatures:
                    # blockTime is Unix timestamp
                    return float(signatures[0].get('blockTime', 0))
            
            return None
            
        except Exception as e:
            Logger.debug(f"[Skimmer] Last tx fetch failed for {address[:8]}...: {e}")
            return None
    
    def _is_active_lp_position(self, account_data: Dict[str, Any]) -> bool:
        """
        Detect if account is an active LP position.
        
        Checks:
        - Owner program (Raydium, Orca, Meteora)
        - Non-zero balance
        - Token account with liquidity
        
        Returns:
            True if LP position detected (should NOT close)
        """
        owner = account_data.get('owner', '')
        
        # Known LP program IDs
        lp_programs = [
            '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8',  # Raydium AMM
            '9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP',  # Orca Whirlpool  
            'Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB',  # Meteora
            'PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY',   # Phoenix
        ]
        
        return owner in lp_programs
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Fetch aggregate statistics from ZombieRepository.
        
        Returns:
            {
                'total_targets': int,
                'pending': int,
                'verified': int,
                'closed': int,
                'skipped': int,
                'failed': int,
                'total_estimated_yield_sol': float
            }
        """
        return self.repo.get_scan_statistics()
    
    def execute_closures(
        self, 
        dry_run: bool = True,
        max_closures: int = 10
    ) -> Dict[str, Any]:
        """
        Execute account closures for verified targets.
        
        Args:
            dry_run: If True, simulates closures without sending transactions
            max_closures: Maximum accounts to close in one run
        
        Returns:
            {
                'attempted': int,
                'successful': int,
                'failed': int,
                'total_yield_sol': float
            }
        
        Note:
            This is a placeholder. Actual closure logic requires:
            1. RECLAMATION_KEYPAIR from environment
            2. Transaction building with closeAccount instruction
            3. Priority fee calculation
            4. Transaction simulation before sending
        """
        Logger.warning("⚠️ [Skimmer] execute_closures() not yet implemented")
        Logger.info("   Closure execution will be integrated into main bot's low-gas window")
        
        return {
            'attempted': 0,
            'successful': 0,
            'failed': 0,
            'total_yield_sol': 0.0
        }
