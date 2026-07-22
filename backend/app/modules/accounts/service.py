import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.schemas import TokenPayload
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.modules.accounts.models import User
from app.modules.accounts.repository import UserRepository
from app.modules.accounts.schemas import LoginRequest, RegisterRequest


class AccountService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
    

    async def register_user(self, payload: RegisterRequest) -> User:
        """
        Register a new user.
        """
        normalized_email = payload.email.lower().strip()
        
        # Hash password and create user
        hashed_pw = hash_password(payload.password)
        user = await self.user_repo.create(
            email=normalized_email,
            full_name=payload.full_name.strip(),
            password=hashed_pw,
        )

        # Commit the transaction
        await self.db.commit()
        return user
    
    
    async def login_user(self, payload: LoginRequest) -> User:
        """
        Verify login credentials.
        """
        normalized_email = payload.email.lower().strip()
        user = await self.user_repo.get_by_email(normalized_email)

        if not user or not verify_password(payload.password, user.password):
            raise AuthenticationError("Invalid email or password.")
            
        if not user.is_active:
            raise AuthenticationError("User account is disabled.")

        return user
    

    async def issue_tokens(self, user: User) -> dict:
        """
        Generate Access and Refresh tokens for a user.
        """
        subject = str(user.id)
        access_jti = uuid.uuid4()
        refresh_jti = uuid.uuid4()

        user.current_refresh_jti = refresh_jti
        self.db.add(user)
        await self.db.commit()

        return {
            "access_token": create_access_token(subject=subject, jti=access_jti),
            "refresh_token": create_refresh_token(subject=subject, jti=refresh_jti),
        }
    
    async def rotate_refresh_token(self, payload: TokenPayload) -> User:
        user = await self.user_repo.get_by_id(payload.sub)
        if not user or not user.is_active:
            raise AuthenticationError("Invalid user account.")
        if user.current_refresh_jti != payload.jti:
            # token reuse — someone used an old/stolen refresh token.
            # Nuke the whole session as a precaution.
            user.current_refresh_jti = None
            await self.db.commit()
            raise AuthenticationError("Refresh token reuse detected. Please log in again.")
        return user

        