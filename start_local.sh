#!/usr/bin/env bash
set -euo pipefail

ALGOTRADING_DIR="/home/roshan/Downloads/Algotrading"
NEXUS_DIR="/home/roshan/nexus"
LOG_DIR="/tmp/algotrading_logs"
PYTHON="python3"
NEXUS_PYTHON="/home/roshan/nexus/venv/bin/python3"
NEXUS_PYTHON_LEGACY="/home/roshan/nexus/venv/bin/python"

mkdir -p "$LOG_DIR"

cleanup() {
    echo "Stopping all services..."
    for pid_file in "$LOG_DIR"/*.pid; do
        [ -f "$pid_file" ] && kill "$(cat "$pid_file")" 2>/dev/null && echo "Stopped $(basename "$pid_file" .pid)"
    done
    echo "All services stopped."
}

status() {
    echo "=== Service Status ==="
    for pid_file in "$LOG_DIR"/*.pid; do
        [ -f "$pid_file" ] || continue
        pid=$(cat "$pid_file")
        name=$(basename "$pid_file" .pid)
        if kill -0 "$pid" 2>/dev/null; then
            echo "  ✅ $name (PID $pid)"
        else
            echo "  ❌ $name (dead)"
        fi
    done
    echo ""
    echo "=== Dockers ==="
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "Docker not available"
    echo ""
    echo "=== NEXUS HTTP ==="
    curl -s http://127.0.0.1:8080/health 2>/dev/null || echo "Not responding"
    echo ""
    echo "=== Streamlit ==="
    curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8501 2>/dev/null || echo "Not responding"
}

start_service() {
    local name=$1
    local pid_file="$LOG_DIR/$name.pid"
    shift
    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "  ⏭️  $name already running (PID $(cat "$pid_file"))"
        return 0
    fi
    nohup "$@" > "$LOG_DIR/$name.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$pid_file"
    echo "  🚀 $name started (PID $pid)"
}

case "${1:-help}" in
    start)
        echo "Starting Algotrading project..."
        cd "$ALGOTRADING_DIR"
        export PYTHONPATH="$ALGOTRADING_DIR"

        echo ""
        echo "  ── Infrastructure (Docker) ──"
        echo "  ⚡ Redis, Postgres, MiroFish expected via docker-compose"

        echo ""
        echo "  ── NEXUS HTTP Daemon ──"
        start_service "nexus-http" "$NEXUS_PYTHON" "$NEXUS_DIR/server/nexus_http_daemon.py" --port 8080 --host 127.0.0.1

        echo ""
        echo "  ── NEXUS MCP Enhanced ──"
        start_service "nexus-mcp" "$NEXUS_PYTHON" "$NEXUS_DIR/server/nexus-mcp-enhanced.py"

        echo ""
        echo "  ── Strategy-KB MCP ──"
        start_service "strategy-kb" "$PYTHON" "$ALGOTRADING_DIR/strategy_db/mcp_server.py"

        echo ""
        echo "  ── Finance MCP ──"
        start_service "finance-mcp" "$PYTHON" "$ALGOTRADING_DIR/mcp_layer/finance_mcp_server.py"

        echo ""
        echo "  ── Streamlit UI ──"
        start_service "streamlit" "$PYTHON" -m streamlit run "$ALGOTRADING_DIR/ui/app.py" --server.port 8501 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false

        echo ""
        echo "All services started. Use '$0 status' to check."
        echo "Logs: $LOG_DIR/"
        echo "Streamlit: http://localhost:8501"
        echo "NEXUS: http://127.0.0.1:8080/health"
        ;;

    stop)
        cleanup
        ;;

    restart)
        cleanup
        sleep 2
        exec "$0" start
        ;;

    status)
        status
        ;;

    help|*)
        echo "Usage: $0 {start|stop|restart|status}"
        echo ""
        echo "  start   - Start all services"
        echo "  stop    - Stop all services"
        echo "  restart - Restart all services"
        echo "  status  - Show service status"
        ;;
esac
