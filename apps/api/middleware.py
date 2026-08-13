from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.urls import reverse
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.api.authentication import is_token_blacklisted, set_auth_cookies
from apps.api.services.auth_service import AuthService

# Not ours to gate: Django admin has its own session auth, static/media are assets,
# and /api/auth/* manages the cookies directly — a preemptive refresh here would
# rotate the refresh token out from under RefreshView before it gets to use it.
NOT_PROCESSED_PREFIXES = ("/admin/", "/static/", "/media/", "/api/auth/")

# Processed (request.user gets resolved/refreshed here too, for the header's
# login/logout link and so /api/ sees a fresh cookie — see below) but NEVER
# redirected to /login/ on failure: public pages, the login page itself, and
# /api/ — a fetch() call must get DRF's own 401 JSON, never an HTML redirect.
NEVER_REDIRECT_EXACT = {"/"}
NEVER_REDIRECT_PREFIXES = ("/como-funciona/", "/como-operan/", "/login/", "/api/")


def is_processed(path):
    return not path.startswith(NOT_PROCESSED_PREFIXES)


def is_redirect_exempt(path):
    return path in NEVER_REDIRECT_EXACT or path.startswith(NEVER_REDIRECT_PREFIXES)


def user_from_access_token(raw_token):
    if not raw_token:
        return None
    try:
        validated = AccessToken(raw_token)
        if is_token_blacklisted(validated["jti"]):
            return None
        return get_user_model().objects.get(pk=validated["user_id"])
    except (TokenError, KeyError, get_user_model().DoesNotExist):
        return None


class JWTPageAuthMiddleware:
    """Gates plain Django template views with the same access/refresh cookie pair
    set at /api/auth/login/ — and transparently refreshes an expired access token
    using the refresh cookie so a live demo session never gets interrupted, on
    pages AND on /api/ calls, instead of forcing a re-login mid-use.

    Runs BEFORE the DRF view, so when it refreshes it patches request.COOKIES in
    place for this same request — CookieJWTAuthentication re-reads that cookie
    independently and would otherwise still see the stale, expired token.

    Only page routes actually redirect to /login/ on failure. /api/ always falls
    through to DRF's own IsAuthenticated check, which returns a proper 401 JSON
    body — a fetch() call getting an HTML redirect instead would just break silently.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.service = AuthService()

    def __call__(self, request):
        user = None
        refreshed_tokens = None

        if is_processed(request.path):
            user = user_from_access_token(request.COOKIES.get(settings.JWT_ACCESS_COOKIE))

            if user is None:
                refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE)
                if refresh_token:
                    try:
                        new_access, new_refresh = self.service.refresh(refresh_token=refresh_token)
                    except AuthenticationFailed:
                        new_access = None
                    if new_access:
                        candidate = user_from_access_token(new_access)
                        if candidate is not None:
                            user = candidate
                            refreshed_tokens = (new_access, new_refresh)
                            # Same request, not just the next one: DRF's
                            # CookieJWTAuthentication reads request.COOKIES itself.
                            request.COOKIES = {**request.COOKIES, settings.JWT_ACCESS_COOKIE: new_access}

            if user is not None:
                request.user = user
            elif not is_redirect_exempt(request.path):
                login_url = f"{reverse('login-page')}?{urlencode({'next': request.get_full_path()})}"
                return HttpResponseRedirect(login_url)

        response = self.get_response(request)

        if refreshed_tokens is not None:
            set_auth_cookies(response, access_token=refreshed_tokens[0], refresh_token=refreshed_tokens[1])

        return response
