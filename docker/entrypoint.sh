#!/bin/sh
# Container entrypoint: bring the database schema up to date, then start the app.
set -e

python manage.py migrate --noinput

exec "$@"
