
import os
import glob

def read_last_log(lines=100):
    log_dir = "logs"
    if not os.path.exists(log_dir):
        print("No logs directory found.")
        return

    # Get list of files sorted by modification time
    files = glob.glob(os.path.join(log_dir, "*.log"))
    if not files:
        print("No log files found.")
        return

    latest_file = max(files, key=os.path.getmtime)
    print(f"--- Reading {latest_file} ---")
    
    try:
        with open(latest_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.readlines()
            for line in content[-lines:]:
                print(line.strip())
    except Exception as e:
        print(f"Error reading log: {e}")

if __name__ == "__main__":
    read_last_log()
