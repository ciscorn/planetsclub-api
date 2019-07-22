"""Authentication Middleware"""

import jwt
from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection

from planetsclub import settings


class AuthCookieAction:
    def __init__(self):
        self.auth = None
        self.user = None
        self.action = "noop"

    def set(self, auth, user):
        self.auth = auth
        self.user = user
        self.action = "set"

    def delete(self):
        self.auth = None
        self.user = None
        self.action = "delete"


class AuthenticationMiddleware:
    def __init__(self, app, backend):
        self.app = app
        self.backend = backend
        self.cookie_name = "token"
        self.security_flags = "httponly; samesite=lax"

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ["http", "websocket"]:
            await self.app(scope, receive, send)
            return

        scope["auth_cookie"] = AuthCookieAction()

        request = HTTPConnection(scope)
        token = request.cookies.get(self.cookie_name)

        token_data = None
        if token is not None:
            try:
                token_data = jwt.decode(token, settings.SECRET_KEY)
            except jwt.InvalidTokenError:
                scope["auth_cookie"].delete()

        (auth, user) = await self.backend.load(request, token_data)
        scope["auth"] = auth
        scope["user"] = user

        async def sender(message):
            if message["type"] != "http.response.start":
                await send(message)
                return

            action = scope["auth_cookie"].action

            # FIXME: tokenの自動更新を実装してもよい（アクセスごとに更新するなど）
            # ただし、画像配信用エンドポイントなどがSet-Cookieを送出しないように注意すること

            if action == "noop":
                cookie_value = None
            elif action == "set":
                token_data = await self.backend.dump(
                    request, scope["auth_cookie"].auth, scope["auth_cookie"].user
                )
                if token_data:
                    token = jwt.encode(token_data, settings.SECRET_KEY).decode("ascii")
                    cookie_value = "{0}={1}; path=/; max-age={2}; {3}".format(
                        self.cookie_name, token, 30 * 24 * 60 * 60, self.security_flags
                    )
                else:
                    action = "delete"

            if action == "delete":
                cookie_value = "{0}={1}; {2}".format(
                    self.cookie_name,
                    "null; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT;",
                    self.security_flags,
                )

            if cookie_value:
                headers = MutableHeaders(scope=message)
                headers.append("Set-Cookie", cookie_value)

            await send(message)

        await self.app(scope, receive, sender)
