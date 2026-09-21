"""
Backend-agnostic DAL routers.

The classes here (``UserQuery``, ``PermissionQuery``) don't talk to a
database themselves -- they route each call to a concrete ``BaseQuery``
subclass built for whichever SQL/NoSQL backend was chosen
(``app.dal.sql.*`` or ``app.dal.nosql.*``). Services depend only on the
routers, so swapping backends never touches ``app.services``.
"""
