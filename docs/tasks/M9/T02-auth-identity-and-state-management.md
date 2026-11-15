# M9-T02 全局状态管理、用户认证体系与多租户上下文（Auth & Identity）

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 |
| 阻塞 | T05, T06, T07 |
| 分支 | `feat/m9-t02-auth-identity-state` |
| Issue | #166 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
交付完整的用户认证与多租户上下文体系，包含登录、注册、找回密码、修改设置与用量仪表盘页面，提供 `AuthContext`、令牌自动刷新、状态持久化与路由鉴权守卫（`ProtectedRoute` / `AdminRoute`）。

---

## 2. 交付范围
1. **认证页面**：
   - 登录页 (`/login`)：邮箱 + 密码，支持密码可见性切换与记住登录；
   - 注册页 (`/register`)：邮箱、密码复杂度即时校验；
   - 密码重置请求与确认页 (`/forgot-password`, `/reset-password`)；
2. **用户中心与设置**：
   - 个人偏好设置 (`/settings`)：语言选择、风险偏好配置（保守/平衡/激进）、配色偏好（美股绿涨红跌 / A股红涨绿跌）；
   - AI 配额仪表盘 (`/me/usage`)：当日已用配额、剩余配额、重置时间与消耗统计；
   - 管理员用户面板 (`/admin/users`)：用户列表、状态管理（仅管理员可见）。
3. **状态与守卫**：
   - `AuthContext` 与 `useAuth()` Hook；
   - `ProtectedRoute`：未认证拦截并重定向至 `/login?redirect=...`；
   - `AdminRoute`：非管理员访问 403 友好提示。
