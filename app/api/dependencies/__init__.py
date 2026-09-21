"""
Dependency providers for the API layer.

This is the only place in ``app.api`` allowed to know about FastAPI's
dependency injection. Every function here composes ``app.dal``/``app.services``
objects for a single request -- there's one module per service/domain, so
routers never construct a service (or a DAO, or reach into ``app.state``)
themselves.
"""
