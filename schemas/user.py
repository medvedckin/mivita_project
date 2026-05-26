from pydantic import BaseModel

from models.user import UserRole


class UserRead(BaseModel):
    id: int
    username: str
    name: str
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True
