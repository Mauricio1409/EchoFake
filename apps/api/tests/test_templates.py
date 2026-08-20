from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken


class PublicPageTests(TestCase):
    """Home, how-it-works and how-attackers stay reachable without logging in."""

    def test_home_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "api/home.html")

    def test_home_does_not_claim_blanket_deletion(self):
        response = self.client.get("/")
        self.assertContains(response, "se borran o se revocan al terminar la demo")
        self.assertNotContains(response, "se borran al terminar la demo")

    def test_how_it_works_renders_without_login(self):
        response = self.client.get("/como-funciona/")
        self.assertEqual(response.status_code, 200)

    def test_how_attackers_renders_without_login(self):
        response = self.client.get("/como-operan/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "api/how-attackers.html")

    def test_login_page_renders_without_login(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "api/login.html")

    def test_home_nav_hides_protected_links_when_logged_out(self):
        response = self.client.get("/")
        self.assertContains(response, 'href="/login/"')
        self.assertNotContains(response, 'href="/nuevo/"')
        self.assertNotContains(response, 'href="/sujetos/"')

    def test_home_hides_create_and_list_ctas_when_logged_out(self):
        response = self.client.get("/")
        self.assertNotContains(response, "Generar un caso")
        self.assertNotContains(response, "Ver casos generados")
        self.assertContains(response, "Iniciar sesión")

    def test_how_it_works_hides_protected_ctas_when_logged_out(self):
        response = self.client.get("/como-funciona/")
        self.assertNotContains(response, "Probar la demo")
        self.assertNotContains(response, "Ver casos generados")
        self.assertContains(response, "Iniciar sesión")

    def test_how_attackers_hides_protected_cta_when_logged_out(self):
        response = self.client.get("/como-operan/")
        self.assertNotContains(response, "Probar la demo")
        self.assertContains(response, "Ver cómo funciona la tecnología")
        self.assertContains(response, "Iniciar sesión")


class ProtectedPageRedirectsWithoutLoginTests(TestCase):
    """Everything else ('el resto de partes') bounces to /login/ when logged out."""

    def test_create_choice_redirects_to_login(self):
        response = self.client.get("/nuevo/")
        self.assertRedirects(response, "/login/?next=/nuevo/", fetch_redirect_response=False)

    def test_create_manual_redirects_to_login(self):
        response = self.client.get("/nuevo/manual/")
        self.assertRedirects(response, "/login/?next=/nuevo/manual/", fetch_redirect_response=False)

    def test_create_auto_redirects_to_login(self):
        response = self.client.get("/nuevo/automatico/")
        self.assertRedirects(response, "/login/?next=/nuevo/automatico/", fetch_redirect_response=False)

    def test_subject_list_redirects_to_login(self):
        response = self.client.get("/sujetos/")
        self.assertRedirects(response, "/login/?next=/sujetos/", fetch_redirect_response=False)

    def test_panel_redirects_to_login(self):
        response = self.client.get("/panel/00000000-0000-0000-0000-000000000000/")
        self.assertRedirects(
            response,
            "/login/?next=/panel/00000000-0000-0000-0000-000000000000/",
            fetch_redirect_response=False,
        )

    def test_api_without_credentials_returns_401_json_not_a_redirect(self):
        # A fetch() call getting an HTML redirect instead of JSON would break silently.
        response = self.client.get("/api/subjects/")
        self.assertEqual(response.status_code, 401)


class ProtectedPageTests(TestCase):
    """Same pages, but reachable once the JWT access cookie is set (as /login/ does)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador", password="pass12345")
        access = str(RefreshToken.for_user(self.user).access_token)
        self.client.cookies[settings.JWT_ACCESS_COOKIE] = access

    def test_panel_renders(self):
        response = self.client.get("/panel/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "api/panel.html")

    def test_panel_has_no_gesture_button(self):
        response = self.client.get("/panel/00000000-0000-0000-0000-000000000000/")
        self.assertNotContains(response, 'data-job-type="gesture"')

    def test_panel_has_purge_button(self):
        response = self.client.get("/panel/00000000-0000-0000-0000-000000000000/")
        self.assertContains(response, 'id="purge-btn"')

    def test_panel_has_generate_card_markup_for_auto_mode_toggle(self):
        # mode=auto hiding is client-side JS; this just guards the id it targets exists.
        response = self.client.get("/panel/00000000-0000-0000-0000-000000000000/")
        self.assertContains(response, 'id="generate-card"')

    def test_create_choice_renders(self):
        response = self.client.get("/nuevo/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "api/create-choice.html")

    def test_create_manual_renders(self):
        response = self.client.get("/nuevo/manual/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "api/create-manual.html")

    def test_create_auto_renders(self):
        response = self.client.get("/nuevo/automatico/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "api/create-auto.html")

    def test_subject_list_renders(self):
        response = self.client.get("/sujetos/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "api/list.html")

    def test_header_shows_logout_once_logged_in(self):
        response = self.client.get("/sujetos/")
        self.assertContains(response, 'id="logout-btn"')

    def test_home_nav_shows_protected_links_once_logged_in(self):
        response = self.client.get("/")
        self.assertContains(response, 'href="/nuevo/"')
        self.assertContains(response, 'href="/sujetos/"')

    def test_home_shows_create_and_list_ctas_once_logged_in(self):
        response = self.client.get("/")
        self.assertContains(response, "Generar un caso")
        self.assertContains(response, "Ver casos generados")

    def test_how_it_works_shows_protected_ctas_once_logged_in(self):
        response = self.client.get("/como-funciona/")
        self.assertContains(response, "Probar la demo")
        self.assertContains(response, "Ver casos generados")

    def test_how_attackers_shows_protected_cta_once_logged_in(self):
        response = self.client.get("/como-operan/")
        self.assertContains(response, "Probar la demo")
