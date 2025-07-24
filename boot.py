# boot.py

"""
Bootstrap for Gunicorn + Gevent: apply gevent patch (excluding threading),
then expose the Flask app as 'application' for Gunicorn to load.
"""
from gevent import monkey
# Patch IO modules but leave threading intact to avoid threading._after_fork issues
monkey.patch_all(thread=False)

# Import and expose the Flask application
from app import app as application

if __name__ == '__main__':
    # Fallback direct run: serve via Gevent WSGI
    import os
    from gevent.pywsgi import WSGIServer
    port = int(os.environ.get('PORT', '8080'))
    print(f"🚀 Starting Gevent WSGI server on 0.0.0.0:{port}...")
    WSGIServer(('0.0.0.0', port), application).serve_forever()
