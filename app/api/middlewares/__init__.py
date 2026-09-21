"""
Custom ASGI middlewares for the API layer.

Add one module per middleware here (e.g. ``auth.py`` for a middleware that
reads and decodes a JWT before FastAPI's dependency injection runs,
``logging.py`` for request logging, ...) and register it on ``app`` in
``app.main`` with ``app.add_middleware(...)``.
"""
