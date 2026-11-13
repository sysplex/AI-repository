# Kubernetes 集群部署与 GitOps 运维指南（deploy/K8S.md）

本文档指导如何将 StockPilot 部署到私有 Kubernetes 集群（192.168.50.36~39），并配合 Harbor 镜像仓库与 Argo CD 实现持续交付与秒级回滚。

---

## 1. 资源清单结构

```
deploy/k8s/
├── kustomization.yaml       # Kustomize 编排入口（Argo CD 直接消费）
├── namespace.yaml           # 专有命名空间 stockpilot
├── configmap.yaml           # 通用环境变量配置
├── secret.example.yaml      # 敏感凭据模板（数据库连接串、SECRET_KEY）
├── migrate-job.yaml         # Alembic 数据库迁移一次性任务
├── api-deployment.yaml      # FastAPI 后端无状态 Deployment（多副本滚动更新）
├── api-service.yaml         # ClusterIP 服务暴露
├── worker-deployment.yaml   # ARQ 异步任务后台工作进程
└── ingress.yaml             # Ingress 路由规则
```

---

## 2. 首次部署准备

### 2.1 创建 Secret
复制 `secret.example.yaml` 并填写真实凭据：
```bash
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.yaml
# 编辑填入真实密码与密钥
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secret.yaml
```

### 2.2 配置 Harbor 镜像拉取凭证（若项目为私有）
```bash
kubectl create secret docker-registry harbor-registry-secret \
  --docker-server=192.168.50.36:30088 \
  --docker-username=admin \
  --docker-password=Harbor12345 \
  --namespace=stockpilot
```

---

## 3. 一键部署与版本切换

### 方式 A：使用 Kustomize / Kubectl（命令行）
```bash
# 1. 运行数据库迁移
kubectl apply -f deploy/k8s/migrate-job.yaml

# 2. 一键应用全量清单
kubectl apply -k deploy/k8s/

# 3. 切换版本只需一行命令：
kubectl set image deployment/stockpilot-api api=192.168.50.36:30088/stockpilot/stockpilot-app:<TARGET_VERSION> -n stockpilot
kubectl set image deployment/stockpilot-worker worker=192.168.50.36:30088/stockpilot/stockpilot-app:<TARGET_VERSION> -n stockpilot
```

### 方式 B：使用 Argo CD（GitOps 推荐）
1. 在 Argo CD（`https://192.168.50.36:31443/`）中创建应用 `stockpilot`，指向 GitHub 仓库的 `deploy/k8s` 路径。
2. 每次发布新版本，CI 自动或手动修改 `deploy/k8s/kustomization.yaml` 中的 `newTag` 并推送 Git。
3. Argo CD 自动拉取并执行无感知平滑滚动发布。

---

## 4. 故障秒级回滚命令（Rollback）

当新版本遇到异常时，执行回滚操作：

```bash
# 查看发布历史版本号
kubectl rollout history deployment/stockpilot-api -n stockpilot

# 一键快速撤销到上一个健康版本
kubectl rollout undo deployment/stockpilot-api -n stockpilot
kubectl rollout undo deployment/stockpilot-worker -n stockpilot

# 查看回滚状态
kubectl rollout status deployment/stockpilot-api -n stockpilot
```
或直接在 Argo CD Web UI 点击 **History and Rollback** 选取历史版本一键回滚。
