"""Planets Club Archive"""

import re
from datetime import datetime
from enum import Enum
from typing import List, Optional, Type, TypeVar

from dateutil.parser import parse as parse_datetime
from pytz import UTC
from starlette.authentication import AuthCredentials

from planetsclub.services.elasticsearch import ESDocModel, NotFoundError
from planetsclub.users.base import BaseUser
from planetsclub.users.models import UserModel

T = TypeVar("T", bound="ArchiveModel")


class ArchiveItemPrivacy(Enum):
    PUBLIC = "public"
    CLUB = "club"


class ArchiveModel(ESDocModel):
    ES_INDEX = "planets-archive"

    @property
    def title(self) -> str:
        return self._data.get("title") or "Untitled"

    @property
    def type(self) -> str:
        return self._data.get("type") or "unknown"

    @property
    def description(self) -> str:
        return self._data.get("description", "")

    @property
    def privacy(self) -> ArchiveItemPrivacy:
        v = self._data.get("privacy", None)
        return ArchiveItemPrivacy(v) if v else ArchiveItemPrivacy.CLUB

    @property
    def series(self) -> str:
        return self._data.get("series", "")

    @property
    def thumbnail_url(self) -> str:
        return self._data.get("thumbnail_url", "")

    @property
    def source(self) -> str:
        return self._data.get("source", "")

    @property
    def length(self) -> Optional[int]:
        return self._data.get("length")

    @property
    def tags(self) -> List[str]:
        return self._data.get("tags") or []

    @property
    def source_id(self) -> str:
        return self._data.get("source_id", "")

    @property
    def body_highlights(self) -> List[str]:
        return self._highlight.get("body", []) if self._highlight else []

    @property
    def body(self) -> Optional[str]:
        return self._data.get("body")

    @property
    def html_content(self) -> Optional[str]:
        if self._user.is_member:
            return self._data.get("html_content")
        else:
            return None

    @property
    def published_at(self) -> Optional[datetime]:
        v = self._data.get("published_at")
        return parse_datetime(v) if v else None

    @property
    def created_at(self) -> Optional[datetime]:
        v = self._data.get("created_at")
        return parse_datetime(v) if v else None

    @property
    def updated_at(self) -> Optional[datetime]:
        v = self._data.get("updated_at")
        return parse_datetime(v) if v else None

    async def get_created_by(self) -> Optional[UserModel]:
        if not self._user.is_member:
            return None
        uid: Optional[str] = self._data.get("created_by")
        if uid:
            return await UserModel.get_by_id(uid, self._user, self._auth)
        else:
            return None

    async def get_updated_by(self) -> Optional[UserModel]:
        if not self._user.is_member:
            return None
        uid: Optional[str] = self._data.get("updated_by")
        print(uid)
        if uid:
            return await UserModel.get_by_id(uid, self._user, self._auth)
        else:
            return None

    @classmethod
    async def get_by_id(
        cls: Type[T], id, user: BaseUser, auth: AuthCredentials
    ) -> Optional[T]:
        model = await cls._es_get(id, user, auth)
        return model

    @classmethod
    async def get_archives(
        cls: Type[T],
        user: BaseUser,
        auth: AuthCredentials,
        sort=None,
        q=None,
        state=None,
        phase=None,
        first=None,
        last=None,
        after=None,
        before=None,
    ):
        must = []
        sort = sort or []
        sort = sort + [{"_id": "desc"}]

        if not user.is_member:
            must.append({"term": {"privacy": "public"}})

        if q:
            must.append({"query_string": {"query": q, "default_operator": "AND"}})

        return await cls._es_search_pagable(
            user,
            auth,
            query={"bool": {"must": must}},
            sort=sort,
            first=first,
            last=last,
            before=before,
            after=after,
            highlight={
                "fields": {"*": {}},
                "fragment_size": 60,
                "number_of_fragments": 3,
            },
            _source={"excludes": ["body", "html_content"]},
        )

    @classmethod
    async def create(cls: Type[T], user: BaseUser, auth, data: dict) -> Optional[T]:
        raise NotImplementedError

    @classmethod
    async def update(cls: Type[T], id, user: BaseUser, auth, data: dict) -> Optional[T]:
        if not user.is_member:
            return None

        if "body" in data:
            data["description"] = re.sub(r"\s+", "", data["body"])[:200]

        alert = cls(id, user=user, auth=auth)
        data["updated_at"] = datetime.now(UTC)
        data["updated_by"] = user.id
        try:
            await alert._es_update(data)
            return alert
        except NotFoundError:
            return None

    @classmethod
    async def delete(cls: Type[T], id, user: BaseUser, auth) -> bool:
        raise NotImplementedError
