# 测试记录（分渠道差分隐私复盘）

本轮新增“分渠道投放复盘 → 受众级差分隐私发布 → 合作方只读带噪结果”链路。以下结果均在本机实际执行。

## 环境
- Python 3.11.2，依赖按 `backend/requirements.txt` 安装；SQLite 用于测试（生产仍为 PostgreSQL 16）。
- 浏览器端用 jsdom 驱动真实前端模块，直连本机 uvicorn + SQLite + Fake Redis（仅替代限流/队列）。
- 命令：
  ```bash
  cd backend
  DATABASE_URL=sqlite:////tmp/dp-test.db REDIS_URL=redis://localhost:6379/0 \
    JWT_SECRET=test-secret SEED_DEMO=false python3 -m pytest tests -q
  ```

## 结果
```
16 passed in 11.72s
```

覆盖项：

| 用例 | 断言 |
|---|---|
| `test_contributions_are_capped_to_one_per_audience` | 每位受众仅一条记录；换渠道/组别为覆盖，贡献恒为1 |
| `test_channel_counts_sum_to_totals` | 渠道小计 = A+B；总计 = 各渠道小计之和 = A+B 总 |
| `test_epsilon_per_query_and_counts_are_integers` | `q = 渠道×2×2`，`per_query = ε/q`；带噪计数为整数且 `0 ≤ 点击 ≤ 触达` |
| `test_retry_same_key_is_idempotent` | 同幂等键重试返回同版本、同 payload，只扣一次额度 |
| `test_correction_creates_new_version` | 更正写 v2 并记录 `corrects_release_id`，额度再扣一次 |
| `test_budget_exhaustion_blocks_new_release_but_old_version_readable` | 超额 409“额度不足”；旧版对内部与 partner 均可读 |
| `test_export_matches_page_payload_without_extra_spend` | 内部/合作方导出的 CSV 完全相同；导出不扣额度；CSV 数值等于页面 payload |
| `test_partner_view_hides_internal_fields` | partner 视图无 `input_sha256`/`idempotency_key` |
| `test_touch_requires_registered_channel` / `test_click_requires_reached` | 渠道必须预登记；点击必须触达 |
| `test_atomic_guard_blocks_double_spend_without_new_release` | `UPDATE … WHERE spent+ε<=total` 在额度用尽后 rowcount=0 |
| `test_release_write_failure_rolls_back_spend` | 结果写入失败时扣额回滚，不产生孤立的已用额度 |
| `test_same_idempotency_key_with_different_request_is_rejected` | 同一幂等键换了 ε 或更正目标时 409，不静默返回旧结果 |
| `test_roles_and_publish_flow`（HTTP） | analyst 可发布；viewer 不可发布不可记账；partner 对 `/overview`、`/studies`、`/runs`、`/audits`、原始触达均 403；`/partner/overview` 仅 partner 可用 |
| `test_budget_exhaustion_returns_409_and_old_version_readable`（HTTP） | 409 语义与旧版可读 |
| `test_viewer_can_read_published_only`（HTTP） | viewer 可读已发布版本与下载 |

## 端到端 HTTP 脚本（真实 uvicorn）
seed 后：3 个研究、9 条渠道、1800 条受众触达、3 个 seed 发布版本；预算 4.0，已用 1.0。
- partner 读取 v1：200；CSV 19 行，首行说明“带噪计数，非真实业务计数”。
- partner 访问 `/overview`、`/studies`、`/domain`、`/runs`、`/audits`、`/studies/{id}/privacy`、`/studies/{id}/privacy/touches`：全部 403。
- 发布 → 同键重试：同 id、同 payload，`spent_epsilon` 仍为扣一次后的值。
- 更正：v3、`corrects_release_id` 指向被更正版本。
- 额度用尽后再发布：409“隐私额度不足：剩余 0.0，本次需要 0.5；可读取既有版本”；旧版仍 200。

## 前端（jsdom 直连后端）
- 分渠道复盘页：额度卡、渠道登记、受众录入、发布表单、发布历史均渲染；发布后跳转 `#release/{id}`。
- 带噪结果页：分渠道×组别明细、参数、CSV 按钮；内部角色额外显示输入 SHA256，partner 不显示。
- 合作方视图：仅列有发布版本的研究；不含内部哈希或原始记录。
- viewer 打开分渠道复盘：无发布/录入表单，可读额度与历史。

## 未自动化验证
- PostgreSQL 并发事务下的真实锁行为（测试用 SQLite；原子扣减以条件 UPDATE 保证，生产库同样语义）。
- Docker Compose 全栈启动（本环境无 docker）。
