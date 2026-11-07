#!/bin/bash

# 自动补充ES索引中缺失的字段
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
    echo "  --check INDEX_NAME           检查指定索引的字段覆盖情况"
    echo "  --check-all                  检查所有索引的字段覆盖情况"
    echo "  --supply INDEX_NAME          为指定索引补充缺失字段"
    echo "  --supply-all                 为所有索引补充缺失字段"
    echo "  --supply-list INDEX1,INDEX2  为指定的多个索引补充字段"
    echo "  --field FIELD_NAME           指定字段名称（默认: del_flag）"
    echo "  --value VALUE                设置字段默认值（默认: 0）"
    echo "  --type FIELD_TYPE            设置字段类型（默认: integer）"
    echo "  --batch-size SIZE            设置批处理大小（默认: 1000）"
    echo "  --dry-run                    试运行模式（只检查不更新）"
    echo "  --include-system             包含系统索引（默认排除）"
    echo "  --dynamic-fields FIELDS      动态字段补充模式（支持: from_type_norm,tags,dataset,primary_category）"
    echo "  --mode MODE                  补充模式: static(默认) 或 dynamic"
    echo "  --force                      强制更新已有字段（仅对动态模式有效）"
    echo ""
    echo "示例:"
    echo "  $0 --check letian"
    echo "  $0 --check-all"
    echo "  $0 --supply letian"
    echo "  $0 --supply-all --dry-run"
    echo "  $0 --supply-list letian,meikeduo,qutian"
    echo "  $0 --supply letian --field status --value 1 --type integer"
    echo "  $0 --supply-all --mode dynamic --dynamic-fields from_type_norm,tags"
    echo "  $0 --supply letian --mode dynamic --dynamic-fields from_type_norm"
    echo "  $0 --supply-all --mode dynamic --dynamic-fields dataset"
    echo "  $0 --supply letian --mode dynamic --dynamic-fields dataset"
    echo "  $0 --supply letian --mode dynamic --dynamic-fields primary_category   # 为缺失 primary_category 的文档补默认分组"
    echo "  $0 --supply-all --mode dynamic --dynamic-fields primary_category       # 为所有索引补充 primary_category"
    echo "  $0 --supply-all --mode dynamic --dynamic-fields from_type_norm --force  # 强制重刷所有索引的from_type_norm字段"
}

# 默认参数
FIELD_NAME="del_flag"
FIELD_VALUE=0
FIELD_TYPE="integer"
BATCH_SIZE=1000
DRY_RUN=""
EXCLUDE_SYSTEM="--exclude-system"
MODE="static"
DYNAMIC_FIELDS=""
FORCE=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --check)
            ACTION="check"
            INDEX_NAME="$2"
            shift 2
            ;;
        --check-all)
            ACTION="check_all"
            shift
            ;;
        --supply)
            ACTION="supply"
            INDEX_NAME="$2"
            shift 2
            ;;
        --supply-all)
            ACTION="supply_all"
            shift
            ;;
        --supply-list)
            ACTION="supply_list"
            INDEX_NAMES="$2"
            shift 2
            ;;
        --field)
            FIELD_NAME="$2"
            shift 2
            ;;
        --value)
            FIELD_VALUE="$2"
            shift 2
            ;;
        --type)
            FIELD_TYPE="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --include-system)
            EXCLUDE_SYSTEM=""
            shift
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --dynamic-fields)
            DYNAMIC_FIELDS="$2"
            shift 2
            ;;
        --force)
            FORCE="--force"
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

# 进入项目根目录
cd "$PROJECT_ROOT"

# 构建基本命令参数
BASE_ARGS="--config $CONFIG_PATH --mode $MODE --batch-size $BATCH_SIZE"

if [ "$MODE" == "dynamic" ]; then
    if [ -z "$DYNAMIC_FIELDS" ]; then
        echo "❌ 动态模式下必须指定 --dynamic-fields 参数"
        exit 1
    fi
    BASE_ARGS="$BASE_ARGS --dynamic-fields $DYNAMIC_FIELDS"
else
    BASE_ARGS="$BASE_ARGS --field $FIELD_NAME --value $FIELD_VALUE --type $FIELD_TYPE"
fi

if [ -n "$DRY_RUN" ]; then
    BASE_ARGS="$BASE_ARGS $DRY_RUN"
fi
if [ -n "$EXCLUDE_SYSTEM" ]; then
    BASE_ARGS="$BASE_ARGS $EXCLUDE_SYSTEM"
fi
if [ -n "$FORCE" ]; then
    BASE_ARGS="$BASE_ARGS $FORCE"
fi

# 执行相应操作
case $ACTION in
    check)
        if [ "$MODE" == "dynamic" ]; then
            echo "🔍 检查索引 $INDEX_NAME 的动态字段 $DYNAMIC_FIELDS 覆盖情况..."
        else
            echo "🔍 检查索引 $INDEX_NAME 的字段 $FIELD_NAME 覆盖情况..."
        fi
        python3 -m knowledge_interface_tools.supply_missing_field \
            $BASE_ARGS \
            --index "$INDEX_NAME" \
            --dry-run
        ;;
    check_all)
        if [ "$MODE" == "dynamic" ]; then
            echo "🔍 检查所有索引的动态字段 $DYNAMIC_FIELDS 覆盖情况..."
        else
            echo "🔍 检查所有索引的字段 $FIELD_NAME 覆盖情况..."
        fi
        python3 -m knowledge_interface_tools.supply_missing_field \
            $BASE_ARGS \
            --index "all" \
            --dry-run
        ;;
    supply)
        if [ "$MODE" == "dynamic" ]; then
            echo "🔄 为索引 $INDEX_NAME 补充动态字段 $DYNAMIC_FIELDS..."
        else
            echo "🔄 为索引 $INDEX_NAME 补充字段 $FIELD_NAME..."
        fi
        python3 -m knowledge_interface_tools.supply_missing_field \
            $BASE_ARGS \
            --index "$INDEX_NAME"
        ;;
    supply_all)
        if [ "$MODE" == "dynamic" ]; then
            echo "🔄 为所有索引补充动态字段 $DYNAMIC_FIELDS..."
        else
            echo "🔄 为所有索引补充字段 $FIELD_NAME..."
        fi
        python3 -m knowledge_interface_tools.supply_missing_field \
            $BASE_ARGS \
            --index "all"
        ;;
    supply_list)
        if [ "$MODE" == "dynamic" ]; then
            echo "🔄 为指定索引列表补充动态字段 $DYNAMIC_FIELDS..."
        else
            echo "🔄 为指定索引列表补充字段 $FIELD_NAME..."
        fi
        python3 -m knowledge_interface_tools.supply_missing_field \
            $BASE_ARGS \
            --indexes "$INDEX_NAMES"
        ;;
esac

echo ""
echo "✅ 操作完成" 
