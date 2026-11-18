from html.parser import HTMLParser
from tests.support import DatabaseCase


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = 0
        self.nested = False
        self.fieldsets = 0
        self.legends = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links += 1
        if tag == 'button' and self.links:
            self.nested = True
        if tag == 'fieldset':
            self.fieldsets += 1
        if tag == 'legend':
            self.legends += 1

    def handle_endtag(self, tag):
        if tag == 'a':
            self.links -= 1


class DesignTests(DatabaseCase):
    def test_navigation_has_single_controls_and_skip_target(self):
        for url in ('/', '/school/gel', '/school/gel/a-gel', '/school/gel/a-gel/algebra'):
            page = self.client.get(url)
            self.assertEqual(page.status_code, 200)
            parser = Controls()
            parser.feed(page.data.decode())
            self.assertFalse(parser.nested, url)
            self.assertIn(b'id="page-content" tabindex="-1"', page.data)
            self.assertIn(b'id="menu" hidden', page.data)
            self.assertIn(b'aria-expanded="false"', page.data)

    def test_quiz_choices_have_question_group_labels(self):
        page = self.client.get('/quiz/gel/a-gel/algebra/1')
        self.assertEqual(page.status_code, 200)
        parser = Controls()
        parser.feed(page.data.decode())
        self.assertGreater(parser.fieldsets, 0)
        self.assertEqual(parser.fieldsets, parser.legends)
