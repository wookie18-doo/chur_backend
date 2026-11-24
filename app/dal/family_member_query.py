"""
Router in front of the concrete family-member DAO.

``FamilyMemberQuery`` inherits directly from the concrete
``FamilyMemberDAO`` for whichever backend was chosen, so every generic
``create``/``get``/``retrieve``/``update``/``delete`` operation is
already available on it as an inherited method, and it only adds the
domain-specific lookups ``FamilyService``/``VisibilityService`` need on
top of them.
"""

import uuid

from sqlmodel import case, col, select

from app.dal.sql.family_member_dao import FamilyMemberDAO
from app.db.sql.models.enums import FamilyRole
from app.db.sql.models.family import FamilyMember
from app.db.sql.models.users import User


class FamilyMemberQuery(FamilyMemberDAO):
    """Everything needed to resolve a user's family membership."""

    async def get_by_user(self, user_id: uuid.UUID) -> FamilyMember | None:
        """
        Fetch a user's family membership, if any.

        ``user_id`` is the table's primary key, so this is a plain
        by-primary-key lookup -- named for readability at call sites.

        :param user_id: user to look up.
        :return: the membership, or ``None`` if the user isn't in a family.
        """
        return await self.get(user_id)

    async def list_members(self, family_id: uuid.UUID) -> list[FamilyMember]:
        """
        Fetch every member of a family.

        :param family_id: family to look up.
        :return: memberships belonging to that family.
        """
        return await self.retrieve(family_id=family_id)

    async def get_family_id_for_user(self, user_id: uuid.UUID) -> uuid.UUID | None:
        """
        Fetch the id of the family a user belongs to, if any.

        :param user_id: user to look up.
        :return: the family id, or ``None`` if the user isn't in a family.
        """
        member = await self.get_by_user(user_id)
        return member.family_id if member is not None else None

    async def list_with_users(
        self, family_id: uuid.UUID
    ) -> list[tuple[FamilyMember, User]]:
        """
        Fetch every member of a family together with their user record.

        :param family_id: family to look up.
        :return: ``(membership, user)`` pairs, owner first.
        """
        query = (
            select(FamilyMember, User)
            .join(User, col(User.id) == col(FamilyMember.user_id))
            .where(FamilyMember.family_id == family_id)
            .order_by(
                case((FamilyMember.role == FamilyRole.OWNER, 0), else_=1),
                col(User.email),
            )
        )
        result = await self.session.exec(query)
        return list(result.all())
