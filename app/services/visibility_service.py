"""
Shared "who can see this" rule for every owned, visibility-tagged record.

Applies to any model with a ``user_id`` (owner) and a ``visibility``
column (``Spent``, ``Income``, ``Wishlist``, ``WishlistItem``,
``PlannedIncome``, ``RecurringTransaction``, ...): the owner can always
read/write their own record; any other user can only *read* it, and only
when its ``visibility`` is ``Visibility.FAMILY`` and the reader shares a
family with the owner. Everyone else gets treated as if the record
doesn't exist.
"""

import uuid

from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.family_member_query import FamilyMemberQuery
from app.db.sql.models.enums import Visibility


class VisibilityService:
    """
    Business logic for who may see an owned, visibility-tagged record.

    Builds its own :class:`~app.dal.family_member_query.FamilyMemberQuery`
    from the db session it's given -- callers never construct a query
    object themselves.
    """

    def __init__(self, requester_id: uuid.UUID, session: AsyncSession) -> None:
        self.requester_id = requester_id
        self.queries = FamilyMemberQuery(session)

    async def can_view(self, owner_id: uuid.UUID, visibility: Visibility) -> bool:
        """
        Check whether the requester may read a record with this owner/visibility.

        :param owner_id: the record's owner.
        :param visibility: the record's visibility.
        :return: whether the requester may read it.
        """
        if owner_id == self.requester_id:
            return True
        if visibility != Visibility.FAMILY:
            return False
        requester_family = await self.queries.get_family_id_for_user(self.requester_id)
        if requester_family is None:
            return False
        owner_family = await self.queries.get_family_id_for_user(owner_id)
        return owner_family == requester_family

    async def visible_owner_ids(self, *, scope: str) -> set[uuid.UUID]:
        """
        Resolve the set of owner ids a list query should consider.

        This alone doesn't fully decide visibility -- pass both this
        result *and* ``self.requester_id`` into the resource's own DAL
        list method (e.g. ``SpentQuery.list_for_range``), which ANDs in
        its own ``user_id == requester_id OR visibility == FAMILY``
        clause. That's what keeps another family member's ``PRIVATE``
        rows out of a family-scope list: the requester's own rows pass
        regardless of visibility, everyone else's only pass when shared.
        Building that clause is each DAL's own job (it needs the actual
        SQLModel column expressions), not this service's -- the `dal`
        layer never imports from `services`.

        :param scope: ``"me"`` for just the requester, ``"family"`` for
            everyone who shares the requester's family (falls back to
            just the requester if they aren't in one).
        :return: owner ids to filter a list query by.
        """
        if scope == "me":
            return {self.requester_id}
        members = await self.queries.get_by_user(self.requester_id)
        if members is None:
            return {self.requester_id}
        family_members = await self.queries.list_members(members.family_id)
        return {member.user_id for member in family_members}
