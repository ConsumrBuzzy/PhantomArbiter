import os
import sys
import subprocess

def build():
    print("🚀 Building Protobufs...")
    
    # Paths
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    proto_dir = os.path.join(project_root, "apps", "datafeed", "src", "datafeed")
    
    # Command
    # python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. apps/datafeed/src/datafeed/market_data.proto
    
    cmd = [
        sys.executable,
        "-m", "grpc_tools.protoc",
        f"-I{project_root}",
        f"--python_out={project_root}",
        f"--grpc_python_out={project_root}",
        os.path.join(proto_dir, "market_data.proto")
    ]
    
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Protobufs compiled successfully.")
    else:
        print("❌ Compilation Failed:")
        print(result.stderr)

if __name__ == "__main__":
    build()
