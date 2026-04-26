# -*- coding: utf-8 -*-
"""赛正报价工作台启动入口。

目标：
1. 统一从仓库根目录启动 Flask 工作台
2. 优先切换到 `backend/.venv`，保证图搜图 / CLIP / PostgreSQL V2 能力可用
3. 保留启动日志，方便排查 Windows 本地环境问题
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import traceback


APP_DIR = Path(__file__).resolve().parent
BACKEND_VENV_PYTHON = APP_DIR / 'backend' / '.venv' / 'Scripts' / 'python.exe'
REEXEC_ENV_FLAG = 'SAIZHENG_SKIP_VENV_REEXEC'
LOG_PATH = APP_DIR / 'server_debug.log'


def log(message: str, *, handle) -> None:
    print(message, flush=True)
    handle.write(f'{message}\n')
    handle.flush()


def ensure_backend_venv_python() -> None:
    """如果当前不是 backend/.venv，就自动切到它。"""
    current_python = Path(sys.executable).resolve()
    target_python = BACKEND_VENV_PYTHON.resolve() if BACKEND_VENV_PYTHON.exists() else None

    if target_python is None:
        return
    if current_python == target_python:
        return
    if os.environ.get(REEXEC_ENV_FLAG) == '1':
        return

    env = os.environ.copy()
    env[REEXEC_ENV_FLAG] = '1'
    args = [str(target_python), str(Path(__file__).resolve()), *sys.argv[1:]]
    if os.name == 'nt':
        completed = subprocess.run(args, env=env)
        raise SystemExit(completed.returncode)
    os.execve(str(target_python), args, env)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='启动赛正报价工作台服务')
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.environ.get('SAIZHENG_PORT', '8080')),
        help='监听端口，默认 8080',
    )
    parser.add_argument(
        '--host',
        default=os.environ.get('SAIZHENG_HOST', '127.0.0.1'),
        help='监听地址，默认 127.0.0.1',
    )
    return parser.parse_args()


def main() -> int:
    ensure_backend_venv_python()
    args = parse_args()

    with LOG_PATH.open('w', encoding='utf-8') as log_file:
        try:
            os.chdir(APP_DIR)
            sys.path.insert(0, str(APP_DIR))

            log(f'Python executable: {sys.executable}', handle=log_file)
            log(f'Python version: {sys.version}', handle=log_file)
            log(f'Working directory: {os.getcwd()}', handle=log_file)
            log(f'Backend venv python: {BACKEND_VENV_PYTHON}', handle=log_file)

            app_file = APP_DIR / 'app.py'
            spec = importlib.util.spec_from_file_location('saizheng_flask_app', app_file)
            if spec is None or spec.loader is None:
                raise RuntimeError(f'无法加载 Flask 入口：{app_file}')

            flask_module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = flask_module
            spec.loader.exec_module(flask_module)

            app = flask_module.app
            load_products = flask_module.load_products
            quote_history_db_cls = flask_module.QuoteHistoryDB

            os.makedirs(APP_DIR / 'data', exist_ok=True)
            os.makedirs(APP_DIR / 'output', exist_ok=True)
            db_path = str(APP_DIR / 'data' / 'quote_history.db')
            flask_module.quote_db = quote_history_db_cls(db_path)
            load_products()

            log('=' * 60, handle=log_file)
            log('赛正报价工作台启动中...', handle=log_file)
            log(f'访问地址：http://{args.host}:{args.port}', handle=log_file)
            log('=' * 60, handle=log_file)

            from waitress import serve

            log(f'Starting waitress server on {args.host}:{args.port} ...', handle=log_file)
            serve(app, host=args.host, port=args.port)
            log('Server stopped normally.', handle=log_file)
            return 0

        except Exception as exc:
            log(f'Error: {exc}', handle=log_file)
            traceback.print_exc(file=log_file)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
