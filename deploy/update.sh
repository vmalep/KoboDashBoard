#!/bin/bash
set -e

cd /srv/kobodashboard
git pull
source .venv/bin/activate
python3 manage.py migrate --no-input
python3 manage.py collectstatic --no-input
sudo systemctl restart kobodashboard
echo "Done. $(git log -1 --oneline)"
