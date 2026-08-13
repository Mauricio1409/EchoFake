from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.utils import datetime_from_epoch


class AuthService:
    def login(self, *, username, password):
        user = authenticate(username=username, password=password)
        if user is None:
            raise AuthenticationFailed("Usuario o contraseña incorrectos.")

        refresh = RefreshToken.for_user(user)
        return user, str(refresh.access_token), str(refresh)

    def refresh(self, *, refresh_token):
        if not refresh_token:
            raise AuthenticationFailed("Falta la sesión para renovar.")

        serializer = TokenRefreshSerializer(data={"refresh": refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise AuthenticationFailed("La sesión expiró. Iniciá sesión de nuevo.") from exc

        validated = serializer.validated_data
        new_refresh = validated.get("refresh", refresh_token)
        return validated["access"], new_refresh

    def logout(self, *, access_token=None, refresh_token=None):
        """Best-effort: blacklisting an already-expired/missing/invalid token is a
        no-op, not a failure — logging out always succeeds from the user's side.

        Blacklists BOTH tokens: the refresh token via simplejwt's native
        RefreshToken.blacklist(), and the access token by hand — AccessToken has
        no BlacklistMixin (only Refresh/Sliding tokens do), so a still-valid access
        token would otherwise keep working for the rest of its lifetime after logout.
        """
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except TokenError:
                pass
        if access_token:
            self._blacklist_access_token(access_token)

    @staticmethod
    def _blacklist_access_token(raw_access_token):
        try:
            token = AccessToken(raw_access_token)
        except TokenError:
            return

        outstanding, _ = OutstandingToken.objects.get_or_create(
            jti=token["jti"],
            defaults={
                "user_id": token["user_id"],
                "token": str(token),
                "created_at": datetime_from_epoch(token["iat"]),
                "expires_at": datetime_from_epoch(token["exp"]),
            },
        )
        BlacklistedToken.objects.get_or_create(token=outstanding)
