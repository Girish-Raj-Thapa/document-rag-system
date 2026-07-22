import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounts.models import User


from sqlalchemy.exc import IntegrityError
from app.core.exceptions import ConflictError


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str) -> User | None:
        """
        Find a user by their email address.
        """
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """
        Find a user by their UUID.
        """
        return await self.db.get(User, user_id)

    async def create(self, email: str, full_name: str, password: str) -> User:
        """
        Create a new user.
        using `flush()` instead of `commit()`. 
        This assigns an ID to the user but keeps the transaction open in case the Service layer needs to do more.
        """
        user = User(
            email=email,
            full_name=full_name,
            password=password,
        )
        self.db.add(user)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise ConflictError("A user with this email already exists.")
        return user
