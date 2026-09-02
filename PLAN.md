# game-rank-monitor 改造计划

> 基于 [alkanaks56/top-games](https://github.com/alkanaks56/top-games)（导入于 2026-09-02）改造。
> 目标：**双商店（App Store + Google Play）游戏榜单监控系统**，聚焦 casual & action（射击）品类。

---

## 1. 目标能力

| 能力 | 说明 |
|---|---|
| 每日榜单 | 双平台 × {casual, action} × 免费榜（可扩展 paid/grossing） |
| 项目详情 | 图标、简介（截断存储）、游戏截图、开发公司、评分 |
| 排名历史 | 每日快照 diff，进出榜/升降信号，dashboard sparkline |
| 公司维度 | 按 developer 聚合；支持 watch 名单，日报推送关注公司动态 |
| 交付 | GitHub Actions 定时采集（海外 runner 解决 Play 访问）+ GitHub Pages 静态 dashboard + Slack 日报 |

## 2. 上游现状盘点（已通读全部 17 个模块）

**可直接复用：**
- 多数据集机制：`config.datasets()` 已支持 countries × genres 交叉积（现默认 5 国 × 17 类型）
- 信号系统：`signals.refresh()` 出 new_entry/debut/exit/climb/fall/new_release 事件
- 静态站点生成：`staticgen.py` + `static_template.py`（含榜单、筛选、sparkline）
- Slack 日报/斜杠命令 + Cloudflare Worker 分享层（worker/）
- GitHub Actions workflow（多窗口 cron + 防重发 + DB 回写 + Pages 部署）
- `bundle_id` 字段已存在，且 iOS bundleId == Play 包名 → **天然跨平台对齐键**

**缺口：**
1. 无 Google Play 数据源（仅 dashboard 有"到 Play 搜索"的链接）
2. `apps` 表无截图列；`description` 有列但被刻意置空（防 DB 膨胀）
3. 无公司维度页面/聚合
4. 无 platform 概念，`snapshots.chart` 单一命名空间
5. `data/topgames.db`（14MB）是作者 puzzle 数据，需清空重来

## 3. 关键设计决策

### D1 — Play 应用 ID 融合（避免改复合主键）
现有 `apps.app_id INTEGER PRIMARY KEY` 贯穿全部 SQL，改复合键风险大。
**方案**：Play 应用以 `int(md5("play:" + package)[:8], 16)` 生成 64 位整数 id；
新增列 `platform TEXT DEFAULT 'ios'`、`store_id TEXT`（iOS=trackId 字符串，Play=包名）。
跨平台同一游戏通过已有的 `bundle_id` 列关联（两平台值相同）。

### D2 — 榜单命名空间
`snapshots` / `events` 各加 `platform` 列（`'ios'`/`'play'`，默认 `'ios'`，ALTER TABLE 平滑迁移）。
chart 取值：iOS 沿用 `topfreeapplications`；Play 用 `top_free` / `top_paid` / `grossing`。
查询一律 `WHERE platform=? AND chart=?`。Play 的 genre 不落 genre_id（Apple 专属），
以 `datasets` slug（`us-play-casual`）区分，genre 语义由配置层承载。

### D3 — Play 数据源选型
**主选**：Python 包 [`google-play-scraper`](https://pypi.org/project/google-play-scraper/)（纯 Python，JoMingyu 维护）：
- `list({category: GAME_CASUAL|GAME_ACTION, collection: TOP_FREE, num, country, lang})` → 榜单
- `app(appId)` → 详情（icon/screenshots/description/developer/ratings）
- 破坏"纯标准库"原则 → 接受，在 workflow 加 `pip install`；play.py 内做 import 失败降级（模块缺失只跳过 Play，不炸 iOS 流程）
**备选**（若包失效）：HTTP 解析 Play 集群页 / SerpApi 付费 API（接口抽象为 `play.py` 内部细节）

### D4 — 详情字段策略（防 DB 膨胀）
- `screenshots TEXT`（JSON 数组，取前 5 张）
- `description` 截断至 1500 字符存储
- DB 已随 git 提交，prune 机制沿用（180 快照 / 120 天事件）

### D5 — 公司维度
- 不建独立表，用 SQL 聚合 `GROUP BY artist`（iOS）/ `developer`（Play）
- 配置 `watch_developers: [...]`，digest 新增 "关注公司" 板块（上榜游戏数/升降）
- dashboard 新增 `/companies` 索引页 + 公司详情页（含跨平台同款合并视图，走 bundle_id）

## 4. 工作分解

### M1 — 数据层双平台化（核心，先行）
| # | 任务 | 文件 |
|---|---|---|
| 1.1 | store schema 迁移：apps + platform/store_id/screenshots；snapshots/events + platform | `store.py` |
| 1.2 | iOS normalize()：存 screenshotUrls、打开 description（截断） | `sources.py` |
| 1.3 | 新建 Play 数据源：fetch_chart / enrich（list + app 详情），对齐 sources 接口 | `topgames/play.py`（新） |
| 1.4 | config：datasets 增加 platform 维度；PLAY_GENRES 映射；我方目标配置（us + casual/action + 双平台） | `config.py` |
| 1.5 | signals.refresh 分派双平台；快照对比逻辑平台无关化 | `signals.py` |
| 1.6 | 清空作者旧 DB；`python -m topgames init` 生成我方 config | `config.json` |
- **验收**：`refresh` 后 DB 中双平台 casual/action 各有 ≥1 个快照；iOS 流程零回归（tests_signals.py 通过）

### M2 — 公司维度 + 详情补全
| # | 任务 |
|---|---|
| 2.1 | watch_developers 配置 + digest 板块 |
| 2.2 | 公司聚合查询函数（上榜数/最好名次/总评分量/近 7 天动向） |
| 2.3 | Play 详情全量落库（icon/screenshots/developer/description） |
- **验收**：日报含关注公司段落；`/companies` 数据接口可用

### M3 — Dashboard 升级
| # | 任务 |
|---|---|
| 3.1 | 平台切换 tab（iOS/Play/合并） |
| 3.2 | App 行展开：截图轮播 + 简介 + 双平台对照（bundle_id join） |
| 3.3 | 公司页：作品列表 + 排名趋势 |
| 3.4 | 首页信号流标注平台徽章 |
- **验收**：Pages 构建产物含上述三块，浏览器验证

### M4 — 部署上线
| # | 任务 |
|---|---|
| 4.1 | workflow：`pip install google-play-scraper`；cron 调至北京时间早 8 点（UTC 0 点 + 备用窗口） |
| 4.2 | Slack secrets（TOPGAMES_SLACK_WEBHOOK）+ Pages 开启 |
| 4.3 | config.json 指向自己的 pages_url/worker_url；仓库改名 game-rank-monitor |
| 4.4 | README 重写（中文，说明 fork 来源与差异） |
- **验收**：连续 2 天定时运行成功，Slack 收到日报，dashboard 更新

## 5. 风险与对策

| 风险 | 概率 | 对策 |
|---|---|---|
| google-play-scraper 失效/被限流 | 中 | play.py 单点封装；失败不阻断 iOS；必要时切 SerpApi |
| 本机无 Google 网络 | 确定 | 本地只测 iOS 路径 + Play 单测用 fixture；Play 端到端在 Actions 验证 |
| Apple 旧 RSS 弃用 | 低 | 上游注释已定位唯一替换函数 `sources.fetch_chart` |
| DB 随截图/简介膨胀 | 中 | 截图仅存 URL（不存图）、简介截断、prune 沿用，监控单次 commit 增量 |
| actions cron 延迟 | 确定 | 沿用上游 4 窗口 + digest --if-due 判重 |

## 6. 测试策略

- 单测（本地可跑，无网络）：Play 响应 fixture → 解析/入库/信号；沿用 tests_signals.py 风格
- 集成（Actions）：workflow 加 `python -m topgames verify`（扩展 verify.py 检查双平台快照新鲜度）
- 回归：iOS 全流程在 M1 任何改动后重跑一遍

## 7. 里程碑顺序与提交约定

M1 → M2 → M3 → M4 串行；每个里程碑一组 commit（`feat(M1): ...`），M1 完成即具备"每日双平台榜单+历史"最小可用能力，此后随时可提前部署。
