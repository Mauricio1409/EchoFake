from django.test import TestCase


class TemplateRenderingTests(TestCase):
    def test_home_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "api/home.html")

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

    def test_home_does_not_claim_blanket_deletion(self):
        response = self.client.get("/")
        self.assertContains(response, "se borran o se revocan al terminar la demo")
        self.assertNotContains(response, "se borran al terminar la demo")

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

    def test_how_attackers_renders(self):
        response = self.client.get("/como-operan/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "api/how-attackers.html")

    def test_panel_has_generate_card_markup_for_auto_mode_toggle(self):
        # mode=auto hiding is client-side JS; this just guards the id it targets exists.
        response = self.client.get("/panel/00000000-0000-0000-0000-000000000000/")
        self.assertContains(response, 'id="generate-card"')
