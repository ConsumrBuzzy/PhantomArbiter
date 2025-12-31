
import os
import shutil
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
PAPER_DIR = os.path.join(DATA_DIR, "paper_sessions")

def reset_paper_data():
    print("🧹 Cleaning up Paper Wallet Sessions...")
    
    if os.path.exists(PAPER_DIR):
        try:
            shutil.rmtree(PAPER_DIR)
            os.makedirs(PAPER_DIR)
            print("✅ 'data/paper_sessions/' has been cleared.")
        except Exception as e:
            print(f"❌ Failed to delete directory: {e}")
            return
    else:
        print("ℹ️ No paper sessions found.")
        
    print("\n✨ Ready for fresh start. Run 'python main.py pulse' or 'graduation'.")

if __name__ == "__main__":
    confirm = input("Are you sure you want to wipe all Paper Trading data? (y/n): ")
    if confirm.lower() == 'y':
        reset_paper_data()
    else:
        print("Cancelled.")
