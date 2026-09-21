"""
Router in front of the concrete permission DAO.

``PermissionQuery`` inherits directly from the concrete ``PermissionDAO``
for whichever backend was chosen (``app.dal.sql.permission_dao.PermissionDAO``
for SQL databases, or a future ``app.dal.nosql.permission_dao.PermissionDAO``
for MongoDB/Motor), so ``get_effective_permissions`` and every generic
``create``/``get``/``retrieve``/``update``/``delete`` operation are already
available on it as inherited methods. ``PermissionService`` is written
entirely against this class and builds it itself from a db session/
connection -- swapping backends means swapping which ``PermissionDAO`` it
inherits from, not touching ``PermissionService``.
"""

from app.dal.sql.permission_dao import PermissionDAO


class PermissionQuery(PermissionDAO):
    """Everything ``PermissionService`` needs to know about roles/permissions."""
