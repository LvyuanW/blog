"""Offline SEO gate for a completed build. Python standard library only.

Run after build.py: python3 scripts/verify_seo.py [--dist dist]
The publication manifest defines the indexable pages; no network requests occur.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITEMAP_NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2}))?$')
ELLIPSIS = re.compile(r'…|\.\.\.')


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.titles, self.canonicals, self.metadata = [], [], []
        self.links, self.ld = [], []
        self.h1 = 0
        self.in_head = self.in_title = self.in_ld = False
        self.buffer = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'head':
            self.in_head = True
        if tag == 'h1':
            self.h1 += 1
        if self.in_head and tag == 'title':
            self.in_title = True
            self.titles.append('')
        if self.in_head and tag == 'meta':
            self.metadata.append(attrs)
        if self.in_head and tag == 'link' and 'canonical' in attrs.get('rel', '').lower().split():
            self.canonicals.append(attrs.get('href', ''))
        if tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
            self.in_ld = True
            self.buffer = []
        for key in ('href', 'src', 'poster'):
            value = attrs.get(key, '')
            # Source-article URLs and relative citations are not site routes.
            if value.startswith('/') and not value.startswith('//'):
                self.links.append(value)

    def handle_endtag(self, tag):
        if tag == 'head':
            self.in_head = False
        if tag == 'title':
            self.in_title = False
        if tag == 'script' and self.in_ld:
            self.ld.append(''.join(self.buffer))
            self.in_ld = False

    def handle_data(self, value):
        if self.in_title:
            self.titles[-1] += value
        if self.in_ld:
            self.buffer.append(value)

    def meta(self, name):
        return [m.get('content', '') for m in self.metadata
                if m.get('name', m.get('property', '')).lower() == name]

    def noindex(self):
        return any(re.search(r'\b(noindex|none)\b', m.get('content', '').lower())
                   for m in self.metadata if m.get('name', '').lower() in ('robots', 'googlebot', 'bingbot'))


def local_file(dist, value):
    """Resolve a root-relative URL, ignoring query and fragment, without escaping dist."""
    path = unquote(urlsplit(value).path)
    target = (dist / path.lstrip('/')).resolve()
    if not target.is_relative_to(dist.resolve()):
        return None
    if target.is_dir() or path.endswith('/'):
        target /= 'index.html'
    return target if target.is_file() else None


def timestamp(value):
    if not isinstance(value, str) or not DATE.fullmatch(value):
        raise ValueError('expected an ISO date or timezone-qualified timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def types(node):
    value = node.get('@type', [])
    return {value} if isinstance(value, str) else set(value) if isinstance(value, list) and all(isinstance(x, str) for x in value) else set()


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def verify(dist, root=ROOT):
    dist, root = Path(dist), Path(root)
    errors, parsed = [], {}
    def fail(where, message):
        errors.append(f'{where}: {message}')
    try:
        manifest = json.loads((dist / '.publication.json').read_text(encoding='utf-8'))
        site, pages = manifest['site'], manifest['pages']
        origin = urlsplit(site)
        if not isinstance(pages, dict) or not pages or origin.scheme not in ('https', 'http') or not origin.netloc or site != site.rstrip('/') or origin.path:
            raise ValueError('expected site origin and a nonempty pages mapping')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f'.publication.json: {exc}']
    source_articles = {}
    for file in (root / 'content/articles').glob('*.json'):
        value = json.loads(file.read_text(encoding='utf-8'))
        source_articles['/library/' + value['slug'] + '/'] = value
    override_file = root / 'content/seo-overrides.json'
    overrides = json.loads(override_file.read_text(encoding='utf-8')) if override_file.exists() else {}
    for a in source_articles.values():
        a.update(overrides.get(a['slug'], {}))
    known_people = {'Lilian Weng'}
    site_file = root / 'site.json'
    if site_file.exists():
        known_people.add(json.loads(site_file.read_text(encoding='utf-8'))['name'])
    organizations = {a['publisher'] for a in source_articles.values()} - known_people
    now = datetime.now(timezone.utc)
    canonicals = []

    def read(path, where):
        try:
            page = Page(path.read_text(encoding='utf-8'))
            parsed[path.resolve()] = page
            return page
        except (OSError, ValueError) as exc:
            fail(where, f'cannot parse HTML: {exc}')
            return None

    for url, dates in pages.items():
        u = urlsplit(url)
        if (u.scheme, u.netloc) != (origin.scheme, origin.netloc) or u.query or u.fragment or not u.path.startswith('/') or any(c.isspace() for c in url) or '\\' in url:
            fail(url, 'invalid canonical URL in manifest')
            continue
        if u.path in ('/articles/', '/articles/index.html', '/404.html'):
            fail(url, 'fallback or 404 must not be in manifest')
        if not isinstance(dates, dict):
            fail(url, 'manifest page metadata is not an object')
            continue
        for key in ('published', 'modified'):
            try:
                date = timestamp(dates.get(key))
                if key == 'modified' and date > now:
                    fail(url, 'lastmod is in the future')
            except (ValueError, TypeError) as exc:
                fail(url, f'invalid {key}: {exc}')
        path = local_file(dist, u.path)
        if path is None or path.suffix != '.html':
            fail(url, 'canonical HTML page is missing')
            continue
        p = read(path, url)
        if p is None:
            continue
        if p.canonicals != [url]:
            fail(url, f'expected one self-canonical, found {p.canonicals}')
        canonicals.extend(p.canonicals)
        for label, values in [('title', p.titles), ('description', p.meta('description'))]:
            if len(values) != 1 or not values[0].strip():
                fail(url, f'expected one nonempty {label}')
            elif ELLIPSIS.search(values[0]):
                fail(url, f'{label} contains a truncation ellipsis')
        if p.noindex():
            fail(url, 'indexable page is marked noindex')
        if p.h1 != 1:
            fail(url, f'expected one H1, found {p.h1}')
        images = p.meta('og:image')
        if len(images) != 1:
            fail(url, 'expected one og:image')
        else:
            image = urlsplit(images[0])
            if (image.scheme, image.netloc) != (origin.scheme, origin.netloc) or local_file(dist, image.path) is None:
                fail(url, 'og:image must resolve to an existing site asset')
        graph = []
        for raw in p.ld:
            try:
                value = json.loads(raw)
                roots = value if isinstance(value, list) else [value]
                if not roots or any(not isinstance(n, dict) for n in roots):
                    raise ValueError('JSON-LD must contain objects')
                for node in roots:
                    if not node.get('@context'):
                        raise ValueError('JSON-LD has no @context')
                    nodes = node.get('@graph', [node])
                    if not isinstance(nodes, list) or not nodes or any(not isinstance(n, dict) or not types(n) for n in nodes):
                        raise ValueError('JSON-LD nodes require @type')
                    graph.extend(nodes)
            except (ValueError, TypeError) as exc:
                fail(url, f'invalid JSON-LD: {exc}')
        if not graph:
            fail(url, 'missing usable JSON-LD')
        all_objects = list(objects(graph))
        ids = {node['@id']: node for node in all_objects if node.get('@id') and types(node)}
        for node in all_objects:
            for role in ('author', 'publisher'):
                if role not in node:
                    continue
                entities = node[role] if isinstance(node[role], list) else [node[role]]
                if not entities:
                    fail(url, f'empty schema {role}')
                for entity in entities:
                    if isinstance(entity, dict) and not types(entity):
                        entity = ids.get(entity.get('@id'), entity)
                    if not isinstance(entity, dict) or not types(entity).intersection({'Person', 'Organization'}) or not isinstance(entity.get('name'), str) or not entity['name'].strip():
                        fail(url, f'schema {role} needs a named Person/Organization or resolvable reference')
                        continue
                    name = entity['name']
                    if (name in organizations or name.endswith(' Team')) and 'Person' in types(entity):
                        fail(url, f'organization {name!r} is incorrectly typed Person')
                    if name in known_people and 'Organization' in types(entity):
                        fail(url, f'person {name!r} is incorrectly typed Organization')
        articles = [node for node in graph if types(node).intersection({'Article', 'BlogPosting'})]
        for article in articles:
            if article.get('url') != url or not article.get('headline') or not article.get('author'):
                fail(url, 'article schema needs its canonical URL, headline and author')
            for field, key in [('datePublished', 'published'), ('dateModified', 'modified')]:
                if article.get(field) != dates.get(key):
                    fail(url, f'{field} must match the local publication manifest')
        source = source_articles.get(u.path)
        if source:
            if len(articles) != 1:
                fail(url, 'translated page needs one Article schema')
            for article in articles:
                original = article.get('translationOfWork')
                if not isinstance(original, dict) or 'Article' not in types(original) or original.get('url') != source['url'] or original.get('headline') != source['original_title']:
                    fail(url, 'translationOfWork is missing or points to the wrong source')
                    continue
                date_field = {'last updated': 'dateModified', 'PDF creation date': 'dateCreated'}.get(source.get('date_kind'), 'datePublished')
                expected = {date_field: source['date']} if source.get('date') else {}
                actual = {key: original[key] for key in ('datePublished', 'dateModified', 'dateCreated') if key in original}
                if actual != expected:
                    fail(url, 'source date or date kind is incorrectly attached to translationOfWork')
        elif u.path.startswith('/articles/') and not articles:
            fail(url, 'personal post is missing Article/BlogPosting schema')
        elif u.path.startswith('/library/') and u.path != '/library/' and not source:
            fail(url, 'translated page has no source article metadata')
        if not articles:
            collections = [node for node in graph if 'CollectionPage' in types(node)]
            if len(collections) != 1 or collections[0].get('url') != url or not collections[0].get('name'):
                fail(url, 'listing/topic needs one named CollectionPage with its canonical URL')
    for canonical, count in Counter(canonicals).items():
        if count > 1:
            fail(canonical, 'canonical is repeated across manifest pages')

    # The two non-indexable/noncanonical special pages are deliberately separate.
    fallback = read(dist / 'articles/index.html', '/articles/')
    if fallback and fallback.canonicals != [site + '/']:
        fail('/articles/', 'fallback must canonicalize to /')
    missing = read(dist / '404.html', '/404.html')
    if missing and not missing.noindex():
        fail('/404.html', '404 must be noindex')
    for path, p in parsed.items():
        for link in set(p.links):
            if local_file(dist, link) is None:
                fail(str(path.relative_to(dist.resolve())), 'missing local target ' + link)
    try:
        sitemap = ET.parse(dist / 'sitemap.xml').getroot()
        if sitemap.tag != SITEMAP_NS + 'urlset':
            raise ValueError('expected sitemap urlset namespace')
        records = sitemap.findall(SITEMAP_NS + 'url')
        urls = [item.findtext(SITEMAP_NS + 'loc') for item in records]
        if Counter(urls) != Counter(pages.keys()):
            fail('sitemap.xml', f'URL set differs from manifest (missing={set(pages)-set(urls)}, extra={set(urls)-set(pages)}, duplicates={[u for u,c in Counter(urls).items() if c>1]})')
        for item, url in zip(records, urls):
            if url in pages and item.findtext(SITEMAP_NS + 'lastmod') != pages[url].get('modified'):
                fail('sitemap.xml', f'lastmod differs from manifest: {url}')
    except (OSError, ET.ParseError, ValueError) as exc:
        fail('sitemap.xml', str(exc))
    try:
        feed = ET.parse(dist / 'feed.xml').getroot()
        if feed.tag != 'rss' or feed.find('channel') is None:
            raise ValueError('expected RSS channel')
        for item in feed.findall('./channel/item'):
            if not item.findtext('title') or item.findtext('link') not in pages:
                fail('feed.xml', 'item requires title and a manifest canonical URL')
    except (OSError, ET.ParseError, ValueError) as exc:
        fail('feed.xml', str(exc))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    args = parser.parse_args(argv)
    errors = verify(args.dist)
    for error in errors:
        print('ERROR', error)
    if errors:
        print(f'SEO validation failed: {len(errors)} error(s).')
        return 1
    print('SEO validation passed: manifest pages, metadata, schema, links, sitemap and feed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
