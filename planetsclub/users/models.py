"""users"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple, Type, TypeVar

import dateutil.parser
import msgpack
from pytz import UTC
from starlette.authentication import AuthCredentials

from planetsclub.services import services
from planetsclub.services.elasticsearch import ESDocModel

from .base import BaseUser, UnauthenticatedUser

T = TypeVar("T", bound="UserModel")


FBAPI_BASE = "https://graph.facebook.com/v3.3"
FBAPI_GROUP_BASE = FBAPI_BASE + "/727594310962689"


class UserModel(ESDocModel, BaseUser):
    ES_INDEX = "planets-users"
    _CACHE_KEY = "users_cache"

    # @classmethod
    # def get_by_google_user_id(cls, google_user_id):
    #     res = cls.search_es({
    #         'query': {'match': {'google_user_id': google_user_id}},
    #         'size': 1,
    #     })
    #     return res[0] if res else None

    # @classmethod
    # def get_by_email(cls, email):
    #     res = cls.search_es({
    #         'query': {'match': {'email': email}},
    #         'size': 1,
    #     })
    #     return res[0] if res else None

    @property
    def is_active(self):
        return not self._data.get("deactivated", False)

    @property
    def is_authenticated(self):
        return self.is_active

    @property
    def is_admin(self) -> Optional[bool]:
        if not self._user.is_member:
            return None
        return self.is_authenticated and self._data.get("is_admin")

    is_owner = is_admin

    @property
    def is_member(self) -> Optional[bool]:
        return True
        # def _ismember(user):
        #     return self.is_authenticated and (
        #         self._data.get("email", "").endswith("@jjp.jp")
        #         or self._data.get("is_admin")
        #     )

        # if (self._user.id != self.id) and not _ismember(self._user):
        #     return None

        # return _ismember(self)

    def is_member_or_me(self):
        return self._user.is_member or (self._user.id == self._id)

    @property
    def real_name(self):
        return self._data.get("real_name")

    @property
    def email(self):
        return self._data.get("email") if self.is_member_or_me() else None

    @property
    def google_id(self):
        return self._data.get("google_id") if self.is_member_or_me() else None

    @property
    def picture_uri(self):
        return self._data.get("picture_uri")

    @property
    def created_at(self) -> Optional[datetime]:
        if not self._user.is_member:
            return None
        v = self._data.get("created_at")
        return dateutil.parser.parse(v) if v else None

    @property
    def updated_at(self) -> Optional[datetime]:
        if not self._user.is_member:
            return None
        v = self._data.get("updated_at")
        return dateutil.parser.parse(v) if v else None

    @classmethod
    async def get_by_id(
        cls: Type[T], id: str, user: BaseUser, auth: AuthCredentials
    ) -> Optional[T]:
        with (await services.redis_pool) as r:
            du = await r.get("planetsclub-user-" + id)

        u: Optional[T] = None
        if du:
            u = cls(id, msgpack.loads(du, raw=False), user=user, auth=auth)
        else:
            u = await super()._es_get(id, user, auth)
            if u:
                with (await services.redis_pool) as r:
                    await r.setex(
                        "planetsclub-user-" + id, 30, msgpack.dumps(u.asdict())
                    )

        return u

    @classmethod
    async def get_by_facebook_access_token(
        cls: Type[T], access_token: str
    ) -> Tuple[Optional[T], Optional[str]]:
        # Get user profile
        resp = await services.http_session.get(
            FBAPI_BASE + "/me",
            params={"access_token": access_token, "fields": "id,name,picture,groups"},
        )

        me = await resp.json()
        if "id" not in me:
            return (None, "INVALID_TOKEN")

        resp = await services.http_session.get(
            FBAPI_GROUP_BASE + "/feed",
            params={"access_token": access_token, "limit": 1},
        )
        pc = await resp.json()
        if "error" in pc:
            return (None, "NOT_PC_MEMBER")

        user = await cls.get_by_id(me["id"], UnauthenticatedUser(), AuthCredentials())

        # ES上に存在しない場合はユーザを生成する
        if not user:
            user = cls(id=me["id"], user=None, auth=None)

        await user._es_update(
            {"real_name": me["name"], "picture_uri": me["picture"]["data"]["url"]},
            doc_as_upsert=True,
        )

        return (user, None)

    @classmethod
    async def get_users(
        cls: Type[T],
        user: BaseUser,
        auth: AuthCredentials,
        q=None,
        include_deactivated=False,
        first=None,
        last=None,
        after=None,
        before=None,
    ):
        if not user.is_member:
            return None

        must: List[Dict] = []
        must_not: List[Dict] = []

        if q:
            must.append({"query_string": {"query": q, "default_operator": "AND"}})

        if not user.is_authenticated:
            must_not.append({"match_all": {}})
        elif not user.is_member:
            must.append({"term": {"_id": user.id}})

        if not include_deactivated:
            must_not.append({"term": {"deactivated": True}})

        return await UserModel._es_search_pagable(
            user,
            auth,
            query={"bool": {"must": must, "must_not": must_not}},
            sort=[{"_id": "desc"}],
            first=first,
            last=last,
            after=after,
            before=before,
        )

    async def deactivate(self: T) -> bool:
        if not self._user.is_admin:
            return False

        await self._es_update({"deactivated": True})
        return True

    async def activate(self: T) -> bool:
        if not self._user.is_admin:
            return False

        await self._es_update({"deactivated": False})
        return True

    async def change_admin_state(self, state: bool) -> bool:
        if not self._user.is_admin:
            return False

        await self._es_update({"is_admin": state})
        return True

    async def _es_update(self, update, *args, **kwargs):
        with (await services.redis_pool) as r:
            await r.delete("planetsclub-user-" + self._id)
        update["updated_at"] = datetime.now(UTC)
        return await super()._es_update(update, *args, **kwargs)

    async def _es_index(self):
        self._data["created_at"] = datetime.now(UTC)
        return await super()._es_index()


class AuthenticationBackend:
    async def load(self, request, auth_data):
        if auth_data:
            _id = auth_data.get("sub")
            scopes = auth_data.get("scope")
            if _id and (scopes is not None):
                user = await UserModel.get_by_id(
                    _id, UnauthenticatedUser(), AuthCredentials()
                )
                if user and user.is_active:
                    auth = AuthCredentials(scopes)
                    user.authenticate(auth, user)
                    return (auth, user)

        return (AuthCredentials(), UnauthenticatedUser())

    async def dump(self, request, auth, user):
        if isinstance(user, UserModel):
            # exp = datetime.now(UTC) + timedelta(days=7)
            return {"sub": user.id, "scope": auth.scopes}  # , "exp": exp}
        else:
            return None
