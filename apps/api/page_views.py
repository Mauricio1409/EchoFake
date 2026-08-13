from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from rest_framework.exceptions import AuthenticationFailed

from apps.api.authentication import set_auth_cookies
from apps.api.services.auth_service import AuthService


class LoginPageView(View):
    template_name = "api/login.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = AuthService()

    def get(self, request):
        return render(request, self.template_name, {"next": request.GET.get("next", "")})

    def post(self, request):
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        next_url = request.POST.get("next") or reverse("subject-list")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = reverse("subject-list")

        try:
            user, access, refresh = self.service.login(username=username, password=password)
        except AuthenticationFailed as exc:
            return render(
                request,
                self.template_name,
                {"error": str(exc.detail), "next": next_url, "username": username},
                status=401,
            )

        response = HttpResponseRedirect(next_url)
        set_auth_cookies(response, access_token=access, refresh_token=refresh)
        return response
