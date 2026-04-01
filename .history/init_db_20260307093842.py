"""
数据库初始化脚本
用法: python init_db.py
功能:
  1. 创建所有数据表
  2. 插入样例辩题数据
"""

from app import app, db, DebateTopic

# 样例辩题数据
SAMPLE_TOPICS = [
    {
        "topic_id": "P001",
        "title": "家长该不该检查孩子的手机？",
        "description": "小明是一名初二学生，最近成绩下降，父母怀疑他沉迷手机。一天晚上，父母趁小明睡着偷偷检查了他的手机，发现他在和同学讨论游戏攻略。",
        "side_a": "家长有权检查孩子手机，这是对孩子负责的表现",
        "side_b": "家长不应检查孩子手机，应尊重孩子的隐私权",
        "category": "家庭教育",
    },
    {
        "topic_id": "P002",
        "title": "考试排名应不应该公开？",
        "description": "某中学一直公开张贴期末考试成绩排名，部分学生因此受到激励奋发学习，但也有学生因排名靠后感到自卑和焦虑，甚至出现厌学情绪。学校正在讨论是否取消公开排名。",
        "side_a": "应该公开排名，有助于激发竞争意识和学习动力",
        "side_b": "不应公开排名，会伤害学生自尊心，制造不必要的焦虑",
        "category": "学校管理",
    },
    {
        "topic_id": "P003",
        "title": "教师应不应该和学生做朋友？",
        "description": "李老师是一位年轻的班主任，她经常和学生一起吃午饭、聊天，甚至加了学生的微信好友。有家长担心这样会影响教师权威，也有家长认为这样更有利于了解学生。",
        "side_a": "教师应该和学生做朋友，亲近的关系有利于教育",
        "side_b": "教师应保持专业距离，过度亲近会削弱教育效果",
        "category": "师生关系",
    },
    {
        "topic_id": "P004",
        "title": "该不该取消家庭作业？",
        "description": "某小学试行"零作业"政策，将课后时间留给学生自由支配。部分家长非常支持，认为减轻了孩子负担；但也有家长焦虑，担心孩子学习跟不上，偷偷给孩子报了补习班。",
        "side_a": "应该取消家庭作业，让学生有更多自主发展时间",
        "side_b": "不应取消家庭作业，适量作业是巩固知识的必要手段",
        "category": "教学方法",
    },
    {
        "topic_id": "P005",
        "title": "差生应不应该被单独分班？",
        "description": "某中学按成绩将学生分为"重点班"和"普通班"。重点班配备了最优秀的教师，普通班的学生和家长对此颇有微词，认为这是教育不公平的体现。",
        "side_a": "按成绩分班有利于因材施教，提高教学效率",
        "side_b": "按成绩分班是教育歧视，加剧教育不公平",
        "category": "教育公平",
    },
    {
        "topic_id": "P006",
        "title": "幼儿园该不该教拼音和算术？",
        "description": "王女士的孩子即将上小学，周围很多家长都让孩子在幼儿园提前学习拼音和算术。王女士纠结是否也应该这样做——不学怕孩子输在起跑线，学了又担心破坏孩子的学习兴趣。",
        "side_a": "应该提前教学，帮助孩子更好地适应小学学习",
        "side_b": "不应提前教学，幼儿阶段应以游戏和探索为主",
        "category": "学前教育",
    },
]


def init_database():
    """初始化数据库并插入样例数据"""
    with app.app_context():
        # 创建所有表
        db.create_all()
        print("✓ 数据表创建成功")

        # 检查是否已有数据
        existing = DebateTopic.query.count()
        if existing > 0:
            print(f"  数据库已有 {existing} 个辩题，跳过样例数据插入")
            print(f"  如需重新插入，请先清空 debate_topics 表")
            return

        # 插入样例辩题
        for item in SAMPLE_TOPICS:
            topic = DebateTopic(
                topic_id=item["topic_id"],
                title=item["title"],
                description=item["description"],
                side_a=item["side_a"],
                side_b=item["side_b"],
                category=item["category"],
                is_active=True,
            )
            db.session.add(topic)

        db.session.commit()
        print(f"✓ 成功插入 {len(SAMPLE_TOPICS)} 个样例辩题")

        # 打印辩题列表
        print("\n--- 辩题列表 ---")
        for item in SAMPLE_TOPICS:
            print(f"  [{item['topic_id']}] {item['title']}")
            print(f"    正方: {item['side_a']}")
            print(f"    反方: {item['side_b']}")
            print()


if __name__ == "__main__":
    print("=" * 50)
    print("  Open Arena - 数据库初始化")
    print("=" * 50)
    print()
    init_database()
    print("初始化完成！")
