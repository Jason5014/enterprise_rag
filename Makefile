# ============================================================
# 企业知识库 — Makefile
# ============================================================
# 用法：
#   make install       安装所有依赖（Python + Node）
#   make dev           同时启动后端 + 前端（需要 tmux 或两个终端）
#   make backend       仅启动 FastAPI 后端（:8000）
#   make frontend      仅启动 Vue3 前端 dev server（:5173）
#   make build         生产构建前端静态文件
#   make test          运行后端单元测试
#   make lint          检查前端 TypeScript 类型
# ============================================================

# Python 虚拟环境路径（优先使用上级课程共享 venv，否则用系统 python）
VENV ?= ../../.venv
PYTHON := $(shell [ -f $(VENV)/bin/python ] && echo $(VENV)/bin/python || echo python3)
PIP    := $(PYTHON) -m pip

BACKEND_PORT  ?= 8900
FRONTEND_PORT ?= 5173

.PHONY: all install install-python install-node dev backend frontend build test lint clean help

help:  ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---- 安装 -------------------------------------------------------

install: install-python install-node  ## 安装所有依赖

install-python:  ## 安装 Python 依赖
	@echo "→ 安装 Python 依赖..."
	$(PIP) install -q -r requirements.txt
	@echo "✓ Python 依赖安装完成"

install-node:  ## 安装 Node.js 依赖
	@echo "→ 安装 Node.js 依赖..."
	cd frontend && npm install
	@echo "✓ Node.js 依赖安装完成"

# ---- 开发启动 ---------------------------------------------------

backend:  ## 启动 FastAPI 后端（端口 8000）
	@echo "→ 启动后端 http://localhost:$(BACKEND_PORT)"
	@echo "   API 文档: http://localhost:$(BACKEND_PORT)/docs"
	$(PYTHON) -m uvicorn backend.main:app \
		--reload \
		--port $(BACKEND_PORT) \
		--log-level info

frontend:  ## 启动 Vue3 前端开发服务（端口 5173，代理 /api → :8900）
	@echo "→ 启动前端 http://localhost:$(FRONTEND_PORT)"
	cd frontend && npm run dev -- --port $(FRONTEND_PORT)

dev:  ## 并行启动后端和前端（需系统安装 tmux；或分两个终端分别运行 make backend / make frontend）
	@if command -v tmux >/dev/null 2>&1; then \
		tmux new-session -d -s rag -n backend "$(MAKE) backend"; \
		tmux new-window -t rag -n frontend "$(MAKE) frontend"; \
		tmux select-window -t rag:backend; \
		tmux attach-session -t rag; \
	else \
		echo "未检测到 tmux，请分两个终端分别运行："; \
		echo "  终端 1: make backend"; \
		echo "  终端 2: make frontend"; \
	fi

# ---- 生产构建 ---------------------------------------------------

build:  ## 生产构建前端静态文件（输出到 frontend/dist/）
	@echo "→ 构建前端..."
	cd frontend && npm run build
	@echo "✓ 构建完成，产物在 frontend/dist/"

# ---- 检查 -------------------------------------------------------

test:  ## 运行后端单元测试
	$(PYTHON) -m pytest tests/ -v

lint:  ## 检查前端 TypeScript 类型
	cd frontend && npm run type-check

# ---- 清理 -------------------------------------------------------

clean:  ## 清理构建产物和缓存
	rm -rf frontend/dist frontend/.vite
	find . -type d -name __pycache__ | xargs rm -rf
	find . -type d -name .pytest_cache | xargs rm -rf
