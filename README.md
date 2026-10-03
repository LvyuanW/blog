# 6yuan · 文章与资料馆

个人博客：<https://blog.wanglvyuan.com>。首页收录 **6yuan 的原创文章**；**资料馆**提供技术资料的中文译文、英文原文与逐段对照；**专题导读**按问题组织相关阅读。

## 本地运行

构建使用 Python 3.10 或更高版本，无需 Node.js 或构建框架。

```sh
python3 scripts/validate.py
python3 scripts/build.py
python3 scripts/verify_seo.py
python3 -m http.server 4173 --directory dist
```

访问 <http://localhost:4173>。`dist/` 是生成目录，不纳入 Git。新增内容格式、日期规则和搜索通知操作见 [发布与维护指南](docs/publishing.md)。

## 内容结构

| 路径 | 用途 |
| --- | --- |
| `content/articles/*.json` | 资料馆现有双语格式：正文、来源、源文日期及段落对应关系 |
| `content/posts/*.json` | 原创文章；`draft: true` 的内容不生成公开页面 |
| `content/seo-overrides.json` | 按资料 `slug` 人工优化摘要和作者署名；未覆盖的新资料有自动回退 |
| `content/title-overrides.json` | 资料的编辑标题，重新导入时保留 |
| `content/topics.json` | 五个专题的导读与推荐；分类列表自动收录对应文章 |
| `public/media/`、`public/downloads/` | 原始图片、公式及已有 PDF |
| `public/assets/` | 样式、交互、来源标志、字体和分享图片 |
| `site.json` | 站点名称、域名、仓库及可选站长验证标记 |

双语块的 `preserve: true` 表示图片、图注、表格或代码保留原文；其余块同时包含 `en` 和 `zh`。从已校验的翻译目录导入时需要 `lxml`，正常构建不需要：

```sh
python3 scripts/import_library.py /path/to/article_translation --pdf-dir /path/to/output/pdf
python3 scripts/validate.py
python3 scripts/build.py
python3 scripts/verify_seo.py
```

导入读取主 manifest 与 `manifest-extra-*.json`，清理脚本和事件处理器，并将图片转为本地资源。原始网页存档、机器路径和中间文件不进入发布内容。

## 发布与搜索发现

核验并推送 `main` 后，发布命令不变：

```sh
ssh root@8.209.199.197 'bash /opt/6yuan-blog/deploy/publish.sh'
```

脚本依次执行 **验证 → 构建 → SEO 检查 → 原子上线 → 搜索通知**。每次构建自动维护页面元信息、结构化数据、专题列表、`/sitemap.xml` 和 `/feed.xml`。发布时间以已发布版本的 `.publication.json` 为依据，重复构建不会把所有文章伪装成新发布或新修改。

上线后，IndexNow 按内容变化通知支持该协议的搜索服务；失败记录会保留，供下次发布或手动重试。Google 不使用 IndexNow，站点所有者仍需一次性完成 Search Console 验证并提交 sitemap。通知成功不保证收录、排名或 AI 引用；引用表现需要另行观测。

生产环境为 Ubuntu + Nginx，静态站点不需要后台进程：

- Git checkout：`/opt/6yuan-blog`
- 发布版本：`/var/www/6yuan/releases/`；当前版本：`/var/www/6yuan/current`
- 搜索通知状态与验证 key 源文件：`/var/www/6yuan/search/`，不进入 Git
- Nginx：`/etc/nginx/sites-available/6yuan-blog`
- HTTPS：Let's Encrypt / Certbot，系统定时器续期

历史版本保留以便回滚。`deploy/nginx.conf` 是首次安装的 HTTP 模板，不应直接覆盖生产环境中由 Certbot 增补的 HTTPS 配置。

## 字体与来源

英文优先使用系统 **Times New Roman**。中文使用自托管的 [朱雀仿宋](https://github.com/TrionesType/zhuque)，保留系统仿宋回退；SIL Open Font License 1.1 授权文本见 `public/assets/fonts/OFL-Zhuque.txt`。

来源标志的出处记录在 `public/assets/logos/sources.json`，仅用于识别来源，不表示合作或背书。原文、图表及标志的权利归各作者；中文为非官方译文，每篇保留原始出处与署名。AutoHarness 页面仅收录论文摘要与文献信息，不宣称收录论文全文。
