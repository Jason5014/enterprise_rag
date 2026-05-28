#!/usr/bin/env python3
"""DashScope API 连接测试"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

def test_basic_connection():
    """测试基本连接"""
    print("=" * 50)
    print("DashScope API 连接测试")
    print("=" * 50)

    # 1. 检查 API Key
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    if not api_key or api_key == "your_dashscope_api_key_here":
        print("[ERROR] 未设置 DASHSCOPE_API_KEY")
        print("请在 .env 文件中设置: DASHSCOPE_API_KEY=your_key")
        return False

    print(f"[OK] API Key: {api_key[:8]}...{api_key[-4:]}")

    # 2. 检查代理设置
    proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
    print("\n代理设置:")
    has_proxy = False
    for var in proxy_vars:
        val = os.getenv(var)
        if val:
            print(f"  {var} = {val}")
            has_proxy = True
    if not has_proxy:
        print("  (无代理设置)")

    # 3. 测试 dashscope 导入
    print("\n导入 dashscope...")
    try:
        import dashscope
        from dashscope import Generation
        print("[OK] dashscope 导入成功")
    except ImportError as e:
        print(f"[ERROR] 导入失败: {e}")
        return False

    # 4. 测试 API 调用
    print("\n测试 API 调用...")
    try:
        response = Generation.call(
            model="qwen-turbo",
            messages=[
                {"role": "user", "content": "你好，请回复'OK'"}
            ],
            api_key=api_key,
            result_format="message"
        )

        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            content = response.output.choices[0].message.content
            print(f"[OK] 响应内容: {content}")
            return True
        else:
            print(f"[ERROR] API 错误: {response.message}")
            return False

    except Exception as e:
        print(f"[ERROR] 调用异常: {type(e).__name__}: {e}")
        return False


def test_without_proxy():
    """测试禁用代理"""
    print("\n" + "=" * 50)
    print("尝试禁用代理连接")
    print("=" * 50)

    # 保存原始代理设置
    proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
    saved = {}
    for var in proxy_vars:
        saved[var] = os.environ.pop(var, None)

    try:
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        from dashscope import Generation

        response = Generation.call(
            model="qwen-turbo",
            messages=[
                {"role": "user", "content": "你好，请回复'OK'"}
            ],
            api_key=api_key,
            result_format="message"
        )

        if response.status_code == 200:
            content = response.output.choices[0].message.content
            print(f"[OK] 无代理连接成功: {content}")
            print("\n建议: 取消代理设置")
            print("  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy")
            return True
        else:
            print(f"[ERROR] API 错误: {response.message}")
            return False

    except Exception as e:
        print(f"[ERROR] 无代理也失败: {type(e).__name__}: {e}")
        return False
    finally:
        # 恢复代理设置
        for var, val in saved.items():
            if val is not None:
                os.environ[var] = val


if __name__ == "__main__":
    success = test_basic_connection()

    if not success:
        print("\n是否尝试无代理连接？(y/n)")
        choice = input().strip().lower()
        if choice == 'y':
            test_without_proxy()
