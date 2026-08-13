from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken


def expired_access_token_for(user):
    token = AccessToken.for_user(user)
    token.set_exp(lifetime=timedelta(seconds=-1))
    return str(token)


class LoginViewTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador", password="pass12345")

    def test_login_success_sets_httponly_cookies(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "operador", "password": "pass12345"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        access_cookie = response.cookies[settings.JWT_ACCESS_COOKIE]
        refresh_cookie = response.cookies[settings.JWT_REFRESH_COOKIE]
        self.assertTrue(access_cookie["httponly"])
        self.assertTrue(refresh_cookie["httponly"])
        self.assertEqual(access_cookie["samesite"], settings.JWT_COOKIE_SAMESITE)

    def test_login_wrong_password_returns_401_and_sets_no_cookies(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "operador", "password": "wrong"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn(settings.JWT_ACCESS_COOKIE, response.cookies)

    def test_login_unknown_user_returns_401(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "ghost", "password": "whatever"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logged_in_cookie_authenticates_subsequent_api_calls(self):
        self.client.post(
            "/api/auth/login/",
            {"username": "operador", "password": "pass12345"},
            format="json",
        )

        response = self.client.get("/api/subjects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class LogoutViewTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador", password="pass12345")
        self.client.post(
            "/api/auth/login/",
            {"username": "operador", "password": "pass12345"},
            format="json",
        )

    def test_logout_clears_cookies(self):
        response = self.client.post("/api/auth/logout/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.cookies[settings.JWT_ACCESS_COOKIE].value, "")
        self.assertEqual(response.cookies[settings.JWT_REFRESH_COOKIE].value, "")

    def test_logout_blacklists_refresh_token(self):
        refresh_token = self.client.cookies[settings.JWT_REFRESH_COOKIE].value

        self.client.post("/api/auth/logout/")

        refresh_response = self.client.post("/api/auth/refresh/")
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)
        with self.assertRaises(Exception):
            RefreshToken(refresh_token).blacklist()  # already blacklisted -> TokenError

    def test_logout_blacklists_access_token_immediately(self):
        access_token = self.client.cookies[settings.JWT_ACCESS_COOKIE].value

        self.client.post("/api/auth/logout/")

        payload = AccessToken(access_token)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=payload["jti"]).exists())

    def test_api_call_rejected_right_after_logout_even_with_still_valid_access_cookie(self):
        # Re-attach the (now blacklisted) access cookie by hand, simulating a
        # browser tab that hasn't cleared it yet.
        access_token = self.client.cookies[settings.JWT_ACCESS_COOKIE].value
        self.client.post("/api/auth/logout/")
        self.client.cookies[settings.JWT_ACCESS_COOKIE] = access_token

        response = self.client.get("/api/subjects/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_without_any_cookie_still_succeeds(self):
        self.client.cookies.clear()

        response = self.client.post("/api/auth/logout/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class RefreshViewTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador", password="pass12345")

    def test_refresh_with_valid_refresh_cookie_issues_new_access_cookie(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies[settings.JWT_REFRESH_COOKIE] = str(refresh)

        response = self.client.post("/api/auth/refresh/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(settings.JWT_ACCESS_COOKIE, response.cookies)

    def test_refresh_without_cookie_returns_401(self):
        response = self.client.post("/api/auth/refresh/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_with_garbage_token_returns_401(self):
        self.client.cookies[settings.JWT_REFRESH_COOKIE] = "not-a-real-token"

        response = self.client.post("/api/auth/refresh/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TransparentRefreshMiddlewareTests(TestCase):
    """The core "must not get kicked out mid-demo" behavior: an expired access
    cookie + a still-valid refresh cookie must silently keep working, on both
    page loads and /api/ calls, in the SAME request — not just the next one."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador", password="pass12345")

    def _set_expired_access_plus_valid_refresh(self):
        self.client.cookies[settings.JWT_ACCESS_COOKIE] = expired_access_token_for(self.user)
        self.client.cookies[settings.JWT_REFRESH_COOKIE] = str(RefreshToken.for_user(self.user))

    def test_protected_page_silently_refreshes_instead_of_redirecting(self):
        self._set_expired_access_plus_valid_refresh()

        response = self.client.get("/sujetos/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.JWT_ACCESS_COOKIE, response.cookies)

    def test_api_call_silently_refreshes_within_the_same_request(self):
        self._set_expired_access_plus_valid_refresh()

        response = self.client.get("/api/subjects/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.JWT_ACCESS_COOKIE, response.cookies)

    def test_refresh_token_rotates_so_the_new_cookie_keeps_working(self):
        self._set_expired_access_plus_valid_refresh()
        old_refresh = self.client.cookies[settings.JWT_REFRESH_COOKIE].value

        response = self.client.get("/sujetos/")

        new_refresh = response.cookies[settings.JWT_REFRESH_COOKIE].value
        self.assertNotEqual(old_refresh, new_refresh)

    def test_both_tokens_expired_redirects_to_login_on_pages(self):
        self.client.cookies[settings.JWT_ACCESS_COOKIE] = expired_access_token_for(self.user)
        expired_refresh = RefreshToken.for_user(self.user)
        expired_refresh.set_exp(lifetime=timedelta(seconds=-1))
        self.client.cookies[settings.JWT_REFRESH_COOKIE] = str(expired_refresh)

        response = self.client.get("/sujetos/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/login/?next="))

    def test_both_tokens_expired_returns_401_json_on_api_not_a_redirect(self):
        self.client.cookies[settings.JWT_ACCESS_COOKIE] = expired_access_token_for(self.user)
        expired_refresh = RefreshToken.for_user(self.user)
        expired_refresh.set_exp(lifetime=timedelta(seconds=-1))
        self.client.cookies[settings.JWT_REFRESH_COOKIE] = str(expired_refresh)

        response = self.client.get("/api/subjects/")

        self.assertEqual(response.status_code, 401)
