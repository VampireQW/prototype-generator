# 首页本地依赖

首页直接加载本地工具类 CSS 和图标字体，不需要联网编译。

| 依赖 | 固定版本 | 来源 | 许可证 |
|---|---|---|---|
| Tailwind CSS | 3.4.17 | https://cdn.tailwindcss.com/3.4.17 | MIT，见 tailwind-LICENSE.txt |
| Font Awesome Free | 6.4.0 | https://www.npmjs.com/package/@fortawesome/fontawesome-free/v/6.4.0 | 字体 SIL OFL 1.1、代码 MIT、图标 CC BY 4.0，见 fontawesome/LICENSE.txt |

`home-utilities.css` 由 `tools/build_home_css.py` 使用仓库内固定版本运行时从首页源码预编译；首页本身不加载 Tailwind 运行时。Font Awesome 的 CSS 与三个 WOFF2 文件为原发行版资产。

2026-10-10：tailwind-runtime.js 为上述固定版本运行时的本地副本，仅用于隔离项目封面渲染；生产首页继续加载预编译工具类 CSS。许可证沿用 tailwind-LICENSE.txt。

2026-10-11：首页构建工具也读取上述本地副本，不再下载 CDN。根目录构建产物使用 `/dist/`、`/build/` 忽略，第三方 Markdown 包的必要 `dist` 运行资源纳入源码交付。
