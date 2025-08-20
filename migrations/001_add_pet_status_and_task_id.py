#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import sqlite3

# 获取数据库路径
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../eternal_pal.db')

# 检查数据库文件是否存在
if not os.path.exists(db_path):
    print(f"错误：数据库文件不存在 - {db_path}")
    print("请确保应用程序已经初始化了数据库。")
    sys.exit(1)

try:
    # 连接到SQLite数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查pets表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pet';")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        print("错误：pets表不存在")
        print("请确保应用程序已经创建了必要的数据库表。")
        conn.close()
        sys.exit(1)
    
    # 检查status字段是否已经存在
    cursor.execute("PRAGMA table_info(pet);")
    columns = cursor.fetchall()
    column_names = [column[1] for column in columns]
    
    # 如果status字段不存在，则添加
    if 'status' not in column_names:
        print("添加status字段到pets表...")
        cursor.execute("ALTER TABLE pet ADD COLUMN status TEXT DEFAULT 'pending';")
        print("status字段添加成功。")
    else:
        print("status字段已经存在，跳过添加。")
    
    # 如果task_id字段不存在，则添加
    if 'task_id' not in column_names:
        print("添加task_id字段到pets表...")
        cursor.execute("ALTER TABLE pet ADD COLUMN task_id TEXT;")
        print("task_id字段添加成功。")
    else:
        print("task_id字段已经存在，跳过添加。")
    
    # 提交更改
    conn.commit()
    print("数据库迁移完成！")
    
    # 显示当前的表结构
    print("\n当前pets表结构：")
    cursor.execute("PRAGMA table_info(pet);")
    columns = cursor.fetchall()
    for column in columns:
        print(f"- {column[1]}: {column[2]}")
    
    # 显示数据库中的宠物记录数量（用于验证）
    cursor.execute("SELECT COUNT(*) FROM pet;")
    count = cursor.fetchone()[0]
    print(f"\n数据库中当前有 {count} 条宠物记录。")
    
except sqlite3.Error as e:
    print(f"数据库错误：{e}")
    # 如果发生错误，回滚事务
    if conn:
        conn.rollback()
    sys.exit(1)
except Exception as e:
    print(f"发生错误：{e}")
    if conn:
        conn.rollback()
    sys.exit(1)
finally:
    # 关闭数据库连接
    if conn:
        conn.close()
        print("数据库连接已关闭。")

print("\n提示：")
print("1. 此迁移脚本已经向pets表添加了status和task_id字段。")
print("2. status字段默认为'pending'，表示宠物创建但3D模型尚未生成完成。")
print("3. task_id字段用于关联异步任务ID，初始值为NULL。")
print("4. 为了确保应用程序正常运行，请重启Gunicorn服务。")