import os

from wsgi import application

# Compatibility entrypoint when service root directory is set to bingo_project/.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bingo_project.settings")
app = application
