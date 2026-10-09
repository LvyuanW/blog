"""Build a static, server-rendered reading library. Python 3.10+, no dependencies."""
from pathlib import Path
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
from datetime import datetime, timezone
import hashlib, json, re, shutil, os
from email.utils import format_datetime
from seo import Publication, imported_at, structured, owner, website, breadcrumb, collection, reading_schema, source_authors

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
SITE = json.loads((ROOT / 'site.json').read_text())
CATEGORIES = ['基础与架构', '上下文工程', '工具与技能', '评测与改进', '安全与可靠性']
TOPIC_SLUGS = dict(zip(CATEGORIES, ['architecture', 'context-engineering', 'tools-and-skills', 'evaluation', 'reliability']))
PUBLICATION = None
LOGOS = {'Anthropic': 'anthropic.svg', 'OpenAI': 'openai.svg', 'LangChain': 'langchain.png', 'Cursor': 'cursor.svg', 'Manus': 'manus.svg', 'Lilian Weng': 'lilian-weng.png', 'HumanLayer': 'humanlayer.png', 'arXiv': 'arxiv.png', 'Google DeepMind': 'arxiv.png', 'DeepMind': 'arxiv.png', 'Sonar': 'sonar.svg', 'Live-SWE-agent': 'github.svg'}

class Text(HTMLParser):
    def __init__(self): super().__init__(); self.values = []
    def handle_data(self, data): self.values.append(data)

def plain(value):
    p = Text(); p.feed(value); return ' '.join(''.join(p.values).split())

def fingerprint(name):
    return hashlib.sha256((ROOT / 'public/assets' / name).read_bytes()).hexdigest()[:10]

def publisher(a, with_name=True):
    name = a['publisher']; file = LOGOS.get(name)
    if name in ['OpenAI', 'Sonar']:
        return f'<span class="publisher"><img class="wordmark" src="/assets/logos/{file}" width="62" height="20" alt="{name}" loading="lazy"></span>'
    image = f'<img src="/assets/logos/{file}" width="20" height="20" alt="" loading="lazy">' if file else '<span class="source-initial">' + escape(name[:1]) + '</span>'
    return '<span class="publisher">' + image + (f'<span>{escape(name)}</span>' if with_name else '') + '</span>'

def date_label(a):
    suffix = {'last updated': ' · 更新', 'PDF creation date': ' · 文件日期'}.get(a.get('date_kind'), '')
    return escape(a.get('date', '')) + suffix

def header(active):
    return f'''<a class="skip-link" href="#main">跳到正文</a><header class="site-header"><div class="header-inner"><a class="brand" href="/" aria-label="6yuan博客首页">6yuan<span class="brand-label">博客</span></a><span class="brand-caption">文章与资料馆</span><nav aria-label="主导航"><a href="/" {'aria-current="page"' if active == 'articles' else ''}>6yuan的文章</a><a href="/library/" {'aria-current="page"' if active == 'library' else ''}>资料馆</a></nav><a class="github-link" href="{SITE['repository']}" aria-label="博客的 GitHub 仓库" rel="noopener noreferrer">GitHub <span aria-hidden="true">↗</span></a></div></header>'''

def layout(title, body, path='/', active='library', description=None, kind='website', extra_head='', noindex=False):
    url = SITE['url'] + path; desc = description or SITE['description']
    robots = 'noindex,follow' if noindex else 'index,follow,max-image-preview:large'
    verification = ''.join(f'<meta name="{name}" content="{escape(SITE[key], quote=True)}">' for key, name in [('google_site_verification', 'google-site-verification'), ('bing_site_verification', 'msvalidate.01')] if SITE.get(key))
    graph = structured(website(SITE), owner(SITE))
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{escape(title)} · 6yuan博客</title><meta name="description" content="{escape(desc, quote=True)}"><meta name="robots" content="{robots}"><link rel="canonical" href="{url}"><meta property="og:title" content="{escape(title, quote=True)}"><meta property="og:description" content="{escape(desc, quote=True)}"><meta property="og:type" content="{kind}"><meta property="og:url" content="{url}"><meta property="og:site_name" content="6yuan博客"><meta property="og:locale" content="zh_CN"><meta property="og:image" content="{SITE['url']}/assets/social-card.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:alt" content="6yuan博客：Agent 开发、文章与资料馆"><meta name="twitter:card" content="summary_large_image"><link rel="alternate" type="application/rss+xml" title="6yuan博客 · 更新订阅" href="/feed.xml"><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/site.css?v={fingerprint('site.css')}"><script src="/assets/site.js?v={fingerprint('site.js')}" defer></script>{verification}{graph}{extra_head}</head><body>{header(active)}{body}<footer class="site-footer"><div><a class="footer-brand" href="/">6yuan.</a><p>文章与资料馆</p></div><nav class="footer-links" aria-label="更多内容"><a href="/topics/">专题导读</a><a href="/feed.xml">RSS 订阅</a></nav><a href="#top" class="back-top">回到顶部 ↑</a></footer></body></html>'''

def write(path, value):
    target = DIST / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(value)

def library(articles):
    publishers = list(dict.fromkeys(a['publisher'] for a in articles))
    filters = ''.join(f'<button type="button" data-category="{c}" aria-pressed="false"><span>{c}</span><span>{sum(a["category"] == c for a in articles):02d}</span></button>' for c in CATEGORIES)
    sources = ''.join(f'<option value="{escape(p)}">{escape(p)}</option>' for p in publishers)
    rows = []
    for i, a in enumerate(articles, 1):
        search = ' '.join([a['title'], a['original_title'], a['publisher'], a['category'], a.get('description', '')]).lower()
        source_date = f'<span class="meta-dot">·</span><span>{date_label(a)}</span>' if a.get('date') else ''
        rows.append(f'''<article class="library-row" data-search="{escape(search, quote=True)}" data-category="{a['category']}" data-publisher="{escape(a['publisher'], quote=True)}" data-date="{escape(a.get('date', ''))}"><span class="row-number">{i:02d}</span><div class="row-content"><div class="row-meta">{publisher(a)}{source_date}<span class="row-category">{a['category']}</span></div><h2><a href="/library/{a['slug']}/">{escape(a['title'])}</a></h2><p class="row-english" lang="en">{escape(a['original_title'])}</p><div class="row-bottom"><span>{a['reading_minutes']} 分钟阅读</span><span>中文 · English · 对照</span></div></div><a class="row-arrow" href="/library/{a['slug']}/" aria-label="阅读{escape(a['title'], quote=True)}"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 12h14m-6-6 6 6-6 6"/></svg></a></article>''')
    body = f'''<main id="main" class="library-main"><section class="library-hero" id="top"><div><p class="eyebrow">THE LIBRARY <span>／</span> 持续积累的阅读档案</p><h1>资料馆<span class="title-dot">。</span></h1></div><div class="library-stats"><div><strong>{len(articles):02d}</strong><span>篇收藏</span></div><div><strong>{len(publishers):02d}</strong><span>个来源</span></div></div></section><section class="library-layout" aria-label="资料列表"><aside class="library-sidebar"><p class="sidebar-heading">按主题浏览</p><div class="topic-filters"><button type="button" class="active" data-category="" aria-pressed="true"><span>全部资料</span><span>{len(articles):02d}</span></button>{filters}</div><a class="topic-guide-link" href="/topics/">专题导读 →</a></aside><div class="library-results"><div class="search-toolbar"><label class="search-box"><span aria-hidden="true">⌕</span><span class="sr-only">搜索资料</span><input id="library-search" type="search" placeholder="搜索标题、来源或主题…" autocomplete="off"></label><label class="source-select"><span class="sr-only">按来源筛选</span><select id="source-filter"><option value="">全部来源</option>{sources}</select></label></div><div class="result-caption"><span id="result-count" aria-live="polite">全部资料 · {len(articles)} 篇</span><label class="sort-control">排序 <select id="sort-order" aria-label="排序方式"><option value="collection">收藏顺序</option><option value="newest">最新日期</option><option value="oldest">最早日期</option></select></label></div><div id="article-list">{''.join(rows)}</div><div id="no-results" class="no-results" hidden><p>没有找到相应资料</p><span>试试其他关键词，或清除筛选条件。</span><button type="button" id="reset-filters">清除筛选</button></div></div></section></main>'''
    desc = 'AI Agent 开发资料馆：收录模型与运行框架、上下文工程、工具与 Skills、评测及安全相关原始资料，提供非官方中文译文、英文原文与逐段对照阅读。'
    PUBLICATION.add('/library/', {'title': 'Agent 开发资料馆', 'description': desc, 'articles': listing(articles)})
    extra = structured(collection(SITE, 'Agent 开发资料馆', desc, '/library/', articles), breadcrumb(SITE, [('首页', '/'), ('资料馆', '/library/')]))
    write('library/index.html', layout('Agent 开发资料馆 · 中文译文与原文', body, '/library/', description=desc, extra_head=extra))

def article(a, previous, following):
    dates = PUBLICATION.add(a['path'], {'article': a, 'site': SITE, 'schema_version': 1, 'neighbors': listing([n for n in [previous, following] if n])}, imported_at('content/articles/' + a['slug'] + '.json') if not PUBLICATION.old else None)
    topic_path = '/topics/' + TOPIC_SLUGS[a['category']] + '/'
    source_date_name = {'PDF creation date': '原文件创建', 'last updated': '原文更新'}.get(a.get('date_kind'), '原文发布')
    source_date = f'<span>{source_date_name} {escape(a["date"])}</span>' if a.get('date') else ''
    recorded = f'<div class="publication-meta"><span>本站收录 <time datetime="{dates["published"]}">{dates["published"][:10]}</time></span><span>本站更新 <time datetime="{dates["modified"]}">{dates["modified"][:10]}</time></span></div>'
    related = f'<div class="related-topic"><a href="{topic_path}">{a["category"]}专题：问题梳理与相关阅读 →</a></div>'
    ending = '摘要完' if a.get('content_kind') == 'abstract' else '全文完'
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
    body = f'''<div class="reading-progress" aria-hidden="true"><div id="reading-progress-bar"></div></div><main id="main" class="article-main" data-reader data-mode="zh"><div class="article-breadcrumb" id="top"><a href="/library/">资料馆</a><span>／</span><a href="{topic_path}">{a['category']}</a></div><header class="article-header"><div class="article-kicker">{publisher(a)}<span class="kicker-divider"></span><span>阅读档案 · 非官方中文译文</span></div><h1><span class="title-zh">{title}</span><span class="title-en" lang="en">{original}</span></h1><p class="article-original-title" lang="en" aria-hidden="true">{original}</p><div class="article-meta"><span>{escape(', '.join(author['name'] for author in source_authors(a)))}</span>{source_date}<span>约 {a['reading_minutes']} 分钟</span><a href="{escape(a['url'], quote=True)}" rel="noopener noreferrer" target="_blank">阅读原文 ↗</a></div>{recorded}{extras}</header><div class="reader-toolbar"><div class="language-controls" role="group" aria-label="阅读语言"><button data-mode-button="zh" aria-pressed="true" class="active">中文</button><button data-mode-button="en" aria-pressed="false">English</button><button data-mode-button="both" aria-pressed="false">中英对照</button></div><div class="reading-tools"><button data-font-step="-1" aria-label="缩小正文字号">A−</button><button data-font-step="1" aria-label="增大正文字号">A＋</button><span class="tool-separator"></span>{downloads}<button id="print-article" aria-label="打印当前阅读模式">打印</button></div></div><div class="reading-layout"><aside class="article-toc"><details open><summary>文章目录 <span>CONTENTS</span></summary><nav aria-label="文章目录">{''.join(toc)}</nav></details><a class="toc-source" href="{escape(a['url'], quote=True)}" target="_blank" rel="noopener noreferrer">{publisher(a)} 原文 ↗</a></aside><article class="article-content"><div class="reader-note"><span class="note-zh">完整译文与原文逐段对应。图片、图注、表格和代码保留原文。</span><span class="note-en" lang="en">A complete reading edition. Figures, captions, tables and code are preserved from the source.</span></div><div class="column-headings"><span>中文译文</span><span lang="en">ENGLISH ORIGINAL</span></div>{''.join(rows)}<div class="article-end"><span class="end-symbol" aria-hidden="true">✳</span><p>— {ending} —</p><p>原文来自 {escape(a['publisher'])}，中文为非官方学习译文。<br><a href="{escape(a['url'], quote=True)}" target="_blank" rel="noopener noreferrer">查看原始出处 ↗</a></p></div>{related}<nav class="article-neighbors" aria-label="相邻资料">{neighbor}</nav></article></div></main><dialog id="image-dialog" aria-label="查看原图"><button class="close-image" aria-label="关闭原图">关闭 ×</button><img alt=""><p>点击空白处或按 Esc 关闭</p></dialog>'''
    extra = structured(reading_schema(SITE, a, dates), breadcrumb(SITE, [('首页', '/'), ('资料馆', '/library/'), (a['category'], topic_path), (a['title'], a['path'])]))
    extra += f'<meta property="article:published_time" content="{dates["published"]}"><meta property="article:modified_time" content="{dates["modified"]}"><meta property="article:section" content="{escape(a["category"], quote=True)}">'
    write('library/' + a['slug'] + '/index.html', layout(a['title'] + ' · 中文译文与原文', body, a['path'], description=a['description'], kind='article', extra_head=extra))


def listing(items):
    return [{key: a.get(key) for key in ['title', 'description', 'path', 'publisher', 'category', 'date', 'original_title']} for a in items]


def links(items):
    return '<ul class="reading-links">' + ''.join(f'<li><a href="{a["path"]}">{escape(a["title"])}</a><span>{escape(a.get("publisher", "6yuan"))}</span></li>' for a in items) + '</ul>'


def topic_pages(topics, articles, posts):
    lookup = {a['slug']: a for a in articles}
    index_desc = '围绕 AI Agent 架构、上下文工程、工具与技能、评测迭代、安全可靠性梳理关键问题，连接原始资料、中文译文与实践文章。'
    cards = ''.join(f'<section class="topic-card"><h2><a href="/topics/{t["slug"]}/">{escape(t["title"])}</a></h2><p>{escape(t["description"])}</p><a class="text-link" href="/topics/{t["slug"]}/">阅读专题 →</a></section>' for t in topics)
    body = f'<main id="main" class="topics-main"><header id="top"><p class="eyebrow">READING GUIDES</p><h1>Agent 开发专题</h1></header><div class="topic-grid">{cards}</div></main>'
    PUBLICATION.add('/topics/', topics)
    entries = [{'title': t['title'], 'path': '/topics/' + t['slug'] + '/'} for t in topics]
    extra = structured(collection(SITE, 'Agent 开发专题', index_desc, '/topics/', entries), breadcrumb(SITE, [('首页', '/'), ('专题导读', '/topics/')]))
    write('topics/index.html', layout('Agent 开发专题', body, '/topics/', description=index_desc, extra_head=extra))
    for t in topics:
        path = '/topics/' + t['slug'] + '/'
        selected = [a for a in articles + posts if a.get('category') == t['category']]
        PUBLICATION.add(path, {'topic': t, 'articles': listing(selected), 'references': listing([lookup[slug] for section in t['sections'] for slug in section['articles']])})
        sections = ''.join(f'<section class="topic-section" id="section-{i}"><h2>{escape(section["heading"])}</h2><p>{escape(section["text"])}</p>{links([lookup[slug] for slug in section["articles"]])}</section>' for i, section in enumerate(t['sections'], 1))
        nav = ''.join(f'<a href="/topics/{other["slug"]}/"'+(' aria-current="page"' if other['slug'] == t['slug'] else '')+f'>{escape(other["category"])}</a>' for other in topics)
        dates = PUBLICATION.pages[SITE['url'] + path]
        body = f'<main id="main" class="topics-main"><div class="article-breadcrumb" id="top"><a href="/library/">资料馆</a><span>／</span><a href="/topics/">专题导读</a></div><header class="topic-header"><p class="eyebrow">READING GUIDE</p><h1>{escape(t["title"])}</h1><p class="topic-intro">{escape(t["intro"])}</p><p class="publication-meta">资料馆编辑导读 · 更新 <time datetime="{dates["modified"]}">{dates["modified"][:10]}</time></p></header><nav class="topic-navigation" aria-label="其他专题">{nav}</nav><div class="topic-body">{sections}<section class="topic-section"><h2>本专题全部资料与文章</h2>{links(selected)}</section></div></main>'
        extra = structured(collection(SITE, t['title'], t['description'], path, selected), breadcrumb(SITE, [('首页', '/'), ('专题导读', '/topics/'), (t['title'], path)]))
        write(path.lstrip('/') + 'index.html', layout(t['title'], body, path, description=t['description'], extra_head=extra))


def personal_pages(posts):
    empty = '<div class="empty-writing"><span class="writing-mark" aria-hidden="true">§</span><div><h2>尚未发布文章</h2><p>这里将收录 6yuan 的原创文章。</p><a href="/library/">先去资料馆看看 ↗</a></div></div>'
    content = ''.join(f'<article class="personal-post"><h2><a href="{a["path"]}">{escape(a["title"])}</a></h2><p>{escape(a["description"])}</p></article>' for a in posts) if posts else empty
    body = f'<main id="main" class="personal-main"><section id="top"><p class="eyebrow">ESSAYS & NOTES <span>／</span> 6YUAN</p><h1>6yuan的文章<span class="title-dot">。</span></h1>{content}</section></main>'
    PUBLICATION.add('/', {'description': SITE['description'], 'posts': listing(posts)})
    extra = structured(collection(SITE, '6yuan的文章', SITE['description'], '/', posts))
    write('index.html', layout('6yuan的文章 · Agent 开发博客', body, '/', active='articles', extra_head=extra))
    # Static-preview fallback; production serves an exact 301 for the old listing URL.
    write('articles/index.html', layout('6yuan的文章', body, '/', active='articles', extra_head='<meta http-equiv="refresh" content="0;url=/">'))
    for a in posts:
        dates = PUBLICATION.add(a['path'], {'post': a, 'site': SITE, 'schema_version': 1}, published_at=a.get('published_at'))
        toc = ''.join(f'<a href="#{escape(b["id"], quote=True)}">{escape(plain(b["html"]))}</a>' for b in a['blocks'] if re.match(r'<h[23][ >]', b['html']))
        paragraphs = ''.join(f'<section class="{"shared" if re.match(r"<(pre|table|figure|img)[ >]", b["html"]) else "pair"}" id="{escape(b["id"], quote=True)}">{b["html"]}</section>' for b in a['blocks'])
        related = f'<div class="related-topic"><a href="/topics/{TOPIC_SLUGS[a["category"]]}/">{a["category"]}专题 →</a></div>' if a.get('category') in TOPIC_SLUGS else ''
        body = f'<main id="main" class="article-main"><div class="article-breadcrumb" id="top"><a href="/">6yuan的文章</a></div><header class="article-header"><h1>{escape(a["title"])}</h1><div class="article-meta"><span>6yuan</span><span>发布 <time datetime="{dates["published"]}">{dates["published"][:10]}</time></span><span>更新 <time datetime="{dates["modified"]}">{dates["modified"][:10]}</time></span></div></header><div class="reading-layout"><aside class="article-toc"><nav aria-label="文章目录">{toc}</nav></aside><article class="article-content">{paragraphs}{related}</article></div></main>'
        schema = {'@type': 'BlogPosting', '@id': SITE['url'] + a['path'] + '#article', 'url': SITE['url'] + a['path'], 'mainEntityOfPage': SITE['url'] + a['path'], 'headline': a['title'], 'description': a['description'], 'inLanguage': 'zh-CN', 'author': owner(SITE), 'publisher': owner(SITE), 'isPartOf': {'@id': SITE['url'] + '/#website'}, 'datePublished': dates['published'], 'dateModified': dates['modified'], 'image': SITE['url'] + '/assets/social-card.png'}
        extra = structured(schema, breadcrumb(SITE, [('6yuan的文章', '/'), (a['title'], a['path'])]))
        write(a['path'].lstrip('/') + 'index.html', layout(a['title'], body, a['path'], active='articles', description=a['description'], kind='article', extra_head=extra))


def feed(items):
    ordered = sorted(items, key=lambda a: PUBLICATION.pages[SITE['url'] + a['path']]['published'], reverse=True)
    rows = []
    for a in ordered:
        url = SITE['url'] + a['path']
        date = format_datetime(datetime.fromisoformat(PUBLICATION.pages[url]['published']))
        rows.append(f'<item><title>{escape(a["title"])}</title><link>{escape(url)}</link><guid isPermaLink="true">{escape(url)}</guid><description>{escape(a["description"])}</description><pubDate>{date}</pubDate><category>{escape(a.get("category", "6yuan的文章"))}</category></item>')
    write('feed.xml', f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel><title>6yuan博客 · 更新订阅</title><link>{SITE["url"]}/</link><description>{escape(SITE["description"])}</description><language>zh-CN</language><atom:link href="{SITE["url"]}/feed.xml" rel="self" type="application/rss+xml"/>{"".join(rows)}</channel></rss>')


def post_description(a):
    text = next((plain(b['html']) for b in a['blocks'] if b['html'].lstrip().startswith('<p')), a['title'])
    sentences = re.split(r'(?<=[。！？!?])', text)
    result = ''
    for sentence in sentences:
        if len(result + sentence) > 150:
            break
        result += sentence
    return result.strip() or f'6yuan 的原创文章《{a["title"]}》，记录 Agent 开发中的问题、分析与实践。'


def main():
    global PUBLICATION
    previous = os.environ.get('BLOG_PREVIOUS_MANIFEST', str(DIST / '.publication.json'))
    PUBLICATION = Publication(SITE['url'], previous)
    articles = sorted([json.loads(p.read_text()) for p in (ROOT / 'content/articles').glob('*.json')], key=lambda a: a.get('source_order', 999))
    overrides_path = ROOT / 'content/seo-overrides.json'
    overrides = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
    for a in articles:
        a.update(overrides.get(a['slug'], {}))
        a['path'] = '/library/' + a['slug'] + '/'
        if not overrides.get(a['slug'], {}).get('description'):
            a['description'] = f'{a["publisher"]}《{a["title"]}》的非官方中文译文，提供英文原文、图表与逐段对照阅读。'
    posts = [json.loads(p.read_text()) for p in sorted((ROOT / 'content/posts').glob('*.json'))]
    posts = [a for a in posts if not a.get('draft', False)]
    for a in posts:
        a['description'] = a.get('description') or post_description(a)
        a['path'] = '/articles/' + a['slug'] + '/'
    posts.sort(key=lambda a: a.get('published_at') or PUBLICATION.old.get(SITE['url'] + a['path'], {}).get('published') or PUBLICATION.now, reverse=True)
    topics = json.loads((ROOT / 'content/topics.json').read_text())
    if DIST.exists(): shutil.rmtree(DIST)
    shutil.copytree(ROOT / 'public', DIST)
    library(articles)
    for i, a in enumerate(articles): article(a, articles[i-1] if i else None, articles[i+1] if i+1 < len(articles) else None)
    personal_pages(posts)
    topic_pages(topics, articles, posts)
    write('404.html', layout('页面未找到', '<main id="main" class="not-found"><p class="eyebrow">404</p><h1 id="top">这一页暂时不存在。</h1><a href="/">返回首页 →</a></main>', '/404.html', noindex=True))
    write('sitemap.xml', PUBLICATION.sitemap())
    write('robots.txt', 'User-agent: *\nAllow: /\nSitemap: ' + SITE['url'] + '/sitemap.xml\n')
    feed(articles + posts)
    PUBLICATION.save(DIST / '.publication.json')
    write('build-info.json', json.dumps({'articles': len(articles), 'posts': len(posts), 'built_at': datetime.now(timezone.utc).isoformat(), 'site': SITE['url']}))
    print(f'Built {len(articles)} library articles, {len(posts)} posts and {len(topics)} topics → {DIST}')

if __name__ == '__main__': main()
