"""
Router in front of the concrete account DAO.

``AccountQuery`` inherits directly from the concrete ``AccountDAO`` for
whichever backend was chosen, so every generic ``create``/``get``/
``retrieve``/``update``/``delete`` operation is already available on it
as an inherited method, and it only adds the domain-specific lookups
``AccountService`` needs on top of them.
"""

import uuid

from app.dal.sql.account_dao import AccountDAO
from app.db.sql.models.account import Account


class AccountQuery(AccountDAO):
    """Everything ``AccountService`` needs to read and write account data."""

    async def list_for_user(
        self, user_id: uuid.UUID, *, include_inactive: bool = False
    ) -> list[Account]:
        """
        Fetch a user's accounts.

        :param user_id: owner to look up.
        :param include_inactive: whether to include archived accounts.
        :return: matching accounts.
        """
        accounts = await self.retrieve(user_id=user_id)
        if include_inactive:
            return accounts
        return [account for account in accounts if account.is_active]
