# Vercel Python handler for Flask WSGI app
import sys
import os

# Add the parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Export for Vercel - this tells Vercel to use the Flask app directly
# Vercel's Python runtime will handle WSGI conversion automatically
application = app