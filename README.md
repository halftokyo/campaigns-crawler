# JP Campaigns Crawler

面向日本官方站点与可靠聚合源的活动抓取器：证券开户、信用卡入会、支付/钱包与地方官方活动等。抓取公开 HTML/RSS/JSON 内容，统一为结构化记录，并可选 Upsert 到 Notion。

- 公开数据库（Notion）：https://belazy.notion.site/29fb57a2d45e802b91a7e337b6183efa?v=29fb57a2d45e80f39992000cdbd92476

## 功能概览
- 配置化抓取：来源在 `configs/sources.json`，支持 html/rss/json、CSS 选择器、关键词过滤。
- 合规与稳健：检查 robots.txt、温和频率、默认关键词过滤（新規/口座開設/ポイント…）。
- 标准化输出：写入 `output/campaigns.json`，带 `external_id` 去重。
- 自动化：GitHub Actions 每周日（UTC）运行，可手动触发。
- 可选 Notion Upsert：设置环境变量即可将记录同步至你的 Notion 数据库。

## 目录结构
```
jp-campaigns-crawler/
  configs/
    sources.json            # 示例来源配置（部分 URL/选择器需校验）
  output/
    .gitkeep
  src/campaigns/
    __init__.py
    main.py                 # CLI 入口
    models.py               # 数据模型
    utils.py                # 文本/日期/ID 工具
    fetch.py                # 请求+robots 校验
    parser.py               # HTML/RSS/JSON 解析与过滤
    pipeline.py             # 主流程：加载配置->抓取->标准化->写文件/Notion
    notion_client.py        # 可选：Notion upsert
  .github/workflows/
    crawl.yml               # 定时与手动触发工作流
  requirements.txt
  .gitignore
  README.md
```

## 快速开始（本地）
1) Python 3.11+

2) 安装依赖
```
pip install -r requirements.txt
```

3) 运行抓取（默认读取 `configs/sources.json`）
```
PYTHONPATH=src python -m campaigns.main --config configs/sources.json --out output/campaigns.json
```

4) 输出
`output/campaigns.json` 包含统一结构的记录：
```
{
  "name": "楽天証券 新規口座開設キャンペーン",
  "provider": "楽天証券",
  "category": "证券开户",
  "reward_type": "积分",
  "reward_value": "最大10000P",
  "deadline": "2025-10-31",
  "source_url": "https://...",
  "external_id": "rakuten-sec:..."
}
```

可选参数：
- `--no-notion` 跳过 Notion upsert（默认尝试 upsert）。
- `--valid-within-days N` 仅保留未来 N 天内截止（含当天/截止日）的记录（适合周报/周度抓取）。
- `--require-deadline` 丢弃无法解析截止日期的记录。
- `--active-only` 仅保留当前未过期（截止日>=今天）的记录（忽略 N 天窗口）。
\- `--weekly-new-and-archive` 周度模式：仅 upsert 最近 7 天“新增发现”的活动，并将已过期的活动在 Notion 标记为失效/归档；需配合 `--state-file` 使用。
\- `--state-file <path>` 指定状态文件路径（默认 `output/state.json`），用于记录 first_seen/last_seen 与归档状态。

## Notion（可选）
设置环境变量后，自动 upsert 到你的 Notion 数据库：
- `NOTION_TOKEN`：Notion 集成密钥（Internal Integration Token）。将数据库“分享到”该集成。
- `NOTION_DATABASE_ID`：数据库 ID（或使用 `NOTION_DATABASE_URL` 自动解析）。
- 可选：`NOTION_DATABASE_URL`：数据库或公开页面 URL（例如你提供的公开链接），程序会自动提取 32 位 ID。
  - 当前数据库链接：`https://belazy.notion.site/29fb57a2d45e802b91a7e337b6183efa?v=29fb57a2d45e80f39992000cdbd92476`
- 可选：属性映射（如你的数据库字段名不同）：
  - `NOTION_PROP_MAP`：JSON 映射，如 `{"name":"标题","provider":"发起方"}`
  - 或分别设置：`NOTION_PROP_NAME`、`NOTION_PROP_PROVIDER`、`NOTION_PROP_CATEGORY`、`NOTION_PROP_REWARD_TYPE`、`NOTION_PROP_REWARD_VALUE`、`NOTION_PROP_DEADLINE`、`NOTION_PROP_SOURCE_URL`、`NOTION_PROP_EXTERNAL_ID`、`NOTION_PROP_LASTCHECKED`、`NOTION_PROP_STATUS`

数据库字段建议（默认字段名如下，如不同请用属性映射覆盖）：
- Title: `Name`
- Rich text: `Provider`, `Category`, `Reward Value`, `External ID`
- Select: `Reward Type`, `Status`（建议包含：有效/需人工确认/失效）
- URL: `Source URL`
- Date: `Deadline`, `LastChecked`

### Notion 视图设置（日历）
- 在数据库页面左上角 `⋯` → `Open as full page` 全页打开。
- 新建视图：`New view` → `Calendar`，Calendar by 选择 `Deadline`。
- 过滤（Filter）：
  - `Status` is `有效` OR `需人工确认`（排除 `失效`）。
  - 可选：`Deadline` is within next `7` days（每周视图）或 next `30` days（月视图）。
- 排序（Sort）：按 `Deadline` 升序。
- 卡片属性（Card properties）：勾选 `Provider`、`Reward Value`、`Category`、`Reward Type`、`Source URL`。
- 若你的字段名与默认不同，可通过仓库 Secrets 设置 `NOTION_PROP_MAP` 对应后再按你的字段名配置视图。

## GitHub Actions
工作流在每周日（UTC）运行，默认使用周度模式：只 upsert 最近一周新增、并归档已过期；同时产出 `campaigns.json`、`new_this_week.json` 与 `expired_to_archive.json`。

将本项目推送到你的 GitHub 仓库（示例）：
```
git init
git add .
git commit -m "init: jp campaigns crawler"
git branch -M main
git remote add origin git@github.com:<your-username>/<your-repo>.git
git push -u origin main
```

## 重要说明
- `configs/sources.json` 中多数来源标记了 `"needs_verification": true`，请根据真实页面校验 URL 与选择器后将其置为 false 或移除该字段。
- 我们默认仅扫描与关键词相关的链接/卡片，减少无关抓取量。
- 若来源提供 RSS/JSON，优先用之；否则回退 HTML 解析。

## 扩展来源
向 `configs/sources.json` 添加一项：
```
{
  "id": "rakuten-sec",
  "provider": "楽天証券",
  "category": "证券开户",
  "source_type": "html",
  "url": "https://www.rakuten-sec.co.jp/web/campaign/",
  "selectors": {"list": "a, .card", "title": "a", "link": "a", "date": ".date, time", "reward": ".reward, .amount"},
  "include_keywords": ["新規", "口座開設", "キャンペーン", "ポイント", "キャッシュバック"],
  "exclude_keywords": ["終了", "終了しました"],
  "needs_verification": true
}
```

## 许可与合规
- 仅抓取公开可访问内容；遵守 robots.txt 与站点条款。
- 不采集任何个人数据；所有链接指向官方页面。
