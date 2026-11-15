# M9-T01 前端工程脚手架、构建工具链与 OpenAPI TypeScript 客户端契约生成

| 项 | 内容 |
|---|---|
| 波次 | Wave 1 |
| 依赖 | M8 结项已完成 |
| 阻塞 | T02, T03, T04 等后续全部前端任务 |
| 分支 | `feat/m9-t01-frontend-scaffolding-openapi` |
| Issue | #165 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
搭建 `frontend/` 现代化前端工程，配置 Vite + React + TypeScript + Tailwind CSS 构建工具链，建立从后端 FastAPI 自动导出 OpenAPI 规范并生成 TypeScript 客户端与类型的自动化机制，实现带 Token 注入与全局错误处理的基础 HTTP Client。

---

## 2. 交付范围
1. **工程脚手架**：
   - 初始化 `frontend/` 目录；
   - `package.json`（依赖：react, react-dom, react-router-dom, @tanstack/react-query, lucide-react, clsx, tailwind-merge, axios / fetch）；
   - `tsconfig.json`（严格模式 `strict: true`, ESNext, Node 模块解析）；
   - `vite.config.ts`（支持环境变量、别名 `@` 指向 `src`、开发服务器反向代理 `/api` 到 `http://localhost:8000`）；
   - `tailwind.config.js` 与 `postcss.config.js`（Tailwind CSS 颜色与样式配置）。
2. **OpenAPI 类型与客户端生成**：
   - 脚本：从后端导出 `openapi.json`，并自动生成类型定义；
   - 类型契约：包含 `UserRead`, `Bar`, `Signal`, `ResearchEnvelope`, `WatchlistRead`, `ScreenerRunRead` 等全套后端 Schema。
3. **基础 HTTP Client**：
   - `src/api/client.ts`：统一 Axios / Fetch 封装；
   - 请求拦截器：自动注入 `Authorization: Bearer <token>`；
   - 响应拦截器：统一错误提取（401, 404, 409, 422, 429, 500, 503）。
4. **验证门禁**：
   - `npm run build` 构建成功且 0 TypeScript 错误；
   - `npm run lint` 语法检查通过；
   - 单元测试覆盖 HTTP Client 拦截器与契约解析。

---

## 3. 验收标准
- [ ] `frontend/` 目录结构完备且构建通过
- [ ] OpenAPI 自动化导出并生成强类型定义
- [ ] 基础 HTTP Client 具备 Bearer 鉴权与错误处理拦截
- [ ] 前端 TypeScript 严格模式 0 警告 0 错误
