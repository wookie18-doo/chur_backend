"""Business logic for chur.

Services own the business rules (validation, authorization, orchestration)
and are built on top of ``app.dal`` (database queries) and ``app.libs``
(low-level third-party integrations). Nothing outside this package should
talk to ``app.dal`` or ``app.libs`` directly -- ``app.api`` and ``app.gql``
call services, and taskiq tasks can depend on the same service objects via
``TaskiqDepends``.
"""
