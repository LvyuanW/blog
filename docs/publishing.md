# 发布与维护指南

日常工作是新增或修改内容、在本地核验、推送 `main`，再执行发布脚本。无需为每篇文章手工维护 sitemap、RSS 或搜索提交通知。

## 新增资料馆文章

继续使用 `content/articles/*.json` 的双语结构。保留稳定的 `slug`、中英文标题、来源 URL、来源署名、源文日期、分类和 `blocks`；原文日期不要改为本站收录日期。图片等共享块用 `preserve: true` 和 `en`，翻译块包含 `en`、`zh`。

可用 `scripts/import_library.py` 从翻译工作目录导入，命令见 README。编辑标题放在 `content/title-overrides.json`，避免下次导入覆盖。

`content/seo-overrides.json` 以**网站 slug** 为键，可独立优化描述与作者，例如：

```json
{
  "example-reading": {
    "description": "用完整中文句子概括这篇资料讨论的问题、方法与边界，并说明这是原文的中文译文。",
    "authors": [
      {"@type": "Person", "name": "原文明确署名的作者"}
    ]
  }
}
```

多人作者逐人列出；组织或团队署名用 `Organization`。不要把致谢名单视为作者名单，也不要补写无法核实的身份。摘要页应明确只是摘要。

未配置覆盖的新资料仍可发布：构建器按标题和来源生成保守的译文描述，并依据现有署名解析个人、多人或组织；没有个人署名时保留来源组织。人工摘要用于提高准确性和可读性，不是发布前置条件。

## 新增原创文章

在 `content/posts/` 新建 JSON，建议文件名与 `slug` 相同。以下只是格式示例，不是待发布文章：

```json
{
  "slug": "agent-eval-notes",
  "title": "文章标题",
  "description": "可选：准确概括文章的问题、方法与结论。",
  "category": "评测与改进",
  "draft": true,
  "blocks": [
    {"id": "intro", "html": "<p>正文开头。</p>"},
    {"id": "topic", "html": "<h2>小节标题</h2>"},
    {"id": "details", "html": "<p>小节正文。</p>"}
  ]
}
```

- `slug`、`title`、非空 `blocks` 必填。slug 使用小写字母、数字及连字符，发布后尽量保持稳定；页面地址为 `/articles/<slug>/`。
- `description` 可省略，构建器优先从开头段落提取完整句子，无法提取时使用保守描述。
- `category` 可省略；填写时只能使用：基础与架构、上下文工程、工具与技能、评测与改进、安全与可靠性。对应专题的“全部资料与文章”列表会自动收录，无须手动加链接。
- `draft` 可省略，默认 `false`。写作期间设为 `true`；准备发布时改为 `false` 或删除该字段。草稿不进入页面、sitemap、RSS 或搜索通知。
- 每个块的 `id` 必须唯一，以字母开头，后续可用字母、数字、下划线或连字符。`html` 使用正文 HTML；二、三级标题会生成目录。图片等本地资源放入 `public/`，并使用对应站点路径，如 `/media/example.png`。不要加入脚本、事件处理器或 iframe。
- `published_at` 可省略。若需要保留已经公开发表的真实历史日期，使用带时区且不晚于当前时间的 ISO 日期时间，例如 `2026-10-03T12:00:00+08:00`。它不是预约发布字段。

## 核验与上线

在仓库根目录执行：

```sh
python3 scripts/validate.py
python3 scripts/build.py
python3 scripts/verify_seo.py
python3 -m http.server 4173 --directory dist
```

检查正文、图片、标题和链接。通过后提交并推送 `main`，然后执行：

```sh
ssh root@8.209.199.197 'bash /opt/6yuan-blog/deploy/publish.sh'
```

发布脚本只快进更新代码，依次运行 `validate.py`、`build.py`、`verify_seo.py`，通过后原子切换线上版本，再运行 `notify_search.py`。内容或 SEO 验证失败时不会切换版本；搜索通知失败会留下重试记录，不回滚已经上线的内容。

每次构建自动生成标题、描述、canonical、分享元信息、结构化数据、专题列表、sitemap 和 RSS。资料的结构化数据区分英文原作与本站译文；原创文章使用本站作者身份。专题的分类列表自动更新，导读文字与精选阅读顺序仍由 `content/topics.json` 编辑维护。

## 发布时间与更新时间

生成目录中的 `.publication.json` 保存页面内容哈希、首次公开时间 `published` 和更新时间 `modified`。生产构建比较**上一次已发布版本**的清单，沿用首次公开时间，只有正文或相关内容元数据实质变化时才更新修改时间。不要手工修改生成清单或用重新构建来“刷新”日期。

首次发布的原创文章，未指定 `published_at` 时使用本次公开发布时间；Git 中保存草稿的时间不是公开日期。本地预览也不应提前确定生产发布日期。已公开文章后续修订应保留首次公开日期。

本轮首次建立清单时，已有资料以 Git 中的首次导入记录作为收录时间基线；此后新增资料使用首次生产发布的时间。原文的发布日期、更新日期和 PDF 创建日期始终单独保留。

本地构建默认沿用现有 `dist/.publication.json`。如需与保存的发布清单比较，可显式指定：

```sh
BLOG_PREVIOUS_MANIFEST=/path/to/previous/.publication.json python3 scripts/build.py
```

`/sitemap.xml` 的修改日期来自发布清单。`/feed.xml` 在每次构建时更新，收录公开原创文章与资料馆文章；文章的首次公开日期不会因重复构建变化。

## 搜索通知与重试

IndexNow 只在内容已上线后发送新增、修改或删除的规范 URL；无变化时不发送请求。服务器持久文件为：

| 文件 | 用途 |
| --- | --- |
| `/var/www/6yuan/search/indexnow-state.json` | 已通知版本、待重试 URL 和通知结果 |
| `/var/www/6yuan/search/indexnow-key.txt` | IndexNow 验证 key 的源文件 |

两者不进入 Git。发布流程提供协议所需的公开验证文本；不要把状态文件复制到公开目录。重试使用**当前线上版本**的清单，不能提交尚未上线的本地预览。

失败通知会在下次发布时自动重试。也可在服务器运行：

```sh
python3 /opt/6yuan-blog/scripts/notify_search.py \
  --manifest /var/www/6yuan/current/.publication.json \
  --state /var/www/6yuan/search/indexnow-state.json \
  --key-file /var/www/6yuan/search/indexnow-key.txt
```

在同一命令后添加 `--dry-run`，只显示待通知变更，不发网络请求，也不写文件。请求被接收并不代表 URL 已被抓取或收录；不要删除状态文件来人为制造全量更新。

## 站长验证与效果观测

Google 不使用 IndexNow。站点所有者需要一次性在 Search Console 验证站点并提交 `https://blog.wanglvyuan.com/sitemap.xml`；后续内容变化由自动更新的 sitemap 提供。Google Indexing API 不是面向普通博客文章的通用提交入口，本项目不使用它来替代这一流程。

需要 HTML 验证时，在 `site.json` 现有配置中添加对应服务提供的**公开验证标记**：

```json
{
  "google_site_verification": "服务提供的公开验证标记",
  "bing_site_verification": "服务提供的公开验证标记"
}
```

这是字段示例，不要用它覆盖完整的 `site.json`，也不要填写账户密码、访问令牌或 API 密钥。重新发布后，再到相应站长平台完成验证；这些字段本身不会代替账户验证或提交操作。

这里的 SEO/GEO 机制帮助搜索与问答系统发现内容、辨认主题和出处，不保证收录、排名或 AI 引用。IndexNow 通知不等于 AI 已读取或引用文章。应通过站长平台的索引与检索数据，以及实际回答中的引用链接持续观察效果；维护准确内容、清晰出处和有效链接，比添加无法验证效果的标记更重要。
