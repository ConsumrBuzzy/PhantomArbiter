try:
    import driftpy
    # print(f"DriftPy Version: {driftpy.__version__}") # version might not be exposed
    from driftpy import instructions
    print("Instructions module found.")
    if hasattr(instructions, 'get_place_perp_order_ix'):
        print("Function 'get_place_perp_order_ix' FOUND.")
    else:
        print("Function 'get_place_perp_order_ix' NOT FOUND.")
        print("Available:", [x for x in dir(instructions) if 'place' in x])
except Exception as e:
    print(f"Error: {e}")
