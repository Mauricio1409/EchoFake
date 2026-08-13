from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken


def is_token_blacklisted(jti):
    return BlacklistedToken.objects.filter(token__jti=jti).exists()


class CookieJWTAuthentication(JWTAuthentication):
    """Same JWTs as the header-based flow, just carried in an httpOnly cookie.

    Browsers attach cookies automatically on same-origin fetch() calls, so every
    existing fetch() in the templates authenticates for free — no Authorization
    header wiring needed across the site's vanilla JS.
    """

    def authenticate(self, request):
        raw_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        if is_token_blacklisted(validated_token["jti"]):
            raise AuthenticationFailed("La sesión fue cerrada.")

        return self.get_user(validated_token), validated_token


def set_auth_cookies(response, *, access_token, refresh_token):
    common = {
        "httponly": True,
        "secure": settings.JWT_COOKIE_SECURE,
        "samesite": settings.JWT_COOKIE_SAMESITE,
        "path": "/",
    }
    response.set_cookie(
        settings.JWT_ACCESS_COOKIE,
        access_token,
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        **common,
    )
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE,
        refresh_token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        **common,
    )


def clear_auth_cookies(response):
    response.delete_cookie(settings.JWT_ACCESS_COOKIE, path="/")
    response.delete_cookie(settings.JWT_REFRESH_COOKIE, path="/")
