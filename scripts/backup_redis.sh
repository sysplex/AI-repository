#!/usr/bin/env bash
# ==============================================================================
# StockPilot Redis 快照备份与归档脚本 (M10-T07)
#
# 功能：
# 1. 验证 Redis 存活性 (PING)
# 2. 触发后台异步持久化 (BGSAVE) 并轮询等待完成
# 3. 复制 dump.rdb 并 gzip 压缩，附带 SHA256 校验码
# 4. 自动清理超期备份
# ==============================================================================

set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
BACKUP_DIR="${BACKUP_DIR:-$(cd "$(dirname "$0")/.." && pwd)/backups/redis}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

mkdir -p "${BACKUP_DIR}"

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

CLI_CMD=(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}")
if [ -n "${REDIS_PASSWORD}" ]; then
    CLI_CMD+=(-a "${REDIS_PASSWORD}")
fi

log "INFO: 开始执行 Redis 快照备份..."
log "INFO: 目标实例: ${REDIS_HOST}:${REDIS_PORT}, 归档目录: ${BACKUP_DIR}"

# 1. PING 连通性测试
if ! "${CLI_CMD[@]}" ping >/dev/null 2>&1; then
    log "ERROR: 无法连接 Redis 实例 (${REDIS_HOST}:${REDIS_PORT})"
    exit 1
fi

# 2. 触发 BGSAVE
PREV_SAVE=$("${CLI_CMD[@]}" lastsave | tr -d '[:space:]')
log "INFO: 上次保存时间戳: ${PREV_SAVE}, 正在触发 BGSAVE ..."

SAVE_OUTPUT=$("${CLI_CMD[@]}" bgsave || true)
log "INFO: BGSAVE 响应: ${SAVE_OUTPUT}"

# 等待持久化落地 (最多等待 60 秒)
MAX_WAIT=60
WAIT_COUNT=0
while [ "${WAIT_COUNT}" -lt "${MAX_WAIT}" ]; do
    CURRENT_SAVE=$("${CLI_CMD[@]}" lastsave | tr -d '[:space:]')
    IN_PROGRESS=$("${CLI_CMD[@]}" info persistence | grep "rdb_bgsave_in_progress" | cut -d: -f2 | tr -d '[:space:]' || echo "0")

    if [ "${IN_PROGRESS}" = "0" ] && [ "${CURRENT_SAVE}" -ge "${PREV_SAVE}" ]; then
        log "INFO: BGSAVE 已完成 (新时间戳: ${CURRENT_SAVE})。"
        break
    fi
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

if [ "${WAIT_COUNT}" -ge "${MAX_WAIT}" ]; then
    log "WARNING: BGSAVE 等待超时，尝试直接定位现有 RDB 文件..."
fi

# 3. 获取 dump.rdb 文件路径
RDB_DIR=$("${CLI_CMD[@]}" config get dir | tail -n 1 | tr -d '[:space:]')
RDB_NAME=$("${CLI_CMD[@]}" config get dbfilename | tail -n 1 | tr -d '[:space:]')
SRC_RDB="${RDB_DIR}/${RDB_NAME}"

if [ ! -f "${SRC_RDB}" ]; then
    # 若在不同主机或容器中挂载，尝试常规默认位置
    if [ -f "/var/lib/redis/dump.rdb" ]; then
        SRC_RDB="/var/lib/redis/dump.rdb"
    elif [ -f "./dump.rdb" ]; then
        SRC_RDB="./dump.rdb"
    else
        log "ERROR: 未找到源 RDB 文件 (${SRC_RDB})"
        exit 1
    fi
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DEST_FILE="${BACKUP_DIR}/redis_${TIMESTAMP}.rdb.gz"

log "INFO: 正在复制并压缩 ${SRC_RDB} -> ${DEST_FILE} ..."
gzip -c "${SRC_RDB}" > "${DEST_FILE}"

# 计算 SHA256 校验和
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${DEST_FILE}" | awk '{print $1}' > "${DEST_FILE}.sha256"
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${DEST_FILE}" | awk '{print $1}' > "${DEST_FILE}.sha256"
fi

FILE_SIZE=$(du -h "${DEST_FILE}" | cut -f1)
log "INFO: Redis 快照备份成功! 文件: ${DEST_FILE} (${FILE_SIZE})"

# 4. 清理过期文件
log "INFO: 正在清理超过 ${RETENTION_DAYS} 天的历史 Redis 备份..."
find "${BACKUP_DIR}" -name "redis_*.rdb.gz*" -type f -mtime +"${RETENTION_DAYS}" -exec rm -f {} + || true

log "INFO: Redis 备份流程全部完成。"
