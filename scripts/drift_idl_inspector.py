import json
import os
from pathlib import Path

def inspect_drift_idl():
    idl_path = Path("node_modules/@drift-labs@/sdk/src/idl/drift.json")
    if not idl_path.exists():
        # Fallback to alternative paths found earlier
        idl_path = Path("node_modules/@drift-labs/sdk/lib/node/idl/drift.json")
        if not idl_path.exists():
            idl_path = Path("node_modules/@drift-labs/sdk/lib/browser/idl/drift.json")
            if not idl_path.exists():
                print(f"IDL not found at any known path")
                return

    with open(idl_path, "r") as f:
        idl = json.load(f)

    # Search in types
    order_params = None
    for type_def in idl.get("types", []):
        if type_def["name"] == "OrderParams":
            order_params = type_def
            break
    
    if not order_params:
        print("OrderParams not found in types")
        return

    fields = order_params["type"]["fields"]
    
    print("\n--- Raw OrderParams Fields JSON ---")
    print(json.dumps(fields, indent=2))

    # Also check Enums
    print("\n--- Enum Indices ---")
    enums_to_check = ["MarketType", "PositionDirection", "OracleSource", "OrderType"]
    for type_def in idl.get("types", []):
        if type_def["name"] in enums_to_check:
            print(f"Enum: {type_def['name']}")
            variants = type_def["type"]["variants"]
            for idx, variant in enumerate(variants):
                print(f"  {idx}: {variant['name']}")

if __name__ == "__main__":
    inspect_drift_idl()
