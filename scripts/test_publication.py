"""Small offline tests for publication dates; no build, Git or network calls."""
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from seo import Publication, reading_schema

SITE = 'https://example.test'
FIRST = '2026-01-02T08:00:00+00:00'
LATER = '2026-02-03T09:00:00+00:00'
IMPORT = '2025-12-01T06:00:00+00:00'
SOURCE = '2023-06-23'


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifest = Path(self.temp.name) / '.publication.json'

    def publication(self, now=FIRST, site=SITE):
        result = Publication(site, self.manifest)
        result.now = now
        return result

    def test_identical_consecutive_builds_keep_lastmod(self):
        first = self.publication()
        before = first.add('/library/example/', {'title': '示例', 'body': ['a', 'b']}, IMPORT)
        first.save(self.manifest)
        second = self.publication(LATER)
        after = second.add('/library/example/', {'body': ['a', 'b'], 'title': '示例'}, IMPORT)
        self.assertEqual(before, after)
        self.assertEqual(second.sitemap(), first.sitemap())
        self.assertEqual(after['modified'], FIRST)

    def test_content_change_updates_only_that_page(self):
        first = self.publication()
        first.add('/library/one/', {'text': 'one'}, IMPORT)
        first.add('/topics/evaluation/', {'text': 'topic'})
        first.save(self.manifest)
        second = self.publication(LATER)
        changed = second.add('/library/one/', {'text': 'edited'})
        same = second.add('/topics/evaluation/', {'text': 'topic'})
        self.assertEqual(changed['published'], IMPORT)
        self.assertEqual(changed['modified'], LATER)
        self.assertNotEqual(changed['hash'], first.pages[SITE + '/library/one/']['hash'])
        self.assertEqual(same, first.pages[SITE + '/topics/evaluation/'])

    def test_source_date_does_not_become_local_publication_date(self):
        publication = self.publication()
        dates = publication.add('/library/example/', {'date': SOURCE}, IMPORT)
        self.assertEqual(dates['published'], IMPORT)
        self.assertEqual(dates['modified'], FIRST)
        self.assertNotEqual(dates['published'], SOURCE)

    def test_existing_publication_date_survives_import_history_changes(self):
        first = self.publication()
        first.add('/library/example/', {'text': 'one'}, IMPORT)
        first.save(self.manifest)
        second = self.publication(LATER)
        dates = second.add('/library/example/', {'text': 'two'}, '2026-01-01T00:00:00+00:00')
        self.assertEqual(dates['published'], IMPORT)
        self.assertEqual(dates['modified'], LATER)

    def test_explicit_publication_date_overrides_previous_and_import_dates(self):
        first = self.publication()
        first.add('/articles/first/', {'text': 'one'}, IMPORT)
        first.save(self.manifest)
        second = self.publication(LATER)
        explicit = '2025-10-01T09:00:00+00:00'
        dates = second.add('/articles/first/', {'text': 'two'}, IMPORT, published_at=explicit)
        self.assertEqual(dates['published'], explicit)
        self.assertEqual(dates['modified'], LATER)

    def test_empty_blog_then_first_post_needs_no_special_case(self):
        first = self.publication()
        first.add('/', {'posts': []})
        first.save(self.manifest)
        self.assertEqual(set(first.pages), {SITE + '/'})
        second = self.publication(LATER)
        homepage = second.add('/', {'posts': ['first']})
        post = second.add('/articles/first/', {'title': 'First post'})
        self.assertEqual(homepage['published'], FIRST)
        self.assertEqual(homepage['modified'], LATER)
        self.assertEqual(post['published'], LATER)
        self.assertEqual(post['modified'], LATER)
        root = ET.fromstring(second.sitemap())
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        self.assertEqual({node.text for node in root.findall('s:url/s:loc', ns)}, set(second.pages))

    def test_manifest_from_other_site_is_not_reused(self):
        first = self.publication()
        first.add('/', {'title': 'same'}, IMPORT)
        first.save(self.manifest)
        second = self.publication(LATER, 'https://other.test')
        dates = second.add('/', {'title': 'same'})
        self.assertEqual(dates['published'], LATER)
        self.assertEqual(dates['modified'], LATER)

    def test_translation_schema_keeps_each_kind_of_source_date_separate(self):
        site = {'url': SITE, 'name': 'Editor'}
        article = {
            'path': '/library/example/', 'url': 'https://source.test/original',
            'original_title': 'Original title', 'title': '译文标题',
            'description': '文章描述', 'category': '基础与架构',
            'publisher': 'Source Publisher', 'date': SOURCE,
            'authors': [{'@type': 'Person', 'name': 'Source Author'}],
        }
        dates = self.publication().add(article['path'], article, IMPORT)
        for kind, field in [(None, 'datePublished'), ('last updated', 'dateModified'), ('PDF creation date', 'dateCreated')]:
            with self.subTest(kind=kind):
                schema = reading_schema(site, {**article, 'date_kind': kind}, dates)
                self.assertEqual(schema['datePublished'], IMPORT)
                self.assertEqual(schema['dateModified'], FIRST)
                source = schema['translationOfWork']
                self.assertEqual(source['url'], article['url'])
                self.assertEqual({key: source[key] for key in ('datePublished', 'dateModified', 'dateCreated') if key in source}, {field: SOURCE})
                self.assertEqual(schema['author'], article['authors'])
                self.assertEqual(source['author'], article['authors'])


if __name__ == '__main__':
    unittest.main()
