import os
import shutil
import datetime

BACKUP_DIR = 'backups'

def list_backups():
    if not os.path.exists(BACKUP_DIR):
        print(f"没有找到备份目录: {BACKUP_DIR}")
        return []
    
    backups = []
    for name in os.listdir(BACKUP_DIR):
        path = os.path.join(BACKUP_DIR, name)
        if os.path.isdir(path):
            backups.append(name)
    
    # 按名称倒序排列 (通常包含日期，所以新的在前面)
    backups.sort(reverse=True)
    return backups

def restore_backup(backup_name):
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    print(f"\n准备从 [{backup_name}] 恢复...")
    
    # 遍历备份文件夹中的文件
    for root, dirs, files in os.walk(backup_path):
        # 计算相对路径
        rel_path = os.path.relpath(root, backup_path)
        
        # 目标目录
        target_dir = os.getcwd() if rel_path == '.' else os.path.join(os.getcwd(), rel_path)
        
        # 确保目标文件夹存在 (如果备份里有子文件夹)
        if rel_path != '.' and not os.path.exists(target_dir):
            os.makedirs(target_dir)
            print(f"创建文件夹: {rel_path}")
            
        for file in files:
            src_file = os.path.join(root, file)
            dst_file = os.path.join(target_dir, file)
            
            # 复制覆盖
            try:
                shutil.copy2(src_file, dst_file)
                print(f"已恢复: {os.path.join(rel_path, file) if rel_path != '.' else file}")
            except Exception as e:
                print(f"恢复失败 {file}: {e}")

    print(f"\n✅ 恢复完成！")

def main():
    print("="*40)
    print("      原型生成器 - 备份恢复工具")
    print("="*40)
    
    backups = list_backups()
    if not backups:
        print("暂无可用备份。")
        input("按回车键退出...")
        return

    print("可用备份列表：")
    for i, name in enumerate(backups):
        print(f"[{i+1}] {name}")
    
    print("-" * 40)
    choice = input("请输入编号进行恢复 (输入 q 退出): ").strip()
    
    if choice.lower() == 'q':
        return
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(backups):
            target = backups[idx]
            confirm = input(f"⚠️  警告：这将覆盖当前项目中的文件。\n确认要恢复 [{target}] 吗？(y/n): ")
            if confirm.lower() == 'y':
                restore_backup(target)
            else:
                print("已取消。")
        else:
            print("无效的编号。")
    except ValueError:
        print("输入无效。")
    
    input("\n按回车键退出...")

if __name__ == '__main__':
    main()
