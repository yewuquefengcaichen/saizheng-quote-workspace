# -*- coding: utf-8 -*-
"""启动报价系统"""
import subprocess
import sys
import os
import traceback
import importlib.util

# 写日志文件
log_file = open('server_debug.log', 'w', encoding='utf-8')

def log(msg):
    print(msg)
    log_file.write(msg + '\n')
    log_file.flush()

try:
    app_dir = r"D:\A赛正\完整导出的商品信息\claudecode-报价系统"
    os.chdir(app_dir)

    # 添加到sys.path
    sys.path.insert(0, app_dir)

    log(f"Python version: {sys.version}")
    log(f"Working directory: {os.getcwd()}")

    # 用别名加载 app.py，避免根目录 app.py 与 backend/app 包同名时互相遮蔽。
    # 如果直接 `from app import ...`，V2 后端里的 `from app.db...` 会被根模块 app.py 抢占。
    app_file = os.path.join(app_dir, 'app.py')
    spec = importlib.util.spec_from_file_location('saizheng_flask_app', app_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'无法加载 Flask 入口: {app_file}')
    flask_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = flask_module
    spec.loader.exec_module(flask_module)

    app = flask_module.app
    load_products = flask_module.load_products
    QuoteHistoryDB = flask_module.QuoteHistoryDB

    log("Imports successful")

    # 初始化
    os.makedirs('data', exist_ok=True)
    os.makedirs('output', exist_ok=True)
    db_path = os.path.join('data', 'quote_history.db')
    flask_module.quote_db = QuoteHistoryDB(db_path)
    load_products()

    log("Initialization complete")

    log("=" * 50)
    log("一键报价系统启动...")
    log("请访问: http://localhost:8080")
    log("=" * 50)

    # 使用waitress生产服务器
    from waitress import serve
    log("Starting waitress server on port 8080...")
    serve(app, host='127.0.0.1', port=8080)
    log("Server started successfully!")

except Exception as e:
    log(f"Error: {e}")
    traceback.print_exc(file=log_file)
finally:
    log_file.close()
