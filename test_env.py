#!/usr/bin/env python3
"""测试环境变量读取"""
import os
from app.config import get_settings

if __name__ == "__main__":
    print("=== 测试环境变量读取 ===")
    settings = get_settings()
    
    print(f"DEEPSEEK_API_KEY: {'已设置' if settings.deepseek_api_key else '未设置'}")
    print(f"DEEPSEEK_BASE_URL: {settings.deepseek_base_url}")
    print(f"IMAGE_API_KEY: {'已设置' if settings.image_api_key else '未设置'}")
    print(f"IMAGE_BASE_URL: {settings.image_base_url}")
    
    print(f"deepseek_ready: {settings.deepseek_ready}")
    print(f"image_ready: {settings.image_ready}")
    
    # 打印当前工作目录和文件
    print(f"\n当前工作目录: {os.getcwd()}")
    print(f"目录中的文件: {os.listdir('.')}")
    
    if os.path.exists('.env'):
        print("找到 .env 文件")
    if os.path.exists('.env.local'):
        print("找到 .env.local 文件")