try:
    from phantom_core import SharedTokenMetadata, SignalScanner

    print("✅ Successfully imported SharedTokenMetadata and SignalScanner")
except ImportError as e:
    print(f"❌ Failed to import: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
