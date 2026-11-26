
"""ASCII-named entrypoint for CI; delegates to 偏差断言.py."""

from pathlib import Path
import runpy

if __name__ == "__main__":
    target = Path(__file__).with_name("偏差断言.py")
    runpy.run_path(str(target), run_name="__main__")
