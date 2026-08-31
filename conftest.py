import os
import sys

# Ensure the project root is importable as `config`, `agent`, `src.*` when
# tests are run from any working directory (e.g. `pytest` from repo root).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
