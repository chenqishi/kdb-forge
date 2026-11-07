#!/bin/bash

# 批量更新ES索引中的del_flag字段
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
    echo "  --check INDEX_NAME          检查指定索引的del_flag覆盖情况"
    echo "  --update INDEX_NAME          更新指定索引的del_flag字段"
    echo "  --update-all INDEX1,INDEX2   批量更新多个索引"
    echo "  --dry-run INDEX_NAME         试运行模式（只检查不更新）"
    echo "  --value VALUE                设置del_flag默认值（默认: 0）"
    echo "  --batch-size SIZE            设置批处理大小（默认: 1000）"
    echo ""
    echo "示例:"
    echo "  $0 --check letian"
    echo "  $0 --update letian"
    echo "  $0 --update-all letian,meikeduo,qutian"
    echo "  $0 --dry-run letian --value 0"
}

# 默认参数
DEFAULT_VALUE=0
BATCH_SIZE=1000
DRY_RUN=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --check)
            ACTION="check"
            INDEX_NAME="$2"
            shift 2
            ;;
        --update)
            ACTION="update"
            INDEX_NAME="$2"
            shift 2
            ;;
        --update-all)
            ACTION="update_all"
            INDEX_NAMES="$2"
            shift 2
            ;;
        --dry-run)
            ACTION="dry_run"
            INDEX_NAME="$2"
            DRY_RUN="--dry-run"
            shift 2
            ;;
        --value)
            DEFAULT_VALUE="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
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

# 进入项目根目录
cd "$PROJECT_ROOT"

# 执行相应操作
case $ACTION in
    check)
        echo "🔍 检查索引 $INDEX_NAME 的del_flag覆盖情况..."
        python3 -m knowledge_interface_tools.update_del_flag_batch \
            --config "$CONFIG_PATH" \
            --index "$INDEX_NAME" \
            --dry-run
        ;;
    update)
        echo "🔄 更新索引 $INDEX_NAME 的del_flag字段..."
        python3 -m knowledge_interface_tools.update_del_flag_batch \
            --config "$CONFIG_PATH" \
            --index "$INDEX_NAME" \
            --value "$DEFAULT_VALUE" \
            --batch-size "$BATCH_SIZE"
        ;;
    update_all)
        echo "🔄 批量更新多个索引的del_flag字段..."
        python3 -m knowledge_interface_tools.update_del_flag_batch \
            --config "$CONFIG_PATH" \
            --indexes "$INDEX_NAMES" \
            --value "$DEFAULT_VALUE" \
            --batch-size "$BATCH_SIZE"
        ;;
    dry_run)
        echo "🔍 试运行模式 - 检查索引 $INDEX_NAME..."
        python3 -m knowledge_interface_tools.update_del_flag_batch \
            --config "$CONFIG_PATH" \
            --index "$INDEX_NAME" \
            --value "$DEFAULT_VALUE" \
            --batch-size "$BATCH_SIZE" \
            --dry-run
        ;;
esac

echo ""
echo "✅ 操作完成" 