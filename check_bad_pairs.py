"""Check bad pairs from database."""
from src.shared.system.db_manager import db_manager

print("Pairs with highest failure rates:")
print("=" * 60)

with db_manager.cursor() as c:
    # Check if table exists and has data
    c.execute("SELECT COUNT(*) as cnt FROM fast_path_attempts")
    count = c.fetchone()['cnt']
    print(f"Total attempts in DB: {count}")
    
    if count > 0:
        c.execute("""
            SELECT pair, 
                   COUNT(*) as attempts,
                   SUM(CASE WHEN success THEN 1 ELSE 0 END) as wins
            FROM fast_path_attempts 
            GROUP BY pair
            ORDER BY 1.0 * wins / attempts ASC
            LIMIT 15
        """)
        rows = c.fetchall()
        
        print(f"\n{'Pair':<20} | {'Attempts':>8} | {'Wins':>6} | Rate")
        print("-" * 55)
        for row in rows:
            rate = 100.0 * row['wins'] / row['attempts'] if row['attempts'] > 0 else 0
            print(f"{row['pair']:<20} | {row['attempts']:>8} | {row['wins']:>6} | {rate:.1f}%")
    else:
        print("No data yet in fast_path_attempts table.")
        
        # Check spread_observations instead
        c.execute("SELECT COUNT(*) as cnt FROM spread_observations")
        spread_count = c.fetchone()['cnt']
        print(f"\nSpread observations: {spread_count}")
        
        if spread_count > 0:
            c.execute("""
                SELECT pair,
                       COUNT(*) as scans,
                       SUM(CASE WHEN was_profitable THEN 1 ELSE 0 END) as profitable
                FROM spread_observations
                GROUP BY pair
                ORDER BY 1.0 * profitable / scans ASC
                LIMIT 15
            """)
            rows = c.fetchall()
            
            print(f"\n{'Pair':<20} | {'Scans':>8} | {'Profit':>6} | Rate")
            print("-" * 55)
            for row in rows:
                rate = 100.0 * row['profitable'] / row['scans'] if row['scans'] > 0 else 0
                print(f"{row['pair']:<20} | {row['scans']:>8} | {row['profitable']:>6} | {rate:.1f}%")
