"""双击或 python restart.py 运行，会自动清理缓存并重启服务器"""
import os, sys, shutil, subprocess, time

# 1. 清理字节码缓存
cache = os.path.join(os.path.dirname(__file__), '__pycache__')
if os.path.exists(cache):
    shutil.rmtree(cache)
    print('已清理 __pycache__')

# 2. 杀掉占用 8000 端口的旧进程
try:
    result = subprocess.run(
        'netstat -ano | findstr ":8000 "',
        shell=True, capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if 'LISTENING' in line:
            pid = line.strip().split()[-1]
            subprocess.run(f'taskkill /PID {pid} /F', shell=True, capture_output=True)
            print(f'已终止进程 {pid}')
    time.sleep(1)
except Exception as e:
    print(f'终止旧进程时出错（忽略）: {e}')

# 3. 用 -B 参数启动服务器（跳过字节码缓存）
print('\n启动服务器 http://localhost:8000')
print('按 Ctrl+C 停止\n')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.execv(sys.executable, [sys.executable, '-B', 'server.py'])
