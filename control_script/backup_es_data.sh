#!/bin/bash

# ES数据备份脚本
# 支持备份所有索引或指定索引的数据到本地
# Author: Assistant
# Date: 2025-01-30

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 配置文件路径
CONFIG_PATH="$PROJECT_ROOT/config/config_es_engine.json"

# 检查配置文件是否存在
if [ ! -f "$CONFIG_PATH" ]; then
    echo "❌ 配置文件不存在: $CONFIG_PATH"
    echo "请确保ES配置文件存在"
    exit 1
fi

# 显示使用说明
show_usage() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --backup-all BACKUP_DIR              备份所有索引（默认排除 embedding，含其余全部字段）"
    echo "  --backup INDEX_NAME BACKUP_DIR       备份指定索引到指定目录"
    echo "  --backup-list INDEX1,INDEX2 DIR      备份指定索引列表到目录"
    echo "  --list-indexes                       列出所有索引"
    echo "  --format FORMAT                      备份格式 (json|ndjson) 默认: ndjson"
    echo "  --batch-size SIZE                    批处理大小，默认: 1000"
    echo "  --include-mapping                    包含索引mapping信息"
    echo "  --include-settings                   包含索引settings信息"
    echo "  --compress                           压缩备份文件"
    echo "  --exclude-system                     排除系统索引（默认排除）"
    echo "  --exclude-dense-vector               排除dense_vector字段（默认排除）"
    echo "  --include-dense-vector               包含dense_vector字段"
    echo "  --use-search-after                   强制使用search_after API（适用于阿里云ES等）"
    echo "  --dry-run                            试运行模式，只显示将要备份的信息"
    echo ""
    echo "示例:"
    echo "  $0 --list-indexes"
    echo "  $0 --backup letian /data/backup"
    echo "  $0 --backup-all /data/backup --compress"
    echo "  $0 --backup-list letian,meikeduo /data/backup --include-mapping"
    echo "  $0 --backup-all /data/backup --dry-run"
    echo "  $0 --backup-all /data/backup --include-dense-vector"
    echo "  $0 --backup-all /data/backup --use-search-after"
}

# 默认参数
BACKUP_FORMAT="ndjson"
BATCH_SIZE=1000
INCLUDE_MAPPING=""
INCLUDE_SETTINGS=""
COMPRESS=""
EXCLUDE_SYSTEM="--exclude-system"
EXCLUDE_DENSE_VECTOR="--exclude-dense-vector"
USE_SEARCH_AFTER=""
DRY_RUN=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --backup-all)
            ACTION="backup_all"
            BACKUP_DIR="$2"
            shift 2
            ;;
        --backup)
            ACTION="backup"
            INDEX_NAME="$2"
            BACKUP_DIR="$3"
            shift 3
            ;;
        --backup-list)
            ACTION="backup_list"
            INDEX_NAMES="$2"
            BACKUP_DIR="$3"
            shift 3
            ;;
        --list-indexes)
            ACTION="list_indexes"
            shift
            ;;
        --format)
            BACKUP_FORMAT="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --include-mapping)
            INCLUDE_MAPPING="--include-mapping"
            shift
            ;;
        --include-settings)
            INCLUDE_SETTINGS="--include-settings"
            shift
            ;;
        --compress)
            COMPRESS="--compress"
            shift
            ;;
        --exclude-system)
            EXCLUDE_SYSTEM="--exclude-system"
            shift
            ;;
        --include-system)
            EXCLUDE_SYSTEM=""
            shift
            ;;
        --exclude-dense-vector)
            EXCLUDE_DENSE_VECTOR="--exclude-dense-vector"
            shift
            ;;
        --include-dense-vector)
            EXCLUDE_DENSE_VECTOR="--include-dense-vector"
            shift
            ;;
        --use-search-after)
            USE_SEARCH_AFTER="--use-search-after"
            shift
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            echo "❌ 未知参数: $1"
            show_usage
            exit 1
            ;;
    esac
done

# 检查是否指定了操作
if [ -z "$ACTION" ]; then
    echo "❌ 必须指定操作"
    show_usage
    exit 1
fi

# 检查备份目录参数
if [[ "$ACTION" == "backup"* && -z "$BACKUP_DIR" ]]; then
    echo "❌ 必须指定备份目录"
    show_usage
    exit 1
fi

# 进入项目根目录
cd "$PROJECT_ROOT"

# 构建基本命令参数
BASE_ARGS="--config $CONFIG_PATH --format $BACKUP_FORMAT --batch-size $BATCH_SIZE"
if [ -n "$INCLUDE_MAPPING" ]; then
    BASE_ARGS="$BASE_ARGS $INCLUDE_MAPPING"
fi
if [ -n "$INCLUDE_SETTINGS" ]; then
    BASE_ARGS="$BASE_ARGS $INCLUDE_SETTINGS"
fi
if [ -n "$COMPRESS" ]; then
    BASE_ARGS="$BASE_ARGS $COMPRESS"
fi
if [ -n "$EXCLUDE_SYSTEM" ]; then
    BASE_ARGS="$BASE_ARGS $EXCLUDE_SYSTEM"
fi
if [ -n "$EXCLUDE_DENSE_VECTOR" ]; then
    BASE_ARGS="$BASE_ARGS $EXCLUDE_DENSE_VECTOR"
fi
if [ -n "$USE_SEARCH_AFTER" ]; then
    BASE_ARGS="$BASE_ARGS $USE_SEARCH_AFTER"
fi
if [ -n "$DRY_RUN" ]; then
    BASE_ARGS="$BASE_ARGS $DRY_RUN"
fi

# 执行相应操作
case $ACTION in
    list_indexes)
        echo "🔍 获取ES索引列表..."
        python3 -m knowledge_interface_tools.backup_es_data \
            $BASE_ARGS \
            --list-indexes
        ;;
    backup)
        echo "💾 备份索引 $INDEX_NAME 到 $BACKUP_DIR..."
        if [ -z "$DRY_RUN" ]; then
            # 创建备份目录
            mkdir -p "$BACKUP_DIR"
            if [ ! -d "$BACKUP_DIR" ]; then
                echo "❌ 无法创建备份目录: $BACKUP_DIR"
                exit 1
            fi
        fi
        python3 -m knowledge_interface_tools.backup_es_data \
            $BASE_ARGS \
            --index "$INDEX_NAME" \
            --backup-dir "$BACKUP_DIR"
        ;;
    backup_all)
        echo "💾 备份所有索引到 $BACKUP_DIR..."
        if [ -z "$DRY_RUN" ]; then
            # 创建备份目录
            mkdir -p "$BACKUP_DIR"
            if [ ! -d "$BACKUP_DIR" ]; then
                echo "❌ 无法创建备份目录: $BACKUP_DIR"
                exit 1
            fi
            
            # 确认操作
            echo "⚠️  警告：这将备份所有索引数据，可能需要较长时间和大量磁盘空间！"
        fi
        python3 -m knowledge_interface_tools.backup_es_data \
            $BASE_ARGS \
            --index "all" \
            --backup-dir "$BACKUP_DIR"
        ;;
    backup_list)
        echo "💾 备份索引列表 $INDEX_NAMES 到 $BACKUP_DIR..."
        if [ -z "$DRY_RUN" ]; then
            # 创建备份目录
            mkdir -p "$BACKUP_DIR"
            if [ ! -d "$BACKUP_DIR" ]; then
                echo "❌ 无法创建备份目录: $BACKUP_DIR"
                exit 1
            fi
        fi
        python3 -m knowledge_interface_tools.backup_es_data \
            $BASE_ARGS \
            --indexes "$INDEX_NAMES" \
            --backup-dir "$BACKUP_DIR"
        ;;
esac

echo ""
echo "✅ 操作完成" 
