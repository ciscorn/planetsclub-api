"""GraphQL API resolvers"""

import logging

from ariadne import (
    load_schema_from_path,
    make_executable_schema,
    snake_case_fallback_resolvers,
)
from ariadne.asgi import GraphQL
from graphql.type import GraphQLSchema

from planetsclub import settings

from . import archives, common, users

_LOGGER = logging.getLogger("planetsclub.graphql")


def _make_executable_schema() -> GraphQLSchema:
    type_defs = load_schema_from_path("schema.graphql")
    resolvers = []
    resolvers.extend(common.resolvers)
    resolvers.extend(archives.resolvers)
    resolvers.extend(users.resolvers)
    resolvers.append(snake_case_fallback_resolvers)
    return make_executable_schema(type_defs, resolvers)


def setup(app) -> None:
    app.mount("/api/graphql", GraphQL(_make_executable_schema(), debug=settings.DEBUG))
