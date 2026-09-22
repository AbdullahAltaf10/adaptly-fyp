"""
Makes the repo-root `ml/` package importable from the backend.

`ml/` sits beside `backend/` rather than inside it, because training code,
saved models and evaluation belong with the machine-learning work, not with the
web server. The backend still needs `ml.inference` at runtime, so the repo root
goes on the import path here - in one place, imported early by app.main, rather
than repeated in every module that needs it.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
