"""Import reviewed bilingual blocks. Original web archives never enter the repo.

Usage: python scripts/import_library.py /path/to/article_translation
Optional: --pdf-dir /path/to/output/pdf
Extraction only dependency: lxml. The site build uses the standard library.
"""
from pathlib import Path
from urllib.parse import urlparse
import argparse, base64, hashlib, json, re, shutil
from lxml import html, etree

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'image/svg+xml': 'svg', 'image/gif': 'gif', 'image/avif': 'avif'}
CATEGORIES = ['基础与架构', '上下文工程', '工具与技能', '评测与改进', '安全与可靠性']

def category(a):
    s = a['slug']
    if any(t in s for t in ['containment', 'sandbox', 'auto_mode']): return '安全与可靠性'
    if any(t in s for t in ['context', 'retrieval', 'manus']): return '上下文工程'
    if any(t in s for t in ['eval', 'improvement', 'traces', 'coding_blackbox', 'autoharness', 'c_compiler']): return '评测与改进'
    if any(t in s for t in ['tools', 'think', 'skills', 'mcp_code', 'code_mods']): return '工具与技能'
    return '基础与架构'

def markup(value, lang='shared', shared_ids=None, id_counts=None):
    el = html.fragment_fromstring(value, create_parent='div')
    shared_ids = shared_ids or set()
    if id_counts is None: id_counts = {}
    for node in list(el.iter()):
        if not isinstance(node.tag, str): continue
        if node.tag in ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'video', 'audio', 'base', 'meta', 'link', 'frame', 'frameset', 'applet', 'template']:
            node.drop_tree(); continue
        original_id = node.get('id') or (node.get('name') if node.tag == 'a' else None)
        if original_id:
            key = lang + '-source-' + original_id
            id_counts[key] = id_counts.get(key, 0) + 1
            node.set('id', key + (f'-{id_counts[key]}' if id_counts[key] > 1 else ''))
            if node.tag == 'a' and node.get('name'): del node.attrib['name']
        for attr in list(node.attrib):
            if attr.lower().startswith('on') or attr in ['style', 'srcdoc']: del node.attrib[attr]
        for attr in ['href', 'src', 'poster']:
            value = node.get(attr)
            if not value: continue
            if value.startswith('data:image/'):
                header, encoded = value.split(',', 1)
                mime = header.split(';')[0][5:]
                if mime not in EXTENSIONS or ';base64' not in header: raise ValueError('Unsupported image data URL')
                raw = base64.b64decode(encoded, validate=True)
                name = hashlib.sha256(raw).hexdigest()[:24] + '.' + EXTENSIONS[mime]
                target = ROOT / 'public/media' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists(): target.write_bytes(raw)
                node.set(attr, '/media/' + name)
            elif urlparse(value).scheme.lower() not in ['', 'http', 'https', 'mailto']:
                del node.attrib[attr]
            elif value.startswith('//'): node.set(attr, 'https:' + value)
            elif attr == 'href' and value.startswith('#') and len(value) > 1:
                prefix = 'shared' if value[1:] in shared_ids else lang
                node.set(attr, '#' + prefix + '-source-' + value[1:])
        if node.tag == 'a' and (node.get('href', '').startswith(('https://', 'http://'))):
            node.set('rel', 'noopener noreferrer')
        if node.tag == 'img':
            node.set('loading', 'lazy'); node.set('decoding', 'async')
    return (el.text or '') + ''.join(html.tostring(c, encoding='unicode') for c in el)

def plain(value):
    return ' '.join(html.fragment_fromstring(value, create_parent='div').text_content().split())

def run(work, pdf_dir):
    manifests = [work / 'manifest.json'] + sorted(work.glob('manifest-extra-*.json'))
    by_slug = {}
    for manifest in manifests:
        for item in json.loads(manifest.read_text()): by_slug[item['slug']] = item
    results = []
    for a in sorted(by_slug.values(), key=lambda a: a.get('source_order', 999)):
        source = work / (a['slug'] + '.json'); translated = work / (a['slug'] + '.zh.json')
        if not source.exists() or not translated.exists(): print('PENDING', a['slug']); continue
        full = json.loads(source.read_text()); zh = json.loads(translated.read_text())
        expected = {b['id'] for b in full['blocks'] if not b['preserve']}
        if expected != set(zh): print('PENDING INCOMPLETE', a['slug']); continue
        slug = re.sub(r'^new\d+_', '', a['slug']).replace('_', '-')
        keep = ['title', 'original_title', 'url', 'date', 'publisher', 'author', 'date_kind', 'source_order', 'content_kind', 'source_note']
        data = {k: a[k] for k in keep if k in a}
        data.update({'slug': slug, 'source_id': a['slug'], 'category': category(a), 'blocks': []})
        shared_ids = set()
        id_counts = {}
        for b in full['blocks']:
            if b['preserve']:
                el = html.fragment_fromstring(b['html'], create_parent='div')
                shared_ids.update(el.xpath('.//@id | .//a/@name'))
        for b in full['blocks']:
            item = {'id': b['id'], 'tag': b['tag'], 'preserve': b['preserve'], 'en': markup(b['html'], 'shared' if b['preserve'] else 'en', shared_ids, id_counts)}
            if not b['preserve']: item['zh'] = markup(zh[b['id']], 'zh', shared_ids, id_counts)
            for key in ['keep_next', 'allow_split', 'compact']:
                if key in b: item[key] = b[key]
            data['blocks'].append(item)
        intro = next((b['zh'] for b in data['blocks'] if b['tag'] == 'p' and not b['preserve'] and '<br' not in b['zh'] and len(plain(b['zh'])) > 40), '')
        data['description'] = plain(intro)[:125].rstrip('。，；： ') + ('…' if len(plain(intro)) > 125 else '')
        body = ''.join(plain(b.get('zh', '')) for b in data['blocks'])
        data['reading_minutes'] = max(2, round(len(body) / 420))
        data['downloads'] = {}
        for language, label in [('zh', '中文'), ('en', '英文')]:
            pdf = pdf_dir / (a['title'] + '（' + label + '）.pdf') if pdf_dir else None
            if pdf and pdf.exists():
                filename = f'{slug}-{language}.pdf'; shutil.copy2(pdf, ROOT / 'public/downloads' / filename)
                data['downloads'][language] = '/downloads/' + filename
        if a.get('source', '').lower().endswith('.pdf') and Path(a['source']).exists():
            filename = slug + '-source.pdf'; shutil.copy2(a['source'], ROOT / 'public/downloads' / filename)
            data['downloads']['original'] = '/downloads/' + filename
        (ROOT / 'content/articles' / (slug + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        results.append(data)
        print('IMPORTED', slug, len(data['blocks']), 'blocks')
    assert len({a['slug'] for a in results}) == len(results)
    print('TOTAL', len(results))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('work', type=Path); parser.add_argument('--pdf-dir', type=Path)
    args = parser.parse_args(); run(args.work, args.pdf_dir)
