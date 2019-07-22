import logging

from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.responses import PlainTextResponse

from . import graphql, settings
from .services import services
from .users.middleware import AuthenticationMiddleware
from .users.models import AuthenticationBackend

_LOGGER = logging.getLogger("planetsclub")

app = Starlette(debug=True)

services.setup(app)
app.add_middleware(AuthenticationMiddleware, backend=AuthenticationBackend())
graphql.setup(app)
