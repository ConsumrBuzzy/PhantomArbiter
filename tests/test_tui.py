
import asyncio
import sys
from src.shared.ui.tui_manager import TUIRunner

class MockEngine:
    async def tick(self):
        print("TICK")
        return {"mode": "MOCK", "state": "ACTIVE"}

async def main():
    try:
        engine = MockEngine()
        runner = TUIRunner(engine, "MOCK")
        print("Runner Initialized")
        # Don't run with Live in a headless remote command if it might block/crash
        # But we want to see if it even gets to 'with Live'
        print("Starting Runner...")
        await runner.run()
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
