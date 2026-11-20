# 榆灯触达样本预算台

内容触达基线点击率→最小可检测差异与预算→预注册方案；单双侧语义固定双侧，功效模拟固定seed。原生 HTML/CSS/JavaScript 多模块工作席，所有计算由 Python 完成。

## 模拟业务
榆灯研究协作组，12名分析师与业务人员，日常使用 `sample-budget-202611-1.csv` 手工抄表。当前三个痛点：观测与口径不可追溯、重算易出错、结果与复核割裂。上游提供独立合成业务观测；本应用接管数据登记、方法执行和输入冻结；下游负责人形成复测/预算方案，观察员获取复核后的CSV。

核心业务实体：CampaignPlan / BaselineScenario / PowerRun / BudgetDecision，以及面向合作方的 Channel / AudienceTouch / PrivacyBudget / PrivacyRelease。源码 model/schema/service/controller/route 与前端 api/store/pages 完成链路，不依赖浏览器本地假数据。

## 功能与方法
- 触达计划、基线情景录入/编辑/删除；重名记录与非法数值明确拒绝。
- 两比例实验样本量正态近似与二项Monte Carlo功效验证。独立等样本双组、双侧正态近似。模拟功效用于检验近似；低事件率应谨慎采用，正式实验须另行预注册。
- 每次运行冻结参数、观测和SHA256。Redis任务由独立worker计算，写DB与共享产物卷；输入修改不会改写历史结果。
- 负责人复核不可覆盖；审计记录登录、数据改动、排队、复核与导出；240请求/分钟限流、全局可恢复错误。
- 分渠道投放复盘（合作方交付）：发布前按预先登记的渠道分别核算 A/B 双组触达与点击；受众表以 `(study_id, audience_key)` 唯一，跨组跨渠道总贡献恒为1（敏感度1）。
- 受众级纯差分隐私发布：每个（渠道×组别×触达/点击）计数独立加入 Laplace 噪声，单次发布 ε 在 `4×渠道数` 个子查询间均分；渠道小计、组别总计与总计由带噪分渠道计数逐层相加，因此分渠道相加必等于总计。
- 页面与下载共用同一条已发布 payload：重试（相同幂等键）直接回读，不重复扣额度、不重抽噪声。更正通过 `corrects_release_id` 另发新版本，旧版保留。额度扣减使用`UPDATE … WHERE spent+ε<=total`原子条件，与结果写入同一事务，并发下不会超扣；额度不足返回409且旧版仍可读。合作方角色只能读取带噪结果，不能访问原始触达、运行或审计。

## 快速启动
```bash
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18244 ，API http://localhost:19244/docs 。数据库映射 17744。无需Node构建。可以从中文和带空格目录启动。清理 `docker compose down -v --remove-orphans` 会删除本题演示数据卷。

|角色|账号|密码|权限与典型动作|
|---|---|---|---|
|admin 负责人|admin@demo.local|Research2026!|全部读写、批准复核、下载|
|analyst 分析师|analyst@demo.local|Research2026!|数据修改、创建任务、读取结果及下载；不能复核|
|viewer 观察员|viewer@demo.local|Research2026!|只读；仅可导出已复核结果，可读带噪发布|
|partner 合作方|partner@demo.local|Research2026!|只看带噪发布结果与下载；不能访问原始数据、运行、审计|

## 一天的工作剧本
1. 09:00 admin登录，查“榆灯·冬季专题”。
2. 09:10 analyst核对 `sample-budget-202611-1.csv` 的seed记录。
3. 09:15 来源录入页检查 `基线点击率 (0–1)` 等业务字段，必要时编辑。
4. 09:20 分析执行页保留默认参数 `{"alpha": 0.05, "power": 0.8, "simulations": 10000}`，命名本轮研究。
5. 09:21 冻结输入并排队，worker实算，结果页自动刷新。
6. 09:25 阅读核心数值、方法边界、明细与SHA256；发现失败先修数据重跑。
7. 09:35 admin打开业务复核，写明限制与下一步动作，归档后不可覆盖。
8. 09:40 viewer读取复核意见并下载CSV，在操作留痕页核对下载事件。
9. 09:50 analyst在“分渠道复盘”登记渠道、录入受众触达，按预设 ε 发布带噪结果；同一幂等键可安全重试，更正另发新版。
10. 10:00 partner登录后只见合作方视图：分渠道双组带噪触达/点击/点击率，页面与CSV同源。

seed是3个前瞻设计情景，每个计划1条基线/候选概率、成本和预算记录；本题用于实验前预算设计，不伪造实验后点击事件。预算与单位成本采用十进制除法向下取整，预计总成本四舍五入至分（ROUND_HALF_UP），避免0.6÷(0.1×2)浮点误差少算样本。预算每组触达上限200000；不足一次双组触达时预算可行样本数与功效均为0。

## 技术与目录
|部分|实现|
|---|---|
|前端|原生ES modules、HTML/CSS、Nginx1.27，无前端框架|
|API|Python3.11、FastAPI0.115、SQLAlchemy2、JWT、PBKDF2密码|
|计算|NumPy2.2、SciPy1.15，固定seed42|
|数据库|PostgreSQL16|
|任务|Redis7持久队列，Python独立worker，心跳healthcheck|

`frontend/src/`分api、stores、types、components/common、hooks、pages、router、utils、constants；`backend/src/`分config、models、schemas、services、controllers、routes、middlewares、utils、constants；`backend/scripts/seed_demo.py`自然键插入、重复不覆盖修改；`backend/migrations/README.md`说明schema版本。

环境变量 `.env.example`：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、DB_PASSWORD、JWT_SECRET、SEED_DEMO。开发时在本地venv安装backend/requirements.txt，设置DATABASE_URL、REDIS_URL、JWT_SECRET再运行uvicorn；前端开发经Nginx代理 `/api/` 到不带前缀的API。

共享枚举：角色admin/analyst/viewer/partner和队列queued/running/completed/failed；后端`src/constants/enums.py`、认证与worker使用相同值；前端`src/types/enums.js`、状态与角色界面使用相同值。Google Fonts：Noto Serif SC + IBM Plex Mono；断网使用serif/monospace回退。

## 算法输入、失败态与复现
输入为选定批次全部观测和参数，输出核心数值、明细、解释；参数经后端严格白名单和范围验证。独立等样本双组、双侧正态近似。模拟功效用于检验近似；低事件率应谨慎采用，正式实验须另行预注册。。空批次拒绝；不完整字段/非有限数/非法计数拒绝；常量相关列与不足样本使任务failed并保留错误。固定seed42、输入checksum相同可复现。独立oracle：功效随样本趋势；公式对norm.ppf；MDE零与越界概率拒绝。

## 差分隐私发布的口径
- 贡献上限：受众表对 `(study_id, audience_key)` 唯一，同一位受众换渠道或换组别是覆盖而非新增，故任一计数查询的敏感度均为1。
- 噪声：`Laplace(0, 1/(ε/q))`，`q = 渠道数 × 2组 × 2指标`；整次发布满足 ε-差分隐私（纯DP、顺序组合）。
- 后处理：带噪计数取整并截断到 `[0, ∞)`、`点击 ≤ 触达`；分渠道小计与总计由这些截断后的值相加，保持“分渠道相加=总计”与DP有效性。
- 额度：每个研究一条 `PrivacyBudget`，默认总额度取 `domain.privacy.default_budget`（4.0）；只有 admin 可重设，且不得低于已用额度。
- 幂等：`(study_id, idempotency_key)` 唯一；重试返回原版本、原 payload、原扣额。更正写新版本并记 `corrects_release_id`。
- 角色隔离：partner 只能访问 `/partner/overview` 与 `/privacy/releases/{id}[/export]`；其余研究/运行/审计接口一律 403。

已知边界：小型本地研究应用，使用合成数据，不含企业SSO与外发邮件；结果由人工复核，不自动执行业务决策；单worker恢复queued/running任务，数据库与Redis间未采用分布式事务。差分隐私发布不替代正式预注册，也不对合作方披露真实计数。以 TESTING.md 记录实际验证结果。

MIT License。
