from typing import Dict, List, Optional

from ariadne import MutationType, QueryType, SchemaBindable
from starlette.authentication import AuthCredentials

from planetsclub.users.models import UserModel

query = QueryType()
mutation = MutationType()


def ensure_user_cache(request):
    state = request.state
    if not hasattr(state, "user_cache"):
        state.user_cache = {}
    return state.user_cache


async def _user_from_info(info, id) -> Optional[UserModel]:
    request = info.context["request"]
    user = await UserModel.get_by_id(id, request.user, request.auth)
    return user


@query.field("me")
def resolve_me(_, info) -> UserModel:
    request = info.context["request"]
    return request.user


@query.field("user")
async def resolve_user(_, info, id) -> Optional[UserModel]:
    return await _user_from_info(info, id)


@query.field("users")
async def resolve_users(_, info, **kwargs):
    kwargs["include_deactivated"] = kwargs.pop("includeDeactivated", False)
    request = info.context["request"]
    return await UserModel.get_users(request.user, request.auth, **kwargs)


@mutation.field("signInWithFacebook")
async def resolve_signin_with_google(_, info, accessToken) -> Dict:
    request = info.context["request"]
    (user, error) = await UserModel.get_by_facebook_access_token(accessToken)
    if error is not None:
        return {"user": None, "error": error}

    assert isinstance(user, UserModel)
    auth = AuthCredentials(["authenticated"])
    user.authenticate(auth, user)
    request["auth_cookie"].set(auth, user)
    return {"user": user, "error": None}


@mutation.field("deactivateUser")
async def resolve_deactivate_user(_, info, id) -> Optional[UserModel]:
    user = await _user_from_info(info, id)
    if user and await user.deactivate():
        return user
    else:
        return None


@mutation.field("activateUser")
async def resolve_activate_user(_, info, id) -> Optional[UserModel]:
    user = await _user_from_info(info, id)
    return user if (user and await user.activate()) else None


@mutation.field("addAdminRole")
async def resolve_add_admin_role(_, info, id) -> Optional[UserModel]:
    user = await _user_from_info(info, id)
    if user and await user.change_admin_state(True):
        return user
    else:
        return None


@mutation.field("removeAdminRole")
async def resolve_remove_admin_role(_, info, id) -> Optional[UserModel]:
    user = await _user_from_info(info, id)
    if user and await user.change_admin_state(False):
        return user
    else:
        return None


@mutation.field("signOut")
async def resolve_sign_out(_, info) -> bool:
    info.context["request"]["auth_cookie"].delete()
    return True


resolvers: List[SchemaBindable] = []
resolvers.extend([query, mutation])
