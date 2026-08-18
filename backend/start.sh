#!/bin/bash
# Exit on error
set -o errexit

# Run database migrations and cache setup
python manage.py migrate --noinput
python manage.py createcachetable

# Start the Django-Q background worker in the background
echo "Starting Django-Q worker..."
python manage.py qcluster &

# Start the Django Web Server in the foreground
echo "Starting Gunicorn web server..."
exec gunicorn bcip_backend.wsgi:application --bind 0.0.0.0:$PORT
