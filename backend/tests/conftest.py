import os
import sys

# Ensure 'app' package (under backend/app) is importable as top-level
PROJECT_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_BACKEND not in sys.path:
    sys.path.insert(0, PROJECT_BACKEND)
