"""Fail a build when bilingual content, local images or source links are missing."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote
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
    for p in paths:
        a=json.loads(p.read_text()); ids=[]
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
    if errors:
        for error in errors:print('ERROR',*error)
        raise SystemExit(1)
    print(f'Validated {len(paths)} articles and {count} blocks; all translations and local assets present.')

if __name__=='__main__': main()
