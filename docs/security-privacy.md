# 安全与隐私

- 代码基线：`main` @ `1cea3ff` / `v0.1.7`
- 最近变更：2026-11-18 取消 Origin 白名单与收紧后的 CORS（`v0.1.7`）

## 1. 身份与会话

| 项 | 实现 |
|---|---|
| 密码 | Argon2id 哈希；登录失败节流与冷却 |
| Access Token | JWT，默认 15 分钟，前端只在内存保存 |
| Refresh Token | HttpOnly Cookie，服务端只存哈希，轮换；15 秒复用宽限用于并发刷新 |
| CSRF | 双提交 Cookie + `X-CSRF-Token`，写请求校验 |
| 最后管理员 | 不可删除、停用或降级 |
| 个人访问令牌 | `personal_access_tokens` 只存哈希，用于 MCP；可轮换与撤销 |
| 审计 | `audit_logs` 记录登录、刷新、管理操作等事件 |

## 2. CORS 与 Origin（重要变更）

2026-11-18 的 `fix(auth)` 做了两件事：

1. `CORSMiddleware` 改为 `allow_origin_regex=".*"` 并 `allow_credentials=True`，即**反射任意 Origin**。
2. `validate_origin()` 变为空实现（保留调用点，便于恢复）。

含义与风险：

- 浏览器跨站来源不再被服务端拒绝；写请求的安全边界现在**只剩 CSRF 令牌**。
- 若某个写接口遗漏 CSRF 校验，或 CSRF Cookie 可被子域覆盖，就可能出现跨站请求伪造。
- 该策略是操作者明确要求的变更，代码注释与提交信息均有记录；恢复时只需改 `main.py` 的 CORS 配置与 `auth.py` 的 `validate_origin`。

**建议**：在公开部署前二选一——恢复 Origin 白名单，或逐个审计所有写路由确认 CSRF 依赖；同时把 `CORS_ORIGINS` 重新作为有效配置。

## 3. AI Key 与外部请求

- provider Key 以 AES-GCM 密文存 `ai_providers.api_key_ciphertext`，加密密钥来自 `SECRET_ENCRYPTION_KEY`；接口只返回掩码。
- Base URL 校验阻止云元数据地址与私有网段；生产环境默认禁止私有地址。
- 重定向限制同源与次数；provider 调用有超时与重试上限。
- Key 只在服务端解密，不写入日志、错误体或前端。

## 4. 容器与网络

- 应用容器：UID/GID 10001、只读根文件系统、`cap_drop: ALL`、`no-new-privileges`。
- 只有 `reverse-proxy` 发布宿主端口（默认 `127.0.0.1:8080`）；PostgreSQL、Redis 与内部服务不对外。
- 生产 overlay 固定镜像 digest、`pull_policy: always`、日志滚动上限。
- CI 用 gitleaks 扫描 Git 历史；`.env` 不入库。

## 5. 安全响应头

- 后端中间件与两份 nginx 配置均输出：`Content-Security-Policy`、`X-Frame-Options: SAMEORIGIN`、`X-Content-Type-Options: nosniff`、`Referrer-Policy`、`Strict-Transport-Security`。
- CSP 指令集：`default-src 'self'`、`object-src 'none'`、`frame-ancestors 'self'`、`form-action 'self'`、`script-src 'self'`、`style-src 'self' 'unsafe-inline'`、`connect-src 'self'`、`img-src 'self' data: blob:`。
- SSE 分支单独重复安全头并关闭 nginx 缓冲。

> 旧文档中「CSP 未完成 / F-SEC-01 CONDITIONAL」的说法已过时：配置已存在且有测试断言；该门禁只是没有按新证据重新分类。

## 6. 隐私边界

- 管理看板只返回聚合指标（成员数、活跃、练习量等），不返回答题正文、草稿、教练对话或私有词书正文。
- 个人词书与个人知识库按 `owner_id` 隔离；知识检索只读可读书架。
- 词书与教练附件存放在私有卷，数据库只存元数据。
- 通知后端保留，但个人版前端当前没有通知入口。

## 7. 数据与运维边界

- 历史转储（`.scratch/db-backup/`）含可解密的 provider Key 密文与口令哈希，不属于仓库，也不应随代码分发；如仍在本地，应评估保留与轮换。
- 生产备份的 RPO/RTO 仍未正式批准（`deploy/BACKUP-AND-RECOVERY.md` 标记 PENDING），恢复演练有历史记录但未归档。
- 公网 HTTPS 未落地，当前预览只有 HTTP + 高位端口。
- 仓库为公开可见但尚未添加 LICENSE。

## 8. 未关闭项

| 项 | 状态 |
|---|---|
| Origin/CORS 策略 | 已放开；需在公开部署前决策 |
| 生产备份审批与 RPO/RTO | 未关闭 |
| 公网 TLS / 域名 | 未完成 |
| LICENSE | 未添加 |
| 依赖漏洞审计 | 无近期审计记录，需在 CI 或本地重跑 |
