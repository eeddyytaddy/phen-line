# boot.py

"""
Bootstrap script for Gunicorn + Gevent that patches gevent without touching threading,
then imports the Flask application. This ensures monkey-patching happens before any forking.
"""

from gevent import monkey
# Patch all necessary modules except threading to avoid replacing threading._stop with Event
monkey.patch_all(thread=False)

# Now import the Flask application; Gunicorn will look for `application`
from app import app as application
