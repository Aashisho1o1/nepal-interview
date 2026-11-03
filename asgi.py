"""Entry point for hosted deployments (Vercel's Python runtime, or any ASGI server).

The API and its domain package live in services/api and packages/core, which are not
installed as packages, so they are put on the import path here.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _p in ("packages/core", "services/api"):
    if str(_ROOT / _p) not in sys.path:
        sys.path.insert(0, str(_ROOT / _p))

from interview_api.app import create_app  # noqa: E402

app = create_app()
