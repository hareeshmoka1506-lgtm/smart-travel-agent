import sys
from pathlib import Path

_wwwroot = Path(__file__).resolve().parent
for _candidate in [_wwwroot / ".python_packages" / "lib" / "site-packages", *_wwwroot.glob("antenv/lib/python*/site-packages")]:
    if _candidate.is_dir():
        sys.path.insert(0, str(_candidate))

from app import app

try:
    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(app)
    wsgi_app = application
except Exception:
    application = app
    wsgi_app = app
