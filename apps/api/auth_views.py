from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.authentication import clear_auth_cookies, set_auth_cookies
from apps.api.serializers import LoginSerializer
from apps.api.services.auth_service import AuthService


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = AuthService()

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Caught by hand, not left to propagate: with authentication_classes = []
        # DRF has no WWW-Authenticate header to offer, so its default exception
        # handler silently rewrites AuthenticationFailed's 401 into a 403.
        try:
            user, access, refresh = self.service.login(**serializer.validated_data)
        except AuthenticationFailed as exc:
            return Response({"detail": str(exc.detail)}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response({"username": user.get_username()}, status=status.HTTP_200_OK)
        set_auth_cookies(response, access_token=access, refresh_token=refresh)
        return response


class LogoutView(APIView):
    # Debe funcionar aunque el access token ya haya expirado — su único trabajo
    # es invalidar el refresh token, no depender de que el access siga vigente.
    permission_classes = [AllowAny]
    authentication_classes = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = AuthService()

    def post(self, request):
        access_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE)
        refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE)
        self.service.logout(access_token=access_token, refresh_token=refresh_token)

        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = AuthService()

    def post(self, request):
        refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE)
        try:
            access, new_refresh = self.service.refresh(refresh_token=refresh_token)
        except AuthenticationFailed as exc:
            return Response({"detail": str(exc.detail)}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response(status=status.HTTP_200_OK)
        set_auth_cookies(response, access_token=access, refresh_token=new_refresh)
        return response
