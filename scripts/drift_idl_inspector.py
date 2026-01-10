import json
import os
from pathlib import Path

def inspect_drift_idl():
    idl_path = Path("node_modules/@drift-labs/sdk/src/idl/drift.json")
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

    enums_to_check = ["MarketType", "PositionDirection", "OracleSource", "OrderType", "PostOnlyParam", "OrderTriggerCondition"]
    order_params = None
    for type_def in idl.get("types", []):
        if type_def["name"] == "OrderParams":
            order_params = type_def
            break
    
    if not order_params:
        print("OrderParams not found in types")
        return

    fields = order_params["type"]["fields"]
    
    with open("src/delta_neutral/drift_order_params.json", "w") as f:
        json.dump(fields, f, indent=2)
    print(f"OrderParams layout written to src/delta_neutral/drift_order_params.json")

    # Check placePerpOrder instruction accounts
    place_perp_order = next((ix for ix in idl.get("instructions", []) if ix["name"] == "placePerpOrder"), None)
    if place_perp_order:
        with open("src/delta_neutral/drift_instruction_accounts.json", "w") as f:
            json.dump(place_perp_order["accounts"], f, indent=2)
        print(f"placePerpOrder accounts written to src/delta_neutral/drift_instruction_accounts.json")

    # Also check Enums
    with open("src/delta_neutral/drift_enums.json", "w") as f:
        enums = {name: [] for name in enums_to_check}
        for type_def in idl.get("types", []):
            if type_def["name"] in enums_to_check:
                enums[type_def["name"]] = [v["name"] for v in type_def["type"]["variants"]]
        json.dump(enums, f, indent=2)
    print(f"Enums written to src/delta_neutral/drift_enums.json")

if __name__ == "__main__":
    inspect_drift_idl()
