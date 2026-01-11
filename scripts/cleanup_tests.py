
import os
import shutil

# Create destination directory
archive_base = r"trash/archive/tests"
os.makedirs(archive_base, exist_ok=True)

# List of items to archive (relative to current CWD)
items_to_move = [
    "tests/integration/layer_a",
    "tests/integration/layer_b",
    "tests/unit/layer_b_execution",
    "tests/test_sauron.py",
    "tests/test_spherical_clusters.py",
    "tests/unit/test_near_miss_analyzer.py"
]

for item in items_to_move:
    if os.path.exists(item):
        print(f"Archiving {item}...")
        # Construct destination path
        # If it's a directory, we need to handle potential conflicts or just move it into the folder
        
        # Basename calculation
        basename = os.path.basename(item.rstrip("/\\"))
        dest_path = os.path.join(archive_base, basename)
        
        # Remove dest if exists to allow overwrite/move
        if os.path.exists(dest_path):
            if os.path.isdir(dest_path):
                shutil.rmtree(dest_path)
            else:
                os.remove(dest_path)
                
        shutil.move(item, dest_path)
    else:
        print(f"Skipping {item} (not found)")

print("Cleanup script completed.")
