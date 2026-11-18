"""Keep the existing Render start command (gunicorn app:app) compatible."""
import os
from wsgi import app as _prepared_application

preload_app = True
bind = '0.0.0.0:' + os.environ.get('PORT', '8000')
workers = 1
accesslog = '-'
# Do not record bearer result URLs, query strings, referrers, IPs or headers.
# Render/proxy logs have separate settings and must be reviewed by the owner.
access_log_format = 'method=%(m)s status=%(s)s bytes=%(B)s duration_us=%(D)s'
errorlog = '-'
