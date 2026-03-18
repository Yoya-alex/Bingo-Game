import os

from bingo_project.wsgi import application

# Compatibility entrypoint for platforms configured with "gunicorn app:app".
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bingo_project.settings")
app = application
