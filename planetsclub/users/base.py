from typing import Optional


class BaseUser:
    @property
    def id(self) -> Optional[str]:
        raise NotImplementedError

    @property
    def real_name(self) -> Optional[str]:
        return None

    @property
    def is_authenticated(self) -> Optional[bool]:
        return False

    @property
    def is_active(self) -> Optional[bool]:
        return False

    @property
    def is_member(self) -> Optional[bool]:
        return False

    @property
    def is_admin(self) -> Optional[bool]:
        return False

    def is_member_or_me(self) -> bool:
        return False


class UnauthenticatedUser(BaseUser):
    @property
    def id(self):
        return None
