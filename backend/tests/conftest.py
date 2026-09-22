"""
Shared pytest setup.

Puts both `backend/` (for `app`) and the repo root (for `ml`) on the import
path, so tests can be run from `backend/` without any environment setup.
`ml/` lives beside `backend/` rather than inside it because training code,
saved models and evaluation belong with the machine-learning work.
"""

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)

for path in (BACKEND_DIR, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)
