import uuid
from typing import Literal
from pydantic import BaseModel

class TokenPayload(BaseModel):
    sub: uuid.UUID
    exp: int
    jti: uuid.UUID
    type: Literal["access", "refresh"]
