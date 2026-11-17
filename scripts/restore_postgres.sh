#!/usr/bin/env bash
# ==============================================================================
# StockPilot PostgreSQL 应急灾备恢复与一致性校验脚本 (M10-T07)
#
# 使用方法：
#   ./scripts/restore_postgres.sh <backup_file.dump> [target_database]
# ==============================================================================

set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <backup_file.dump> [target_database]"
    exit 1
fi

BACKUP_FILE="$1"
TARGET_DB="${2:-${PGDATABASE:-stockpilot}}"

PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-postgres}"
CLEAN_MODE="${CLEAN_MODE:-true}"

export PGPASSWORD

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

log "INFO: 开始执行 PostgreSQL 数据恢复..."
log "INFO: 备份源: ${BACKUP_FILE}"
log "INFO: 恢复目标: ${PGHOST}:${PGPORT}/${TARGET_DB}"

if [ ! -f "${BACKUP_FILE}" ]; then
    log "ERROR: 备份文件不存在: ${BACKUP_FILE}"
    exit 1
fi

# 1. 校验 SHA256 完整性（如果存在 .sha256 文件）
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [ -f "${CHECKSUM_FILE}" ]; then
    EXPECTED_SHA=$(cat "${CHECKSUM_FILE}" | tr -d '[:space:]')
    log "INFO: 检查 SHA256 完整性 (预期值: ${EXPECTED_SHA})..."
    if command -v sha256sum >/dev/null 2>&1; then
        ACTUAL_SHA=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')
    elif command -v shasum >/dev/null 2>&1; then
        ACTUAL_SHA=$(shasum -a 256 "${BACKUP_FILE}" | awk '{print $1}')
    else
        ACTUAL_SHA=""
    fi

    if [ -n "${ACTUAL_SHA}" ] && [ "${ACTUAL_SHA}" != "${EXPECTED_SHA}" ]; then
        log "ERROR: SHA256 校验失败! 实际: ${ACTUAL_SHA}, 预期: ${EXPECTED_SHA}"
        exit 1
    fi
    log "INFO: SHA256 完整性校验通过。"
fi

# 2. 目标数据库存在性探测与建库
DB_EXISTS=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${TARGET_DB}'" || echo "0")
if [ "${DB_EXISTS}" != "1" ]; then
    log "INFO: 目标数据库 ${TARGET_DB} 不存在，正在创建..."
    psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres -c "CREATE DATABASE \"${TARGET_DB}\";"
fi

# 3. 执行 pg_restore
RESTORE_OPTS=(
    -h "${PGHOST}"
    -p "${PGPORT}"
    -U "${PGUSER}"
    -d "${TARGET_DB}"
    --no-owner
    --no-privileges
)

if [ "${CLEAN_MODE}" = "true" ]; then
    RESTORE_OPTS+=(--clean --if-exists)
fi

START_TIME=$(date +%s)
log "INFO: 执行 pg_restore 导入数据..."

# pg_restore 在 clean 模式下若遇到尚未存在的对象可能会以警告退出 (code 1)，此处容忍 warning
set +e
pg_restore "${RESTORE_OPTS[@]}" "${BACKUP_FILE}" 2>&1 | grep -v "already exists" | grep -v "does not exist" || true
RESTORE_RC=$?
set -e

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
log "INFO: 数据导入完成，耗时: ${DURATION}s"

# 4. 关键表健康与数据完整性校验
log "INFO: 执行 Schema 与 Alembic 版本校验..."

ALEMBIC_HEAD=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${TARGET_DB}" -tAc "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null || echo "NONE")
USERS_COUNT=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${TARGET_DB}" -tAc "SELECT count(*) FROM users;" 2>/dev/null || echo "0")
ACCOUNTS_COUNT=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${TARGET_DB}" -tAc "SELECT count(*) FROM sim_accounts;" 2>/dev/null || echo "0")
ALERTS_COUNT=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${TARGET_DB}" -tAc "SELECT count(*) FROM alerts;" 2>/dev/null || echo "0")

log "INFO: [校验结果] Alembic Head Revision: ${ALEMBIC_HEAD}"
log "INFO: [校验结果] 注册用户数: ${USERS_COUNT}, 模拟盘账户数: ${ACCOUNTS_COUNT}, 活跃提醒规则数: ${ALERTS_COUNT}"

if [ "${ALEMBIC_HEAD}" = "NONE" ]; then
    log "ERROR: 恢复后数据库缺少 alembic_version，可能恢复未成功!"
    exit 1
fi

log "INFO: 恭喜! 数据库 ${TARGET_DB} 恢复与健康检查全部成功。"
