# Open Arena — MySQL 配置教程

本文档说明如何为 Open Arena 项目配置并初始化 MySQL 数据库。

---

## 一、前置要求

| 软件 | 最低版本 | 说明 |
|------|----------|------|
| MySQL / MariaDB | 8.0+ / 10.6+ | 数据库服务 |
| Python | 3.10+ | 项目运行环境 |
| pymysql | 1.1.0+ | 已在 `requirements.txt` 中声明 |
| cryptography | 42.0.0+ | pymysql 的 caching_sha2 认证依赖 |

---

## 二、创建数据库和用户

登录 MySQL 命令行（以 root 用户为例）：

```bash
mysql -u root -p
```

执行以下 SQL，创建项目所需的两个数据库及专用用户：

```sql
-- 主业务库（辩论竞技场 + 教案竞技场）
CREATE DATABASE IF NOT EXISTS open_arena
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- 多智能体教学地图库
CREATE DATABASE IF NOT EXISTS teaching_maps
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- 创建专用用户（建议不要直接用 root 连业务库）
CREATE USER IF NOT EXISTS 'arena_user'@'localhost' IDENTIFIED BY '替换为强密码';

-- 授权
GRANT ALL PRIVILEGES ON open_arena.*   TO 'arena_user'@'localhost';
GRANT ALL PRIVILEGES ON teaching_maps.* TO 'arena_user'@'localhost';
FLUSH PRIVILEGES;
```

> **提示**：如果本地开发图方便也可以直接使用 `root` 用户，将下面 `.env` 中的用户名改为 `root` 即可。

---

## 三、配置 `.env` 文件

项目根目录中已提供 `.env.example` 模板，将其复制为 `.env` 并填写数据库信息：

```bash
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

在 `.env` 中找到 `DATABASE_URL` 字段，按如下格式填写：

```dotenv
# 格式：mysql+pymysql://<用户名>:<密码>@<主机>:<端口>/<数据库名>?charset=utf8mb4
DATABASE_URL=mysql+pymysql://arena_user:替换为强密码@127.0.0.1:3306/open_arena?charset=utf8mb4
```

同时确认多智能体教学地图库的名称与第二步一致（默认 `teaching_maps`）：

```dotenv
TEACHING_MAP_MYSQL_DB=teaching_maps
```

> **注意**：`.env` 已被 `.gitignore` 忽略，密码不会意外提交到仓库。

---

## 四、`.env` 数据库相关字段说明

| 字段 | 说明 | 示例值 |
|------|------|--------|
| `DATABASE_URL` | 主业务库连接字符串，供 SQLAlchemy 使用 | `mysql+pymysql://root:pw@127.0.0.1:3306/open_arena?charset=utf8mb4` |
| `TEACHING_MAP_MYSQL_DB` | 多智能体教学地图使用的数据库名 | `teaching_maps` |

---

## 五、安装 Python 依赖

如果尚未安装依赖，先执行：

```bash
pip install -r requirements.txt
```

主要数据库相关依赖：

- `pymysql>=1.1.0` — Python 连接 MySQL 的驱动
- `flask-sqlalchemy>=3.1.0` — ORM 框架
- `cryptography>=42.0.0` — MySQL 8.0 新认证协议所需

---

## 六、初始化数据表

配置完成后，运行项目内置的初始化脚本，自动建表：

```bash
python init_db.py
```

成功后终端会输出：

```
==================================================
  Open Arena - 数据库初始化
==================================================

[OK] 数据表创建成功
  - debate_sessions, debate_rounds（辩论竞技场）
  - lesson_sessions, lesson_chat_rounds（教案设计竞技场）
```

该脚本会创建以下数据表：

| 数据表 | 所属模块 | 说明 |
|--------|----------|------|
| `debate_sessions` | 教育观辩论场 | 辩论会话主表 |
| `debate_rounds` | 教育观辩论场 | 每轮辩论内容 |
| `debate_session_owners` | 教育观辩论场 | 会话归属（访客绑定） |
| `lesson_sessions` | 教案设计竞技场 | 教案生成会话主表 |
| `lesson_chat_rounds` | 教案设计竞技场 | 多轮追问记录 |

> **多智能体教学地图** (`teaching_maps` 库) 的表结构由子应用在首次请求时自动创建，无需手动初始化。

---

## 七、验证连接是否正常

启动应用后访问任意功能页面，若页面正常加载且无数据库报错，即说明连接成功。

也可以用 Python 快速验证：

```bash
python -c "
from app import app, db
with app.app_context():
    db.engine.connect()
    print('数据库连接成功！')
"
```

---

## 八、常见问题排查

### 1. `Access denied for user` 报错
- 检查 `.env` 中的用户名和密码是否正确
- 确认该用户对 `open_arena` 数据库有 `ALL PRIVILEGES` 权限

### 2. `Unknown database 'open_arena'` 报错
- 确认已执行第二步中的 `CREATE DATABASE` 语句

### 3. `Authentication plugin 'caching_sha2_password' is not supported` 报错
- 确认已安装 `cryptography` 包：`pip install cryptography>=42.0.0`
- 或将 MySQL 用户改为旧认证方式（不推荐）：
  ```sql
  ALTER USER 'arena_user'@'localhost' IDENTIFIED WITH mysql_native_password BY '替换为强密码';
  ```

### 4. 连接超时 / `Can't connect to MySQL server`
- 确认 MySQL 服务已启动：
  ```bash
  # Windows
  net start MySQL80
  # macOS (Homebrew)
  brew services start mysql
  # Linux
  sudo systemctl start mysql
  ```
- 确认端口（默认 `3306`）未被防火墙屏蔽

### 5. 中文乱码
- 确保 `DATABASE_URL` 末尾包含 `?charset=utf8mb4`
- 确保建库时指定了 `CHARACTER SET utf8mb4`

---

## 九、完整配置速查（开发环境示例）

```dotenv
# .env（开发环境最小配置示例）
SECRET_KEY=dev-secret-key-change-in-prod

DATABASE_URL=mysql+pymysql://root:your_password@127.0.0.1:3306/open_arena?charset=utf8mb4
TEACHING_MAP_MYSQL_DB=teaching_maps
```

配置完成后，按顺序执行：

```bash
pip install -r requirements.txt   # 安装依赖
python init_db.py                  # 初始化数据表
python app.py                      # 启动应用
```

浏览器打开 `http://127.0.0.1:5000` 即可使用。
