"""Elasticsearch"""

import base64
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Sequence, Type, TypeVar

import msgpack
from elasticsearch import NotFoundError
from starlette.authentication import AuthCredentials

from planetsclub.services import services
from planetsclub.users.base import BaseUser, UnauthenticatedUser

_LOGGER = logging.getLogger("planetsclub.services.elasticsearch")


T = TypeVar("T", bound="ESDocModel")


def _sort_to_cursor(values) -> str:
    return base64.urlsafe_b64encode(msgpack.dumps(values)).decode("ascii").rstrip("=")


def _cursor_to_sort(cursor: str):
    try:
        c = cursor.encode("ascii")
        c += b"=" * (4 - len(c) % 4)
        s = base64.urlsafe_b64decode(c)
        return msgpack.loads(s, raw=False)
    except ValueError:
        return None


def _reversed_sort_spec(sort):
    r = []
    for s in sort:
        if isinstance(s, dict):
            s = deepcopy(s)
            for key in s:
                if isinstance(s[key], dict):
                    d = s[key]
                    # order
                    odr = d.get("order", "desc" if (key == "_score") else "asc")
                    d["order"] = "desc" if odr == "asc" else "asc"
                    # missing
                    missing = d.get("missing", "_last")
                    d["missing"] = "_first" if missing == "_last" else "_last"
                else:
                    s[key] = "desc" if s[key] == "asc" else "asc"
            r.append(s)
        elif isinstance(s, str):
            r.append(
                {s: {"order": "asc" if s == "_score" else "desc", "missing": "_first"}}
            )
        else:
            raise RuntimeError("invalid sort criteria")
    return r


class ESDocModel:
    ES_INDEX = ""
    _id: Optional[str]
    _data: Dict[str, Any]
    _inner_hits: Optional[dict]
    _highlight: Optional[Dict[str, List]]
    _user: BaseUser
    _auth: AuthCredentials

    def __init__(
        self,
        id: Optional[str] = None,
        data: Optional[dict] = None,
        inner_hits: Optional[dict] = None,
        highlight: Optional[dict] = None,
        user: Optional[BaseUser] = None,
        auth: Optional[AuthCredentials] = None,
    ):
        self._id = id
        self._data = data or {}
        self._inner_hits = inner_hits
        self._highlight = highlight
        self._user = user or UnauthenticatedUser()
        self._auth = auth or AuthCredentials()

    def __str__(self):
        return "<ESDocModel({}) id={}>".format(self.ES_INDEX, self._id)

    @property
    def id(self) -> Optional[str]:
        return self._id

    def asdict(self) -> dict:
        if self._data:
            return deepcopy(self._data)
        else:
            return {}

    def authenticate(self, auth, user):
        self._auth = auth
        self._user = user

    @classmethod
    async def _es_get(
        cls: Type[T],
        id: str,
        user: Optional[BaseUser],
        auth: Optional[AuthCredentials],
        **kwargs
    ) -> Optional[T]:
        try:
            res = await services.es.get(index=cls.ES_INDEX, id=id, **kwargs)
        except NotFoundError:
            return None
        return cls(res["_id"], data=res["_source"], user=user, auth=auth)

    @classmethod
    async def _es_mget(
        cls,
        ids: Sequence[str],
        user: Optional[BaseUser],
        auth: Optional[AuthCredentials],
        **kwargs
    ):
        if not isinstance(ids, list):
            ids = list(ids)
        if not ids:
            return []
        res = await services.es.mget(index=cls.ES_INDEX, body={"ids": ids}, **kwargs)
        return [
            cls(doc["_id"], data=doc["_source"], user=user, auth=auth)
            for doc in res["docs"]
            if doc["found"]
        ]

    @classmethod
    async def _es_search_raw(cls, body: dict, **kwargs):
        return await services.es.search(index=cls.ES_INDEX, body=body, **kwargs)

    @classmethod
    async def _es_search_pagable(
        cls: Type[T],
        user: Optional[BaseUser],
        auth: Optional[AuthCredentials],
        query: Optional[dict],
        sort,
        first: Optional[int],
        last: Optional[int],
        after: Optional[str],
        before: Optional[str],
        highlight=None,
        _source=None,
    ):
        es = services.es
        if sort is None:
            sort = [{"_id": "desc"}]

        (reverse_order, size) = (False, first or 10)
        if first is not None and after:
            (reverse_order, size) = (False, first)
        elif last is not None and before:
            (reverse_order, size) = (True, last)

        if size > 2000:
            size = 2000

        if reverse_order:
            sort = _reversed_sort_spec(sort)

        body = {"size": size + 1, "query": query, "sort": sort}
        if not reverse_order and after:
            search_after = _cursor_to_sort(after)
            if len(sort) == len(search_after):
                body["search_after"] = search_after
        elif reverse_order and before:
            search_after = _cursor_to_sort(before)
            if len(sort) == len(search_after):
                body["search_after"] = search_after

        if highlight:
            body["highlight"] = highlight
        if _source:
            body["_source"] = _source

        search_meta = {"index": cls.ES_INDEX}
        msearch_body = [search_meta, body]

        nextprev: Optional[str] = None
        pagable: Dict[str, Any] = {}
        if not reverse_order:
            if after is None:
                pagable["has_previous_page"] = False
            else:
                nextprev = "has_previous_page"
        else:
            if before is None:
                pagable["has_next_page"] = False
            else:
                nextprev = "has_next_page"

        if nextprev:
            msearch_body.extend(
                [
                    search_meta,
                    {"_source": False, "size": 1, "query": query, "sort": sort},
                ]
            )

        # wait tasks
        msearch_res = await es.msearch(body=msearch_body)
        res = msearch_res["responses"][0]
        total = res["hits"]["total"]
        total_count = total["value"]
        total_rel = total["relation"]
        hits = res["hits"]["hits"]

        if not reverse_order:
            if len(hits) > size:
                pagable["has_next_page"] = True
                hits = hits[:size]
            else:
                pagable["has_next_page"] = False
        else:
            if len(hits) > size:
                pagable["has_previous_page"] = True
                hits = hits[:size]
            else:
                pagable["has_previous_page"] = False

        if nextprev:
            nextprev_res = msearch_res["responses"][1]["hits"]["hits"]
            initial = nextprev_res[0] if nextprev_res else None
            pagable[nextprev] = bool(
                initial and len(hits) and initial["sort"] != hits[0]["sort"]
            )

        if reverse_order:
            hits.reverse()

        if hits:
            pagable["start_cursor"] = _sort_to_cursor(hits[0]["sort"])
            pagable["end_cursor"] = _sort_to_cursor(hits[-1]["sort"])

        pagable["total_count"] = total_count
        pagable["total_count_rel"] = total_rel
        pagable["items"] = [
            cls(
                hit["_id"],
                data=hit["_source"],
                inner_hits=hit.get("inner_hits"),
                highlight=hit.get("highlight"),
                user=user,
                auth=auth,
            )
            for hit in hits
        ]
        return pagable

    async def _es_index(self, update=True, upsert=False, refresh=False, **kwargs):
        res = await services.es.index(
            index=self.ES_INDEX, id=self._id, refresh=refresh, body=self._data, **kwargs
        )
        self._id = res["_id"]

    async def _es_update(
        self, update, refresh: Optional[bool] = None, doc_as_upsert=False, **kwargs
    ):
        if self._id is None:
            raise RuntimeError("This document doesn't have an id")

        if "_source" not in kwargs:
            kwargs["_source"] = True

        body = {"doc": update}
        if doc_as_upsert:
            body["doc_as_upsert"] = True

        res = await services.es.update(
            index=self.ES_INDEX, id=self._id, refresh=refresh, body=body, **kwargs
        )
        self._id = res["_id"]
        if kwargs["_source"]:
            self._data.update(res["get"]["_source"])

    async def _es_delete(self, refresh=False):
        await services.es.delete(index=self.ES_INDEX, id=self._id, refresh=refresh)
