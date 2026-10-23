"""Keep the existing Render start command (gunicorn app:app) compatible."""
import os
from wsgi import app as _prepared_application

preload_app = True
bind = '0.0.0.0:' + os.environ.get('PORT', '8000')
workers = 1
accesslog = '-'
errorlog = '-'
