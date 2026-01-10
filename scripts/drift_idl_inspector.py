import json
import os
from pathlib import Path

def inspect_drift_idl():
    idl_path = Path("node_modules/@drift-labs/sdk/src/idl/drift.json")
    if not idl_path.exists():
        print(f"IDL not found at {idl_path}")
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

    print(f"{'#':<3} | {'Option':<8} | {'Field Name':<25} | {'Type':<20} | {'Struct'}")
    print("-" * 75)
    for i, field in enumerate(fields):
        name = field["name"]
        f_type = field["type"]
        
        is_option = False
        if isinstance(f_type, dict) and "option" in f_type:
            is_option = True
            inner_type = f_type["option"]
        else:
            inner_type = f_type

        # Handle defined types (Enums)
        if isinstance(inner_type, dict) and "defined" in inner_type:
            type_str = f"Enum({inner_type['defined']})"
            fmt = "B"
        else:
            type_str = str(inner_type)
            fmt = struct_mapping.get(inner_type, "Unknown")

        option_str = "Yes" if is_option else "No"
        print(f"{i+1:3d} | {option_str:<8} | {name:<25} | {type_str:<20} | {fmt}")

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
