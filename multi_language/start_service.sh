#!/bin/bash
################################################################################
#
# 多语言识别服务启动脚本
#
################################################################################

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# 默认配置
HOST="0.0.0.0"
PORT=8007
#MODEL_PATH="$PROJECT_ROOT/model/lid.176.ftz"
MODEL_PATH="$PROJECT_ROOT/model/lid.176.bin"
# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印信息
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 检查模型文件
check_model() {
    if [ ! -f "$MODEL_PATH" ]; then
        print_error "模型文件不存在: $MODEL_PATH"
        print_info "请从以下地址下载模型文件:"
        print_info "https://fasttext.cc/docs/en/language-identification.html"
        exit 1
    fi
    print_info "模型文件检查通过: $MODEL_PATH"
}

# 检查依赖
check_dependencies() {
    print_info "检查 Python 依赖..."
    
    if ! python3 -c "import flask" 2>/dev/null; then
        print_warning "Flask 未安装，正在安装..."
        pip3 install flask
    fi
    
    if ! python3 -c "import fasttext" 2>/dev/null; then
        print_warning "fasttext 未安装，正在安装..."
        pip3 install fasttext
    fi
    
    print_info "依赖检查完成"
}

# 启动服务
start_service() {
    print_info "启动多语言识别服务..."
    print_info "服务地址: http://$HOST:$PORT"
    print_info "健康检查: http://$HOST:$PORT/health"
    print_info "预测接口: http://$HOST:$PORT/lang_predict"
    print_info ""
    print_info "按 Ctrl+C 停止服务"
    print_info "=========================================="
    
    cd "$SCRIPT_DIR"
    python3 multi_language_service.py \
        --host "$HOST" \
        --port "$PORT" \
        --model_path "$MODEL_PATH"
}

# 显示帮助信息
show_help() {
    cat << EOF
多语言识别服务启动脚本

使用方法:
    $0 [选项]

选项:
    -h, --help              显示帮助信息
    -H, --host HOST         服务监听地址 (默认: 0.0.0.0)
    -p, --port PORT         服务端口号 (默认: 6000)
    -m, --model MODEL_PATH  模型文件路径 (默认: ../model/lid.176.ftz)

示例:
    # 使用默认配置启动
    $0

    # 指定端口启动
    $0 --port 8080

    # 指定所有参数
    $0 --host 127.0.0.1 --port 8080 --model /path/to/lid.176.ftz

EOF
}

# 解析命令行参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -H|--host)
                HOST="$2"
                shift 2
                ;;
            -p|--port)
                PORT="$2"
                shift 2
                ;;
            -m|--model)
                MODEL_PATH="$2"
                shift 2
                ;;
            *)
                print_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# 主函数
main() {
    print_info "=========================================="
    print_info "多语言识别服务"
    print_info "=========================================="
    
    # 解析命令行参数
    parse_args "$@"
    
    # 检查模型文件
    check_model
    
    # 检查依赖
    check_dependencies
    
    # 启动服务
    start_service
}

# 运行主函数
main "$@"

