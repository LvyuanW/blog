'use strict';
(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const save = (key, value) => { try { localStorage.setItem(key, value); } catch {} };
  const read = key => { try { return localStorage.getItem(key); } catch { return null; } };
  const search = $('#library-search');
  if (search) {
    const rows = $$('.library-row'), list = $('#article-list'), source = $('#source-filter'), sort = $('#sort-order');
    let category = '';
    const params = new URLSearchParams(location.search);
    search.value = params.get('q') || '';
    if ([...source.options].some(o => o.value === params.get('source'))) source.value = params.get('source');
    if ($$('[data-category]').some(b => b.matches('button') && b.dataset.category === params.get('topic'))) category = params.get('topic');
    const update = (changeUrl = true) => {
      const terms = search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
      let count = 0;
      for (const row of rows) {
        row.hidden = !(terms.every(t => row.dataset.search.includes(t)) && (!category || row.dataset.category === category) && (!source.value || row.dataset.publisher === source.value));
        if (!row.hidden) count++;
      }
      $$('.topic-filters button').forEach(b => { const active = b.dataset.category === category; b.classList.toggle('active', active); b.setAttribute('aria-pressed', String(active)); });
      $('#result-count').textContent = `${category || '全部资料'} · ${count} 篇`;
      $('#no-results').hidden = count > 0;
      const ordered = [...rows];
      if (sort.value !== 'collection') ordered.sort((a, b) => (a.dataset.date || '').localeCompare(b.dataset.date || '') * (sort.value === 'newest' ? -1 : 1));
      ordered.forEach(r => list.append(r));
      if (changeUrl) {
        const query = new URLSearchParams();
        if (search.value.trim()) query.set('q', search.value.trim());
        if (category) query.set('topic', category);
        if (source.value) query.set('source', source.value);
        history.replaceState(null, '', location.pathname + (query.size ? '?' + query : '') + location.hash);
      }
    };
    search.addEventListener('input', () => update()); source.addEventListener('change', () => update()); sort.addEventListener('change', () => update());
    $$('.topic-filters button').forEach(b => b.addEventListener('click', () => { category = b.dataset.category; update(); }));
    $('#reset-filters').addEventListener('click', () => { search.value = ''; source.value = ''; category = ''; update(); search.focus(); });
    update(false);
  }
  const reader = $('[data-reader]');
  if (!reader) return;
  const buttons = $$('[data-mode-button]');
  const setMode = (mode, keepPosition = false) => {
    if (!['zh', 'en', 'both'].includes(mode)) mode = 'zh';
    const anchor = keepPosition ? $$('.pair,.shared', reader).find(el => el.getBoundingClientRect().bottom > 95) : null;
    const offset = anchor?.getBoundingClientRect().top;
    reader.dataset.mode = mode;
    document.body.classList.toggle('reading-both', mode === 'both');
    document.documentElement.lang = mode === 'en' ? 'en' : 'zh-CN';
    buttons.forEach(b => { const active = b.dataset.modeButton === mode; b.classList.toggle('active', active); b.setAttribute('aria-pressed', String(active)); });
    save('6yuan:reading-mode', mode);
    if (anchor && window.scrollY > 500) window.scrollBy({ top: anchor.getBoundingClientRect().top - offset, behavior: 'instant' });
  };
  buttons.forEach(b => b.addEventListener('click', () => setMode(b.dataset.modeButton, true)));
  setMode(new URLSearchParams(location.search).get('lang') || read('6yuan:reading-mode') || 'zh');
  let font = Math.max(17, Math.min(25, Number(read('6yuan:font-size')) || 20));
  const setFont = () => {
    document.documentElement.style.setProperty('--reading-size', font + 'px');
    save('6yuan:font-size', String(font));
    $$('[data-font-step]').forEach(b => b.disabled = Number(b.dataset.fontStep) < 0 ? font <= 17 : font >= 25);
  };
  $$('[data-font-step]').forEach(b => b.addEventListener('click', () => { font = Math.max(17, Math.min(25, font + Number(b.dataset.fontStep))); setFont(); })); setFont();
  $('#print-article').addEventListener('click', () => window.print());
  const toc = $('.article-toc details'); if (innerWidth <= 760 && toc) toc.open = false;
  const links = $$('.article-toc nav a');
  const targets = links.map(link => document.getElementById(decodeURIComponent(link.hash.slice(1)))).filter(Boolean);
  const progress = $('#reading-progress-bar');
  let pending = false;
  const onScroll = () => {
    pending = false;
    const content = $('.article-content'); const rect = content.getBoundingClientRect();
    progress.style.width = Math.max(0, Math.min(100, (100 - rect.top) / Math.max(1, rect.height - innerHeight + 150) * 100)) + '%';
    let current = targets[0]; for (const t of targets) if (t.getBoundingClientRect().top < 150) current = t;
    links.forEach(link => { const active = current && link.hash === '#' + current.id; link.classList.toggle('current', Boolean(active)); if (active) link.setAttribute('aria-current', 'location'); else link.removeAttribute('aria-current'); });
  };
  addEventListener('scroll', () => { if (!pending) { pending = true; requestAnimationFrame(onScroll); } }, { passive: true });
  addEventListener('resize', onScroll); onScroll();
  const dialog = $('#image-dialog'); let lastFocus;
  $$('.shared img').forEach(img => {
    img.tabIndex = 0; img.setAttribute('role', 'button'); img.setAttribute('aria-label', '放大图片' + (img.alt ? '：' + img.alt : ''));
    const open = () => { lastFocus = img; $('img', dialog).src = img.src; $('img', dialog).alt = img.alt; dialog.showModal(); document.body.style.overflow = 'hidden'; };
    img.addEventListener('click', open); img.addEventListener('keydown', e => { if (['Enter', ' '].includes(e.key)) { e.preventDefault(); open(); } });
  });
  const close = () => dialog.close(); $('.close-image', dialog).addEventListener('click', close);
  dialog.addEventListener('click', e => { if (e.target === dialog) close(); });
  dialog.addEventListener('close', () => { document.body.style.overflow = ''; lastFocus?.focus({ preventScroll: true }); });
  document.addEventListener('click', e => { $$('.download-menu[open]').forEach(menu => { if (!menu.contains(e.target)) menu.open = false; }); });
})();
