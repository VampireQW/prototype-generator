# -*- coding: utf-8 -*-
"""
数据迁移脚本
将现有 projects.json 中的项目分配给指定用户

用法:
  python migrate.py <username>
  
如果用户不存在，会提示创建。
"""

import sys
import os
import json

# 确保从项目根目录运行
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import db

def main():
    if len(sys.argv) < 2:
        print("用法: python migrate.py <username>")
        print("将所有现有项目分配给该用户")
        sys.exit(1)
    
    username = sys.argv[1]
    
    # 初始化数据库
    db.init_db()
    
    # 查找用户
    user = db.get_user_by_username(username)
    if not user:
        print(f"用户 '{username}' 不存在。")
        password = input("请输入密码为该用户创建账号: ").strip()
        if not password or len(password) < 6:
            print("密码至少 6 个字符")
            sys.exit(1)
        display_name = input("显示名称 (留空使用用户名): ").strip() or username
        user = db.create_user(username, password, display_name)
        if not user:
            print("创建用户失败")
            sys.exit(1)
        print(f"✅ 用户创建成功: {user['username']} (ID: {user['id']})")
    else:
        print(f"找到用户: {user['username']} (ID: {user['id']})")
    
    # 读取项目列表
    projects_file = os.path.join('data', 'projects.json')
    if not os.path.exists(projects_file):
        print("项目列表为空，无需迁移")
        sys.exit(0)
    
    with open(projects_file, 'r', encoding='utf-8') as f:
        projects = json.load(f)
    
    if not projects:
        print("项目列表为空，无需迁移")
        sys.exit(0)
    
    # 分配所有没有 owner 的项目
    count = 0
    for p in projects:
        project_id = p['id']
        existing_owner = db.get_project_owner(project_id)
        if existing_owner is None:
            db.set_project_owner(project_id, user['id'])
            count += 1
            print(f"  → {project_id}")
    
    print(f"\n✅ 迁移完成: {count} 个项目已分配给 {user['username']}")
    print(f"   共 {len(projects)} 个项目，其中 {len(projects) - count} 个已有归属")

if __name__ == '__main__':
    main()
