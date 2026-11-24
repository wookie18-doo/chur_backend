from fastapi.routing import APIRouter

from app.api.v1 import (
    accounts,
    categories,
    currencies,
    families,
    imports,
    incomes,
    monitoring,
    planned_incomes,
    recurring,
    reports,
    spents,
    statement_parsing,
    statement_sources,
    transfers,
    users,
    wishlists,
)

v1_router = APIRouter()
v1_router.include_router(monitoring.router)
v1_router.include_router(users.router)
v1_router.include_router(families.router)
v1_router.include_router(categories.router)
v1_router.include_router(accounts.router)
v1_router.include_router(currencies.router)
v1_router.include_router(transfers.router)
v1_router.include_router(spents.router)
v1_router.include_router(incomes.router)
v1_router.include_router(wishlists.router)
v1_router.include_router(planned_incomes.router)
v1_router.include_router(reports.router)
v1_router.include_router(recurring.router)
v1_router.include_router(imports.router)
v1_router.include_router(statement_parsing.router)
v1_router.include_router(statement_sources.router)
