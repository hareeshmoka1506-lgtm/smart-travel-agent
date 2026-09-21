#!/bin/bash
set -e
export PYTHONPATH="/home/site/wwwroot/.python_packages/lib/site-packages:${PYTHONPATH}"
gunicorn --worker-class uvicorn.workers.UvicornWorker --bind=0.0.0.0:8000 --workers 1 --timeout 600 --access-logfile - --error-logfile - app:app
