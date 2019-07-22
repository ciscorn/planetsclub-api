from typing import List, Optional

from ariadne import EnumType, MutationType, ObjectType, QueryType, SchemaBindable

from planetsclub.archives.models import ArchiveItemPrivacy, ArchiveModel
from planetsclub.users.models import UserModel


def _get_request(info):
    return info.context["request"]


query = QueryType()
mutation = MutationType()
archiveItem = ObjectType("ArchiveItem")


def input_to_data(input) -> dict:
    body = input["body"].strip()
    data = {
        "title": input["title"].strip(),
        "type": input["type"],
        "body": body,
        "series": input["series"].strip(),
        "html_content": input["htmlContent"].strip(),
        "length": input.get("length"),
        "tags": input["tags"],
        "source": input["source"],
        "source_id": input["sourceId"].strip(),
        "thumbnail_url": input["thumbnailUrl"].strip(),
        "published_at": input["publishedAt"],
    }
    return data


@mutation.field("updateArchiveItem")
async def resolve_update_archive_item(_, info, id, input) -> Optional[ArchiveModel]:
    request = _get_request(info)
    (user, auth) = (request.user, request.auth)
    data = input_to_data(input)
    return await ArchiveModel.update(id, user, auth, data=data)


@query.field("archiveItem")
async def resolve_archive_item(_, info, id) -> Optional[ArchiveModel]:
    request = _get_request(info)
    alert = await ArchiveModel.get_by_id(id, request.user, request.auth)
    return alert


@query.field("archiveItems")
async def resolve_archive_items(_, info, **kwargs) -> str:
    request = _get_request(info)
    kwargs.setdefault("sort", [{"created_at": "desc"}])
    pagable = await ArchiveModel.get_archives(request.user, request.auth, **kwargs)
    return pagable


@archiveItem.field("updatedBy")
async def resolve_update_by(item: ArchiveModel, info) -> Optional[UserModel]:
    return await item.get_updated_by()


@archiveItem.field("createdBy")
async def resolve_created_by(item: ArchiveModel, info) -> Optional[UserModel]:
    return await item.get_created_by()


resolvers: List[SchemaBindable] = []
resolvers.extend(
    [query, mutation, archiveItem, EnumType("ArchiveItemPrivacy", ArchiveItemPrivacy)]
)
