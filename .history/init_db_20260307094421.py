"""
数据库初始化脚本
用法: python init_db.py
功能: 创建辩论会话数据表（debate_sessions）
注意: 辩题数据保存在 topics.py 中，不存入数据库
"""

from app import app, db


def init_database():
    """初始化数据库：创建数据表"""
    with app.app_context():
        db.create_all()
        print("✓ 数据表创建成功（debate_sessions）")
        print()
        print("说明：")
        print("  - 辩题数据保存在 topics.py 文件中，如需修改辩题请直接编辑该文件")
        print("  - 数据库仅存储辩论过程中产生的会话数据")
        print("  - 数据库连接信息配置在 .env 文件中")


if __name__ == "__main__":
    print("=" * 50)
    print("  Open Arena - 数据库初始化")
    print("=" * 50)
    print()
    init_database()
    print()
    print("初始化完成！")
