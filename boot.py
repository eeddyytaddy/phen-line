# boot.py

"""
Bootstrap script for running the Flask app under Gevent's own WSGI server,
avoiding any forking and thus eliminating threading._after_fork issues.
"""
from gevent import monkey
# Patch all IO modules; leave threading alone since we won't fork
monkey.patch_all(thread=False)

import os
from gevent.pywsgi import WSGIServer
from app import app  # your Flask application

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8080'))
    print(f"🚀 Starting Gevent WSGI server on 0.0.0.0:{port}...")
    # Serve the Flask app; handles many concurrent requests via greenlets
    WSGIServer(('0.0.0.0', port), app).serve_forever()
