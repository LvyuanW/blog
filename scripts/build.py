"""Build a static, server-rendered reading library. Python 3.10+, no dependencies."""
from pathlib import Path
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
from datetime import datetime, timezone
import hashlib, json, re, shutil

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
SITE = json.loads((ROOT / 'site.json').read_text())
CATEGORIES = ['基础与架构', '上下文工程', '工具与技能', '评测与改进', '安全与可靠性']
LOGOS = {'Anthropic': 'anthropic.svg', 'OpenAI': 'openai.svg', 'LangChain': 'langchain.png', 'Cursor': 'cursor.svg', 'Manus': 'manus.svg', 'Lilian Weng': 'lilian-weng.png', 'HumanLayer': 'humanlayer.png', 'arXiv': 'arxiv.png', 'Google DeepMind': 'arxiv.png', 'DeepMind': 'arxiv.png'}

class Text(HTMLParser):
    def __init__(self): super().__init__(); self.values = []
    def handle_data(self, data): self.values.append(data)

def plain(value):
    p = Text(); p.feed(value); return ' '.join(''.join(p.values).split())

def fingerprint(name):
    return hashlib.sha256((ROOT / 'public/assets' / name).read_bytes()).hexdigest()[:10]

def publisher(a, with_name=True):
    name = a['publisher']; file = LOGOS.get(name)
    if name == 'OpenAI':
        return '<span class="publisher"><img class="wordmark" src="/assets/logos/openai.svg" width="62" height="20" alt="OpenAI" loading="lazy"></span>'
    image = f'<img src="/assets/logos/{file}" width="20" height="20" alt="" loading="lazy">' if file else '<span class="source-initial">' + escape(name[:1]) + '</span>'
    return '<span class="publisher">' + image + (f'<span>{escape(name)}</span>' if with_name else '') + '</span>'

def date_label(a):
    suffix = {'last updated': ' · 更新', 'PDF creation date': ' · 文件日期'}.get(a.get('date_kind'), '')
    return escape(a.get('date', '')) + suffix

def header(active):
    return f'''<a class="skip-link" href="#main">跳到正文</a><header class="site-header"><div class="header-inner"><a class="brand" href="/" aria-label="6yuan 首页">6yuan<span class="brand-period">.</span></a><span class="brand-caption">文章与资料馆</span><nav aria-label="主导航"><a href="/articles/" {'aria-current="page"' if active == 'articles' else ''}>6yuan的文章</a><a href="/library/" {'aria-current="page"' if active == 'library' else ''}>资料馆</a></nav><a class="github-link" href="{SITE['repository']}" aria-label="博客的 GitHub 仓库" rel="noopener noreferrer">GitHub <span aria-hidden="true">↗</span></a></div></header>'''

def layout(title, body, path='/', active='library', description=None, kind='website', extra_head=''):
    url = SITE['url'] + path; desc = description or SITE['description']
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{escape(title)} · 6yuan</title><meta name="description" content="{escape(desc, quote=True)}"><link rel="canonical" href="{url}"><meta property="og:title" content="{escape(title, quote=True)}"><meta property="og:description" content="{escape(desc, quote=True)}"><meta property="og:type" content="{kind}"><meta property="og:url" content="{url}"><meta property="og:site_name" content="6yuan"><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/site.css?v={fingerprint('site.css')}"><script src="/assets/site.js?v={fingerprint('site.js')}" defer></script>{extra_head}</head><body>{header(active)}{body}<footer class="site-footer"><div><a class="footer-brand" href="/">6yuan.</a><p>文章与资料馆</p></div><a href="#top" class="back-top">回到顶部 ↑</a></footer></body></html>'''

def write(path, value):
    target = DIST / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(value)

def library(articles):
    publishers = list(dict.fromkeys(a['publisher'] for a in articles))
    filters = ''.join(f'<button type="button" data-category="{c}" aria-pressed="false"><span>{c}</span><span>{sum(a["category"] == c for a in articles):02d}</span></button>' for c in CATEGORIES)
    sources = ''.join(f'<option value="{escape(p)}">{escape(p)}</option>' for p in publishers)
    rows = []
    for i, a in enumerate(articles, 1):
        search = ' '.join([a['title'], a['original_title'], a['publisher'], a['category'], a.get('description', '')]).lower()
        rows.append(f'''<article class="library-row" data-search="{escape(search, quote=True)}" data-category="{a['category']}" data-publisher="{escape(a['publisher'], quote=True)}" data-date="{escape(a.get('date', ''))}"><span class="row-number">{i:02d}</span><div class="row-content"><div class="row-meta">{publisher(a)}<span class="meta-dot">·</span><span>{date_label(a)}</span><span class="row-category">{a['category']}</span></div><h2><a href="/library/{a['slug']}/">{escape(a['title'])}</a></h2><p class="row-english" lang="en">{escape(a['original_title'])}</p><div class="row-bottom"><span>{a['reading_minutes']} 分钟阅读</span><span>中文 · English · 对照</span></div></div><a class="row-arrow" href="/library/{a['slug']}/" aria-label="阅读{escape(a['title'], quote=True)}"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 12h14m-6-6 6 6-6 6"/></svg></a></article>''')
    body = f'''<main id="main" class="library-main"><section class="library-hero" id="top"><div><p class="eyebrow">THE LIBRARY <span>／</span> 持续积累的阅读档案</p><h1>资料馆<span class="title-dot">。</span></h1></div><div class="library-stats"><div><strong>{len(articles):02d}</strong><span>篇收藏</span></div><div><strong>{len(publishers):02d}</strong><span>个来源</span></div><p>中英对照 · 完整图文</p></div></section><section class="library-layout" aria-label="资料列表"><aside class="library-sidebar"><p class="sidebar-heading">按主题浏览</p><div class="topic-filters"><button type="button" class="active" data-category="" aria-pressed="true"><span>全部资料</span><span>{len(articles):02d}</span></button>{filters}</div></aside><div class="library-results"><div class="search-toolbar"><label class="search-box"><span aria-hidden="true">⌕</span><span class="sr-only">搜索资料</span><input id="library-search" type="search" placeholder="搜索标题、来源或主题…" autocomplete="off"></label><label class="source-select"><span class="sr-only">按来源筛选</span><select id="source-filter"><option value="">全部来源</option>{sources}</select></label></div><div class="result-caption"><span id="result-count" aria-live="polite">全部资料 · {len(articles)} 篇</span><label class="sort-control">排序 <select id="sort-order" aria-label="排序方式"><option value="collection">收藏顺序</option><option value="newest">最新日期</option><option value="oldest">最早日期</option></select></label></div><div id="article-list">{''.join(rows)}</div><div id="no-results" class="no-results" hidden><p>没有找到相应资料</p><span>试试其他关键词，或清除筛选条件。</span><button type="button" id="reset-filters">清除筛选</button></div></div></section></main>'''
    write('index.html', layout('资料馆', body, '/'))
    write('library/index.html', layout('资料馆', body, '/library/'))

def article(a, previous, following):
    title = escape(a['title']); original = escape(a['original_title']); rows = []; toc = []
    for b in a['blocks']:
        bid = escape(b['id'], quote=True)
        if b['preserve']:
            classes = 'shared' + (' keep-next' if b.get('keep_next') else '') + (' allow-split' if b.get('allow_split') else '')
            rows.append(f'<div class="{classes}" id="{bid}">{b["en"]}</div>'); continue
        if b['tag'] in ['h2', 'h3']:
            en, zh = escape(plain(b['en'])), escape(plain(b['zh']))
            toc.append(f'<a class="toc-{b["tag"]}" href="#{bid}"><span class="toc-zh">{zh}</span><span class="toc-en" lang="en">{en}</span></a>')
        classes = 'pair' + (' keep-next' if b.get('keep_next') else '')
        rows.append(f'<section class="{classes}" id="{bid}"><div class="zh" lang="zh-CN">{b["zh"]}</div><div class="en" lang="en">{b["en"]}</div></section>')
    download_items = []
    for lang, label in [('zh', '中文 PDF'), ('en', '英文 PDF'), ('original', '原版 PDF')]:
        if a.get('downloads', {}).get(lang): download_items.append(f'<a href="{a["downloads"][lang]}" download>{label} ↓</a>')
    downloads = '<details class="download-menu"><summary>下载 PDF</summary><div>' + ''.join(download_items) + '</div></details>' if download_items else ''
    extras = ''
    if a.get('source_note'): extras = f'<p class="source-note">{escape(a["source_note"])}</p>'
    neighbor = ''
    for item, label in [(previous, '上一篇'), (following, '下一篇')]:
        neighbor += f'<a href="/library/{item["slug"]}/"><span>{label}</span><strong>{escape(item["title"])}</strong></a>' if item else '<span></span>'
    body = f'''<div class="reading-progress" aria-hidden="true"><div id="reading-progress-bar"></div></div><main id="main" class="article-main" data-reader data-mode="zh"><div class="article-breadcrumb" id="top"><a href="/library/">资料馆</a><span>／</span><span>{a['category']}</span></div><header class="article-header"><div class="article-kicker">{publisher(a)}<span class="kicker-divider"></span><span>阅读档案 · 非官方中文译文</span></div><h1><span class="title-zh">{title}</span><span class="title-en" lang="en">{original}</span></h1><p class="article-original-title" lang="en" aria-hidden="true">{original}</p><div class="article-meta"><span>{escape(a.get('author', a['publisher']))}</span><span>{date_label(a)}</span><span>约 {a['reading_minutes']} 分钟</span><a href="{escape(a['url'], quote=True)}" rel="noopener noreferrer" target="_blank">阅读原文 ↗</a></div>{extras}</header><div class="reader-toolbar"><div class="language-controls" role="group" aria-label="阅读语言"><button data-mode-button="zh" aria-pressed="true" class="active">中文</button><button data-mode-button="en" aria-pressed="false">English</button><button data-mode-button="both" aria-pressed="false">中英对照</button></div><div class="reading-tools"><button data-font-step="-1" aria-label="缩小正文字号">A−</button><button data-font-step="1" aria-label="增大正文字号">A＋</button><span class="tool-separator"></span>{downloads}<button id="print-article" aria-label="打印当前阅读模式">打印</button></div></div><div class="reading-layout"><aside class="article-toc"><details open><summary>文章目录 <span>CONTENTS</span></summary><nav aria-label="文章目录">{''.join(toc)}</nav></details><a class="toc-source" href="{escape(a['url'], quote=True)}" target="_blank" rel="noopener noreferrer">{publisher(a)} 原文 ↗</a></aside><article class="article-content"><div class="reader-note"><span class="note-zh">完整译文与原文逐段对应。图片、图注、表格和代码保留原文。</span><span class="note-en" lang="en">A complete reading edition. Figures, captions, tables and code are preserved from the source.</span></div><div class="column-headings"><span>中文译文</span><span lang="en">ENGLISH ORIGINAL</span></div>{''.join(rows)}<div class="article-end"><span class="end-symbol" aria-hidden="true">✳</span><p>— 全文完 —</p><p>原文来自 {escape(a['publisher'])}，中文为非官方学习译文。<br><a href="{escape(a['url'], quote=True)}" target="_blank" rel="noopener noreferrer">查看原始出处 ↗</a></p></div><nav class="article-neighbors" aria-label="相邻资料">{neighbor}</nav></article></div></main><dialog id="image-dialog" aria-label="查看原图"><button class="close-image" aria-label="关闭原图">关闭 ×</button><img alt=""><p>点击空白处或按 Esc 关闭</p></dialog>'''
    schema = {'@context': 'https://schema.org', '@type': 'Article', 'headline': a['title'], 'inLanguage': ['zh-CN', 'en'], ('dateCreated' if a.get('date_kind') == 'PDF creation date' else 'dateModified' if a.get('date_kind') == 'last updated' else 'datePublished'): a.get('date', ''), 'author': {'@type': 'Person' if a['publisher'] == 'Lilian Weng' else 'Organization', 'name': a.get('author', a['publisher'])}, 'isBasedOn': a['url'], 'url': SITE['url'] + '/library/' + a['slug'] + '/'}
    extra = '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c') + '</script>'
    write('library/' + a['slug'] + '/index.html', layout(a['title'], body, '/library/' + a['slug'] + '/', description=a.get('description'), kind='article', extra_head=extra))

def main():
    articles = sorted([json.loads(p.read_text()) for p in (ROOT / 'content/articles').glob('*.json')], key=lambda a: a.get('source_order', 999))
    if DIST.exists(): shutil.rmtree(DIST)
    shutil.copytree(ROOT / 'public', DIST)
    library(articles)
    for i, a in enumerate(articles): article(a, articles[i-1] if i else None, articles[i+1] if i+1 < len(articles) else None)
    empty = '''<main id="main" class="personal-main"><section id="top"><p class="eyebrow">ESSAYS & NOTES <span>／</span> 6YUAN</p><h1>6yuan的文章<span class="title-dot">。</span></h1><div class="empty-writing"><span class="writing-mark" aria-hidden="true">§</span><div><h2>尚未发布文章</h2><p>这里将收录 6yuan 的原创文章。</p><a href="/library/">先去资料馆看看 ↗</a></div></div></section></main>'''
    write('articles/index.html', layout('6yuan的文章', empty, '/articles/', active='articles'))
    write('404.html', layout('页面未找到', '<main id="main" class="not-found"><p class="eyebrow">404</p><h1 id="top">这一页暂时不存在。</h1><a href="/library/">返回资料馆 ↗</a></main>', '/404.html'))
    urls = ['/', '/library/', '/articles/'] + ['/library/' + a['slug'] + '/' for a in articles]
    write('sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join('<url><loc>' + escape(SITE['url'] + u) + '</loc></url>' for u in urls) + '</urlset>')
    write('robots.txt', 'User-agent: *\nAllow: /\nSitemap: ' + SITE['url'] + '/sitemap.xml\n')
    write('build-info.json', json.dumps({'articles': len(articles), 'built_at': datetime.now(timezone.utc).isoformat(), 'site': SITE['url']}))
    print(f'Built {len(articles)} articles → {DIST}')

if __name__ == '__main__': main()
