#!/bin/sh
set -e

# Seed the served static dir with the bundled landing page on first start.
mkdir -p /srv/static
if [ ! -f /srv/static/index.html ]; then
    cp /etc/site/index.html /srv/static/index.html
fi

python3 /usr/local/bin/server_entrypoint.py

exec nginx -g 'daemon off;'
