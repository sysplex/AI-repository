#!/usr/bin/env bash
# ==============================================================================
# StockPilot PostgreSQL 自动化逻辑备份与归档脚本 (M10-T07)
# 
# 功能：
# 1. 检查数据库连通性
# 2. 生成带时间戳的自定义格式压缩归档 (pg_dump -Fc)
# 3. 计算并输出 SHA256 校验码文件
# 4. 自动清理过期冷备文件 (RETENTION_DAYS)
# ==============================================================================

set -euo pipefail

# 默认配置（支持环境变量覆盖）
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-postgres}"
PGDATABASE="${PGDATABASE:-stockpilot}"
BACKUP_DIR="${BACKUP_DIR:-$(cd "$(dirname "$0")/.." && pwd)/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

export PGPASSWORD

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="${PGDATABASE}_${TIMESTAMP}.dump"
FILEPATH="${BACKUP_DIR}/${FILENAME}"
CHECKSUM_PATH="${FILEPATH}.sha256"

mkdir -p "${BACKUP_DIR}"

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

log "INFO: 开始执行 PostgreSQL 自动化备份..."
log "INFO: 目标主机: ${PGHOST}:${PGPORT}, 目标库: ${PGDATABASE}, 归档目录: ${BACKUP_DIR}"

# 1. 连通性健康检查
if command -v pg_isready >/dev/null 2>&1; then
    if ! pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -t 10; then
        log "ERROR: 数据库不可达 (${PGHOST}:${PGPORT}/${PGDATABASE})"
        exit 1
    fi
fi

# 2. 执行逻辑备份 (自定义归档格式 -Fc 支持压缩并支持细粒度并行恢复)
START_TIME=$(date +%s)
log "INFO: 执行 pg_dump 生成冷备文件: ${FILENAME} ..."

pg_dump \
    -h "${PGHOST}" \
    -p "${PGPORT}" \
    -U "${PGUSER}" \
    -d "${PGDATABASE}" \
    -F c \
    -b \
    -v \
    -f "${FILEPATH}" 2>&1 | tail -n 10

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

if [ ! -f "${FILEPATH}" ] || [ ! -s "${FILEPATH}" ]; then
    log "ERROR: 备份文件未生成或大小为 0: ${FILEPATH}"
    exit 1
fi

FILE_SIZE=$(du -h "${FILEPATH}" | cut -f1)
log "INFO: 备份成功! 大小: ${FILE_SIZE}, 耗时: ${DURATION}s"

# 3. 计算 SHA256 校验摘要
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${FILEPATH}" | awk '{print $1}' > "${CHECKSUM_PATH}"
    log "INFO: SHA256 校验和已写入: $(cat "${CHECKSUM_PATH}")"
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${FILEPATH}" | awk '{print $1}' > "${CHECKSUM_PATH}"
    log "INFO: SHA256 校验和已写入: $(cat "${CHECKSUM_PATH}")"
fi

# 4. 清理超过保留周期的历史备份
log "INFO: 正在清理超过 ${RETENTION_DAYS} 天的历史备份文件..."
find "${BACKUP_DIR}" -name "${PGDATABASE}_*.dump*" -type f -mtime +"${RETENTION_DAYS}" -exec rm -f {} + || true

log "INFO: PostgreSQL 备份流程全部完成。"
