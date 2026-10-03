"""Fail a build when bilingual content, local images or source links are missing."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote
from datetime import datetime, timezone
import json, re

ROOT = Path(__file__).resolve().parents[1]

class Check(HTMLParser):
    def __init__(self): super().__init__(); self.errors=[]; self.text=[]
    def handle_data(self, text): self.text.append(text)
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag in ['script', 'iframe', 'object', 'embed', 'form', 'video', 'base', 'meta', 'link', 'frame', 'frameset', 'applet', 'template']: self.errors.append('Unsafe/unsupported tag: '+tag)
        if any(k.startswith('on') for k in attrs): self.errors.append('Inline handler')
        for key in ['href', 'src']:
            v=attrs.get(key,'')
            if urlparse(v).scheme not in ['', 'https', 'http', 'mailto']: self.errors.append('Invalid scheme: '+v[:70])
            if v.startswith('/') and not (ROOT/'public'/unquote(v.lstrip('/'))).exists(): self.errors.append('Missing local asset: '+v)

def main():
    paths=list((ROOT/'content/articles').glob('*.json')); errors=[]; count=0
    assert paths, 'No articles'
    slugs=set()
    for p in paths:
        a=json.loads(p.read_text()); ids=[]
        slug=a.get('slug','')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug) or slug in slugs: errors.append((p.stem,'Invalid or duplicate slug'))
        slugs.add(slug)
        if not a.get('title') or not a.get('original_title') or not a.get('url','').startswith('https://'): errors.append((p.stem,'Missing metadata'))
        for b in a['blocks']:
            count+=1; ids.append(b['id'])
            for lang in (['en'] if b['preserve'] else ['en','zh']):
                if not b.get(lang): errors.append((b['id'],'Missing '+lang)); continue
                parser=Check(); parser.feed(b[lang]);errors.extend((b['id'],e) for e in parser.errors)
                if not b['preserve'] and not ''.join(parser.text).strip(): errors.append((b['id'],'Empty text '+lang))
        if len(ids)!=len(set(ids)):errors.append((p.stem,'Duplicate block IDs'))
        for v in a.get('downloads',{}).values():
            if not (ROOT/'public'/v.lstrip('/')).is_file():errors.append((p.stem,'Missing PDF '+v))
    post_slugs=set(); posts=0
    for p in (ROOT/'content/posts').glob('*.json'):
        a=json.loads(p.read_text())
        if not isinstance(a.get('draft',False),bool): errors.append((p.stem,'draft must be boolean'))
        if a.get('draft'): continue
        posts+=1; slug=a.get('slug','')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug) or slug in post_slugs: errors.append((p.stem,'Invalid or duplicate post slug'))
        post_slugs.add(slug)
        if not a.get('title') or not a.get('blocks'): errors.append((p.stem,'Missing title or blocks'))
        if a.get('category') and a['category'] not in ['基础与架构','上下文工程','工具与技能','评测与改进','安全与可靠性']: errors.append((p.stem,'Unknown topic category'))
        if a.get('published_at'):
            try:
                date=datetime.fromisoformat(a['published_at'])
                if date.tzinfo is None or date>datetime.now(timezone.utc): raise ValueError()
            except (ValueError,TypeError): errors.append((p.stem,'published_at must be a non-future ISO datetime with timezone'))
        ids=[]
        for b in a.get('blocks',[]):
            bid=b.get('id',''); ids.append(bid)
            if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]*',bid): errors.append((p.stem,'Invalid block ID'))
            parser=Check(); parser.feed(b.get('html',''))
            errors.extend((p.stem,e) for e in parser.errors)
            if not b.get('html'): errors.append((p.stem,'Empty post block'))
        if len(ids)!=len(set(ids)): errors.append((p.stem,'Duplicate post block IDs'))
    if errors:
        for error in errors:print('ERROR',*error)
        raise SystemExit(1)
    print(f'Validated {len(paths)} library articles, {posts} posts and {count} bilingual blocks; translations and local assets present.')

if __name__=='__main__': main()
