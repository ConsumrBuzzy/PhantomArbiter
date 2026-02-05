import asyncio
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solana.rpc.async_api import AsyncClient
from spl.token.instructions import close_account, CloseAccountParams
from solders.system_program import transfer, TransferParams

# Constants
# Standard SPL Token Program ID
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
# SPL Memo Program ID
MEMO_PROGRAM_ID = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
# Treasury Address (Placeholder - to be configured via env vars in production)
TREASURY_PUBKEY = Pubkey.from_string("11111111111111111111111111111111") 

async def find_zombie_value(client: AsyncClient, owner_pubkey: str):
    """
    Scans for 0-balance accounts and calculates reclaimable SOL.
    
    Args:
        client: AsyncClient instance connected to Solana RPC.
        owner_pubkey: String representation of the owner's public key.
        
    Returns:
        tuple: (list of zombie account PublicKeys, potential SOL value as float)
    """
    owner = Pubkey.from_string(owner_pubkey)
    # Filter for all token accounts owned by the user
    response = await client.get_token_accounts_by_owner(
        owner, 
        {"programId": TOKEN_PROGRAM_ID}
    )
    
    zombie_accounts = []
    # Iterate through accounts to check actual balance/state logic
    # Note: get_token_accounts_by_owner returns accounts. We need to check if they are empty.
    # A more efficient way might be to parse the account data, but checking balance via RPC 
    # for each might be slow if there are thousands. 
    # Optimized approach: The response.value contains the account info. 
    # We can parse the data to find the amount without extra RPC calls if using jsonParsed encoding,
    # but strictly following the requested logic:
    
    for account in response.value:
        # In a real high-perf scenario, we'd batch these or use getProgramAccounts with filters
        balance_resp = await client.get_token_account_balance(account.pubkey)
        if balance_resp.value.amount == "0":
            zombie_accounts.append(account.pubkey)
            
    # Standard rent for a Token Account is approx 0.00203928 SOL
    potential_sol = len(zombie_accounts) * 0.00203928
    return zombie_accounts, potential_sol

def build_trustless_reclaim_tx(owner_pubkey: str, zombie_accounts: list, total_sol: float):
    """
    Constructs a list of instructions for an atomic reclaim transaction.
    Instruction 1-N: Close Account (Rent -> Owner)
    Instruction N+1: 10% Fee Transfer (Owner -> Treasury)
    
    Args:
        owner_pubkey: The wallet causing the rent to be reclaimed.
        zombie_accounts: List of PublicKeys for accounts to close.
        total_sol: Estimated total SOL being reclaimed.
        
    Returns:
        list[Instruction]: List of instructions to include in the transaction.
    """
    owner = Pubkey.from_string(owner_pubkey)
    instructions = []
    
    # 1. Close Instructions
    # This loop generates a close instruction for every zombie account found.
    # The 'dest' must be the owner to ensure the rent goes back to them.
    for acc_pubkey in zombie_accounts:
        params = CloseAccountParams(
            program_id=TOKEN_PROGRAM_ID, 
            account=acc_pubkey, 
            dest=owner, 
            owner=owner
        )
        instructions.append(close_account(params))
    
    # 2. 10% Fee Instruction (Atomic)
    # We calculate 10% of the TOTAL potential formatted SOL, convert to lamports.
    # 1 SOL = 1,000,000,000 lamports.
    fee_lamports = int((total_sol * 0.1) * 1_000_000_000)
    
    # Ensure strict integer for lamports and prevent 0 fee if small
    if fee_lamports > 0:
        instructions.append(
            transfer(
                TransferParams(
                    from_pubkey=owner, 
                    to_pubkey=TREASURY_PUBKEY, 
                    lamports=fee_lamports
                )
            )
        )
    
    return instructions

def create_skim_memo(target_pubkey: str, sol_amount: float, count: int):
    """
    Generates the SPL Memo for the initial 'PI Contact'.
    This is a call-to-action sent to the user.
    """
    message = f"ARBITER: Found {sol_amount:.3f} SOL in {count} zombie accounts. Reclaim via: phantomarbiter.io/skimmer?w={target_pubkey}".encode("utf-8")
    
    # The memo program instruction
    return Instruction(
        program_id=MEMO_PROGRAM_ID, 
        accounts=[AccountMeta(Pubkey.from_string(target_pubkey), is_signer=True, is_writable=True)], 
        data=message
    )
