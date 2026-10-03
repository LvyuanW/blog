"""Shared publishing metadata. No external service is required to build the site."""
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def structured(*nodes):
    return '<script type="application/ld+json">' + json.dumps(
        {'@context': 'https://schema.org', '@graph': list(nodes)},
        ensure_ascii=False).replace('<', '\\u003c') + '</script>'


def imported_at(path):
    """Bootstrap existing content from its first recorded import, not its source date."""
    result = subprocess.run(['git', 'log', '--diff-filter=A', '--format=%cI', '--', str(path)],
                            cwd=ROOT, capture_output=True, text=True)
    dates = result.stdout.strip().splitlines()
    return dates[-1] if dates else None


class Publication:
    def __init__(self, site, previous=None):
        self.site = site.rstrip('/')
        self.now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.old = {}
        if previous and Path(previous).exists():
            data = json.loads(Path(previous).read_text())
            if data.get('site') == self.site:
                self.old = data.get('pages', {})
        self.pages = {}

    def add(self, path, payload, first_recorded=None, published_at=None):
        url = self.site + path
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        old = self.old.get(url, {})
        first = published_at or old.get('published') or first_recorded or self.now
        entry = {'hash': digest, 'published': first,
                 'modified': old['modified'] if old.get('hash') == digest else self.now}
        self.pages[url] = entry
        return entry

    def save(self, target):
        Path(target).write_text(json.dumps({'site': self.site, 'pages': self.pages}, ensure_ascii=False, indent=2) + '\n')

    def sitemap(self):
        rows = ''.join('<url><loc>' + escape(url) + '</loc><lastmod>' + escape(item['modified']) + '</lastmod></url>'
                       for url, item in self.pages.items())
        return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + rows + '</urlset>\n'


def owner(site):
    return {'@type': 'Person', '@id': site['url'] + '/#author', 'name': site['name'], 'url': site['url'] + '/'}


def website(site):
    return {'@type': 'WebSite', '@id': site['url'] + '/#website', 'url': site['url'] + '/',
            'name': '6yuan博客', 'alternateName': '6yuan', 'description': site['description'],
            'inLanguage': 'zh-CN', 'publisher': {'@id': site['url'] + '/#author'}}


def breadcrumb(site, entries):
    return {'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i, 'name': name, 'item': site['url'] + path}
        for i, (name, path) in enumerate(entries, 1)]}


def collection(site, title, description, path, articles):
    return {'@type': 'CollectionPage', '@id': site['url'] + path + '#page', 'url': site['url'] + path,
            'name': title, 'description': description, 'inLanguage': 'zh-CN',
            'isPartOf': {'@id': site['url'] + '/#website'},
            'mainEntity': {'@type': 'ItemList', 'numberOfItems': len(articles), 'itemListElement': [
                {'@type': 'ListItem', 'position': i, 'name': a['title'], 'url': site['url'] + a['path']}
                for i, a in enumerate(articles, 1)]}}


def source_authors(article):
    if article.get('authors'):
        return article['authors']
    name = article.get('author')
    if article['publisher'] == 'Lilian Weng' and (not name or name == article['publisher']):
        return [{'@type': 'Person', 'name': 'Lilian Weng'}]
    if not name or name == article['publisher'] or name.endswith(' Team'):
        return [{'@type': 'Organization', 'name': name or article['publisher']}]
    return [{'@type': 'Person', 'name': n.strip()} for n in re.split(r',\s*|\s+&\s+', name) if n.strip()]


def reading_schema(site, a, dates):
    url = site['url'] + a['path']
    source = {'@type': 'Article', '@id': a['url'], 'url': a['url'], 'headline': a['original_title'],
              'inLanguage': 'en', 'author': source_authors(a),
              'publisher': {'@type': 'Person' if a['publisher'] == 'Lilian Weng' else 'Organization', 'name': a['publisher']}}
    if a.get('date'):
        source[{'PDF creation date': 'dateCreated', 'last updated': 'dateModified'}.get(a.get('date_kind'), 'datePublished')] = a['date']
    return {'@type': 'Article', '@id': url + '#article', 'url': url, 'headline': a['title'],
            'description': a['description'], 'inLanguage': 'zh-CN', 'author': source_authors(a),
            'publisher': {'@id': site['url'] + '/#author'}, 'datePublished': dates['published'], 'dateModified': dates['modified'],
            'mainEntityOfPage': {'@id': url}, 'isPartOf': {'@id': site['url'] + '/#website'},
            'articleSection': a['category'], 'translationOfWork': source,
            'image': site['url'] + '/assets/social-card.png'}
