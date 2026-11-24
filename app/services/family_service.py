import uuid

from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.family_member_query import FamilyMemberQuery
from app.dal.family_query import FamilyQuery
from app.dal.user_query import UserQuery
from app.db.sql.models.enums import FamilyRole
from app.db.sql.models.family import Family, FamilyMember
from app.db.sql.models.users import User


class AlreadyInFamilyError(Exception):
    """Raised when a user who already belongs to a family is added to one."""


class NotInFamilyError(Exception):
    """Raised when an action needs a family membership that doesn't exist."""


class NotFamilyOwnerError(Exception):
    """Raised when a non-owner attempts an owner-only family action."""


class OwnerCannotLeaveError(Exception):
    """Raised when a family's owner tries to leave instead of deleting it."""


class UserNotFoundError(Exception):
    """Raised when a user to add to a family can't be found."""


class FamilyService:
    """
    Business logic for grouping users into families.

    Builds its own :class:`~app.dal.family_query.FamilyQuery` and
    :class:`~app.dal.family_member_query.FamilyMemberQuery` from the db
    session it's given -- callers never construct a query object
    themselves. A user belongs to at most one family at a time.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.families = FamilyQuery(session)
        self.members = FamilyMemberQuery(session)
        self.users = UserQuery(session)

    async def create(self, owner: User, name: str) -> Family:
        """
        Create a new family with ``owner`` as its sole, owning member.

        :param owner: user who will own the new family.
        :param name: family name.
        :raises AlreadyInFamilyError: if ``owner`` already belongs to a family.
        :return: the created family.
        """
        if await self.members.get_by_user(owner.id) is not None:
            raise AlreadyInFamilyError
        family = await self.families.create(name=name)
        await self.members.create(
            user_id=owner.id, family_id=family.id, role=FamilyRole.OWNER
        )
        return family

    async def _require_own_family_as_owner(self, actor_id: uuid.UUID) -> uuid.UUID:
        membership = await self.members.get_by_user(actor_id)
        if membership is None:
            raise NotInFamilyError
        if membership.role != FamilyRole.OWNER:
            raise NotFamilyOwnerError
        return membership.family_id

    async def add_member(
        self,
        actor: User,
        user_id: uuid.UUID | None = None,
        *,
        email: str | None = None,
    ) -> tuple[FamilyMember, User]:
        """
        Add a user to the acting user's family as a plain member.

        :param actor: user requesting the addition -- must own their family.
        :param user_id: user to add; ignored when ``email`` is given.
        :param email: email of the user to add, as an alternative to the id.
        :raises NotInFamilyError: if ``actor`` isn't in a family.
        :raises NotFamilyOwnerError: if ``actor`` isn't that family's owner.
        :raises UserNotFoundError: if no such user exists.
        :raises AlreadyInFamilyError: if the user already belongs to a family.
        :return: the created membership and the added user.
        """
        family_id = await self._require_own_family_as_owner(actor.id)
        if email is not None:
            user = await self.users.get_by_email(email.strip().lower())
        elif user_id is not None:
            user = await self.users.get_by_id(user_id)
        else:
            user = None
        if user is None:
            raise UserNotFoundError
        user_id = user.id
        if await self.members.get_by_user(user_id) is not None:
            raise AlreadyInFamilyError
        member = await self.members.create(
            user_id=user_id, family_id=family_id, role=FamilyRole.MEMBER
        )
        return member, user

    async def rename(self, actor: User, name: str) -> Family:
        """
        Rename the acting user's family.

        :param actor: user requesting the rename -- must own their family.
        :param name: new family name.
        :raises NotInFamilyError: if ``actor`` isn't in a family.
        :raises NotFamilyOwnerError: if ``actor`` isn't that family's owner.
        :return: the renamed family.
        """
        family_id = await self._require_own_family_as_owner(actor.id)
        family = await self.families.update(family_id, name=name)
        assert family is not None  # noqa: S101
        return family

    async def remove_member(self, actor: User, user_id: uuid.UUID) -> None:
        """
        Remove a member from the acting user's family.

        :param actor: user requesting the removal -- must own their family.
        :param user_id: user to remove.
        :raises NotInFamilyError: if ``actor`` isn't in a family.
        :raises NotFamilyOwnerError: if ``actor`` isn't that family's owner.
        :raises OwnerCannotLeaveError: if ``user_id`` is the family's owner --
            an owner is removed by deleting the family, not by this call.
        """
        await self._require_own_family_as_owner(actor.id)
        if actor.id == user_id:
            raise OwnerCannotLeaveError
        await self.members.delete(user_id)

    async def set_member_role(
        self, actor: User, user_id: uuid.UUID, role: FamilyRole
    ) -> tuple[FamilyMember, User]:
        """
        Change a member's role in the acting user's family.

        Making someone the owner hands ownership over: the actor becomes a
        plain member, so a family never has two owners (or none).

        :param actor: user requesting the change -- must own their family.
        :param user_id: member whose role changes.
        :param role: the role to give them.
        :raises NotInFamilyError: if ``actor`` isn't in a family, or
            ``user_id`` isn't in the same family.
        :raises NotFamilyOwnerError: if ``actor`` isn't that family's owner.
        :raises OwnerCannotLeaveError: if the actor tries to demote
            themselves -- ownership is transferred by promoting someone else.
        :return: the updated membership and its user.
        """
        family_id = await self._require_own_family_as_owner(actor.id)
        target = await self.members.get_by_user(user_id)
        user = await self.users.get_by_id(user_id)
        if target is None or target.family_id != family_id or user is None:
            raise NotInFamilyError
        if user_id == actor.id:
            if role != FamilyRole.OWNER:
                raise OwnerCannotLeaveError
            return target, user
        if role == FamilyRole.OWNER:
            await self.members.update(actor.id, role=FamilyRole.MEMBER)
        updated = await self.members.update(user_id, role=role)
        assert updated is not None  # noqa: S101
        return updated, user

    async def leave(self, actor: User) -> None:
        """
        Remove the acting user from their own family.

        :param actor: user leaving.
        :raises NotInFamilyError: if ``actor`` isn't in a family.
        :raises OwnerCannotLeaveError: if ``actor`` owns their family.
        """
        membership = await self.members.get_by_user(actor.id)
        if membership is None:
            raise NotInFamilyError
        if membership.role == FamilyRole.OWNER:
            raise OwnerCannotLeaveError
        await self.members.delete(actor.id)

    async def list_members(self, actor: User) -> list[FamilyMember]:
        """
        List every member of the acting user's family.

        :param actor: user requesting the list.
        :raises NotInFamilyError: if ``actor`` isn't in a family.
        :return: memberships in the actor's family.
        """
        membership = await self.members.get_by_user(actor.id)
        if membership is None:
            raise NotInFamilyError
        return await self.members.list_members(membership.family_id)

    async def list_members_with_users(
        self, actor: User
    ) -> list[tuple[FamilyMember, User]]:
        """
        List the acting user's family members together with their users.

        :param actor: user requesting the list.
        :raises NotInFamilyError: if ``actor`` isn't in a family.
        :return: ``(membership, user)`` pairs.
        """
        membership = await self.members.get_by_user(actor.id)
        if membership is None:
            raise NotInFamilyError
        return await self.members.list_with_users(membership.family_id)

    async def get_own_family(self, actor: User) -> Family | None:
        """
        Fetch the acting user's family, if any.

        :param actor: user requesting their family.
        :return: the family, or ``None`` if ``actor`` isn't in one.
        """
        membership = await self.members.get_by_user(actor.id)
        if membership is None:
            return None
        return await self.families.get(membership.family_id)
