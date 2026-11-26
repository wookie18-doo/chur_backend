"""
Router in front of the concrete account DAO.

``AccountQuery`` inherits directly from the concrete ``AccountDAO`` for
whichever backend was chosen, so every generic ``create``/``get``/
``retrieve``/``update``/``delete`` operation is already available on it
as an inherited method, and it only adds the domain-specific lookups
``AccountService`` needs on top of them.
"""

import uuid
from collections.abc import Iterable

from sqlmodel import col, select

from app.dal.sql.account_dao import AccountDAO
from app.db.sql.models.account import Account


class AccountQuery(AccountDAO):
    """Everything ``AccountService`` needs to read and write account data."""

    async def list_for_users(
        self, user_ids: Iterable[uuid.UUID], *, include_inactive: bool = False
    ) -> list[Account]:
        """
        Fetch every account owned by any of the given users.

        :param user_ids: owners to look up.
        :param include_inactive: whether to include archived accounts.
        :return: matching accounts, grouped by owner.
        """
        query = select(Account).where(col(Account.user_id).in_(list(user_ids)))
        if not include_inactive:
            query = query.where(col(Account.is_active).is_(True))
        query = query.order_by(col(Account.user_id), col(Account.name))
        result = await self.session.exec(query)
        return list(result.all())
