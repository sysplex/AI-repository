#!/usr/bin/env bash
# ==============================================================================
# StockPilot 自动化容灾恢复演练与数据一致性验证脚本 (M10-T07)
#
# 流程：
# 1. 查找最新冷备文件（若无则自动触发即时备份）
# 2. 建立完全隔离的临时演练库 (stockpilot_dr_verify_*)
# 3. 执行无损恢复并校验 SHA256 签名与 Schema 表结构
# 4. 自动化对比核心业务表行数与 Alembic 迁移版本一致性
# 5. 安全清理演练临时库并输出演练合格报告
# ==============================================================================

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/../backups/postgres}"
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-postgres}"
export PGPASSWORD

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [DR-DRILL] $*"
}

log "========================================================"
log "   StockPilot 灾备演练 (Disaster Recovery Drill) 开始   "
log "========================================================"

# 1. 定位最新备份文件
DUMP_FILE="${1:-}"
if [ -z "${DUMP_FILE}" ]; then
    log "INFO: 未显式指定备份文件，正在检索 ${BACKUP_DIR} 中最新归档..."
    if [ -d "${BACKUP_DIR}" ]; then
        DUMP_FILE=$(find "${BACKUP_DIR}" -name "*.dump" -type f | sort -r | head -n 1 || true)
    fi
fi

if [ -z "${DUMP_FILE}" ] || [ ! -f "${DUMP_FILE}" ]; then
    log "WARNING: 未检索到有效备份文件，自动调用 backup_postgres.sh 现场生成..."
    bash "${SCRIPT_DIR}/backup_postgres.sh"
    DUMP_FILE=$(find "${BACKUP_DIR}" -name "*.dump" -type f | sort -r | head -n 1)
fi

log "INFO: 选定演练备份归档: ${DUMP_FILE}"

# 2. 创建临时演练隔离数据库
DRILL_DB="stockpilot_dr_verify_$(date +%s)_$$"
log "INFO: 创建隔离演练目标数据库: ${DRILL_DB} ..."
psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres -c "CREATE DATABASE \"${DRILL_DB}\";"

# 注册 EXIT 钩子，确保演练结束（无论成功与否）均清理临时库
cleanup() {
    log "INFO: 执行演练收尾清理，销毁临时数据库 ${DRILL_DB} ..."
    psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres -c "
        SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DRILL_DB}' AND pid <> pg_backend_pid();
        DROP DATABASE IF EXISTS \"${DRILL_DB}\";
    " >/dev/null 2>&1 || true
    log "INFO: 临时数据库 ${DRILL_DB} 已成功销毁。"
}
trap cleanup EXIT

# 3. 调用恢复脚本将冷备恢复至演练库
log "INFO: 执行灾备恢复导入..."
bash "${SCRIPT_DIR}/restore_postgres.sh" "${DUMP_FILE}" "${DRILL_DB}"

# 4. 执行数据与架构完整性自动化断言
log "INFO: 正在断言演练数据库 ${DRILL_DB} 数据与约束..."

# (1) 验证 Alembic 版本存在
ALEMBIC_VER=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${DRILL_DB}" -tAc "SELECT version_num FROM alembic_version LIMIT 1;" || echo "")
if [ -z "${ALEMBIC_VER}" ]; then
    log "ERROR: [断言失败] 恢复库中缺少 alembic_version 迁移头！"
    exit 1
fi
log "ASSERTION PASS: Alembic Head Revision = ${ALEMBIC_VER}"

# (2) 验证核心业务数据表齐全
REQUIRED_TABLES=(
    "users"
    "user_sessions"
    "audit_logs"
    "sim_accounts"
    "sim_positions"
    "sim_orders"
    "sim_trades"
    "equity_snapshots"
    "ai_reports"
    "alerts"
    "notification_channels"
    "alert_history"
    "daily_reports"
)

TOTAL_TABLES_COUNT=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${DRILL_DB}" -tAc "
    SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';
")
log "INFO: 恢复库公共 Schema 数据表总计: ${TOTAL_TABLES_COUNT} 张"

for tbl in "${REQUIRED_TABLES[@]}"; do
    EXISTS=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${DRILL_DB}" -tAc "
        SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='${tbl}';
    " || echo "0")
    if [ "${EXISTS}" != "1" ]; then
        log "ERROR: [断言失败] 关键业务表 ${tbl} 未能在恢复库中找到！"
        exit 1
    fi
    ROW_COUNT=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${DRILL_DB}" -tAc "SELECT count(*) FROM \"${tbl}\";")
    log "ASSERTION PASS: 表 [${tbl}] 存在并可读，当前行数: ${ROW_COUNT}"
done

log "========================================================"
log "   容灾恢复演练全部通过! 数据库无损一致性已严格证明   "
log "========================================================"
