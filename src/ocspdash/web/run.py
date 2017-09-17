# -*- coding: utf-8 -*-

"""

This file should be used to run the flask app with something like Gunicorn. For example:
gunicorn -b 0.0.0.0:8000 ocspdash.web.run:app

This file should NOT be imported anywhere, though, since it would instantiate the app.

"""

from ocspdash.web import create_application

app = create_application()
