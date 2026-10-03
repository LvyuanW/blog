# 6yuan · 文章与资料馆

个人博客：<https://blog.wanglvyuan.com>

两个板块：**6yuan的文章**（暂未发布内容）与 **资料馆**（原始技术资料、中文译文及逐段对照阅读）。

## 本地运行

构建只需要 Python 3.10 或更高版本，不需要 Node.js 或构建框架。

```sh
python3 scripts/validate.py
python3 scripts/build.py
python3 -m http.server 4173 --directory dist
```

访问 <http://localhost:4173>。构建产物 `dist/` 不纳入 Git。

## 内容结构

- `content/articles/*.json`：完整中英文正文、来源、发布日期、主题及段落对应关系。
- `public/media/`：按内容哈希命名的原始图片与公式，避免重复存储。
- `public/downloads/`：已有的中英文 PDF，以及原版 PDF。
- `public/assets/`：样式、交互代码、来源标志和仿宋网页字体。
- `site.json`：站点名称、域名和仓库地址。

文章块中的 `preserve: true` 表示图表、图注、代码或其他应保持原文的内容。其余块同时包含 `en` 和 `zh`；两种语言可以切换或对照。搜索和筛选在浏览器本地运行，无用户追踪或第三方脚本。

从已校验的翻译工作目录导入（仅此步骤需要 `lxml`）：

```sh
python3 scripts/import_library.py /path/to/article_translation --pdf-dir /path/to/output/pdf
python3 scripts/validate.py
python3 scripts/build.py
```

导入脚本读取主 manifest 和 `manifest-extra-*.json`，只收录已完整翻译的文章，移除脚本与事件处理器，将图片转为本地静态资源。原始 HTML 存档、机器路径和中间文件不会进入发布内容。

## 部署

生产环境使用 Ubuntu + Nginx，静态站点不需要后台进程。

- Git checkout：`/opt/6yuan-blog`
- 发布目录：`/var/www/6yuan/releases/`
- 当前版本软链接：`/var/www/6yuan/current`
- Nginx：`/etc/nginx/sites-available/6yuan-blog`
- 域名：`blog.wanglvyuan.com`
- HTTPS：Let's Encrypt / Certbot，系统定时器自动续期。

后续发布：先在本地核验内容并推送 `main`，再运行：

```sh
ssh root@8.209.199.197 'bash /opt/6yuan-blog/deploy/publish.sh'
```

发布脚本仅快进拉取，先验证、构建，再原子切换软链接。历史发布目录保留，可将 `current` 指向上一版本回滚。`deploy/nginx.conf` 是首次安装的 HTTP 模板；生产 HTTPS 配置由 Certbot 增补，不应直接覆盖已有证书配置。

## 字体与来源

英文优先使用系统 **Times New Roman**。中文使用自托管的 [朱雀仿宋](https://github.com/TrionesType/zhuque)，并保留系统仿宋回退。字体依 SIL Open Font License 1.1 使用，授权文本见 `public/assets/fonts/OFL-Zhuque.txt`。

来源标志取自各来源网站或用户提供的网页存档，出处记录在 `public/assets/logos/sources.json`。标志仅用于识别来源，不表示合作或背书。原文、图表及各项标志权利归原作者；中文为非官方学习译文。每篇保留原始出处与署名。AutoHarness 所提供存档为论文摘要页，资料馆明确标注摘要，不宣称收录论文全文。
