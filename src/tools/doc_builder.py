import os
import sys
import inspect
import importlib.util

# Paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.append(PROJECT_ROOT)
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")

# Configuration
MODULES_TO_DOC = [
    "src.strategies.tactical",
    "src.strategies.components.decision_engine",
    "src.strategies.components.data_feed_manager",
    "src.strategy.watcher",
    "src.system.db_manager",
    "src.system.data_source_manager",
    "src.execution.position_manager",
]


def load_module_from_path(module_name):
    """Load a module dynamically."""
    try:
        return importlib.import_module(module_name)
    except Exception as e:
        print(f"Error loading {module_name}: {e}")
        return None


def get_class_doc(cls):
    """Format class documentation."""
    doc = f"## {cls.__name__}\n\n"
    if cls.__doc__:
        doc += f"{inspect.cleandoc(cls.__doc__)}\n\n"

    # Methods
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_") or name == "__init__":
            doc += f"### `{name}`\n"
            if method.__doc__:
                doc += f"{inspect.cleandoc(method.__doc__)}\n\n"
            else:
                doc += "*No documentation available.*\n\n"
    return doc


def build_docs():
    """Generate API.md."""
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)

    output = "# PhantomTrader API Reference\n\n"
    output += "Auto-generated documentation for Core Components.\n\n"

    for module_name in MODULES_TO_DOC:
        module = load_module_from_path(module_name)
        if not module:
            continue

        output += f"# Module: `{module_name}`\n\n"

        for name, obj in inspect.getmembers(module, predicate=inspect.isclass):
            if obj.__module__ == module_name:
                output += get_class_doc(obj)

    with open(os.path.join(DOCS_DIR, "API.md"), "w") as f:
        f.write(output)

    print("✅ Generated docs/API.md")


if __name__ == "__main__":
    build_docs()
