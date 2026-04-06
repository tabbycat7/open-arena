# Open Arena - AI 教育平台

Open Arena 是一个基于大语言模型（LLM）和多智能体（Multi-Agent）技术构建的综合性教师教研辅助与测评平台。本项目旨在通过 AI 的介入，为教师、师范生提供创新的教育研讨、教案测评以及自动化的教案生成工具。

## 🌟 核心功能模块

项目当前主要包含三大核心子应用，均可通过平台首页（AI 应用卡片）快速访问：

### 1. 🎭 教育观辩论场 (Debate Arena)
将教育观结合现实生活场景改造为特定辩题。系统提供「加持」（辅助补充）与「反驳」（对立视角）双模型机制，由教师与 AI 进行深度辩论，以此测评并刻画教师的底层教育观。
- **预设题库**：内置了 40 道精心设计的教育观辩题（如：应试教育与素质教育的取舍、教案难度的把控等）。
- **双模型辅导**：全程提供多视角的思辨反馈与对话式交互。

### 2. ⚔️ 教案设计竞技场 (Lesson Plan Arena)
通过填入具体的教学阶段、主题与要求，系统将同时并行调用两个不同的大模型生成两份教案。
- **盲测比对评估**：支持用户在隐藏生成方身份的情况下，对生成的教案进行多维度打分和评估对比。
- **多轮次追问**：支持基于生成的教案，进行无缝的多轮次追问与细节调优。

### 3. 🗺️ 多智能体教学地图 (Multi-Agent Teaching Map)
基于 `LangGraph` 框架开发的多智能体协作应用子模块，实现对高维教学设计的结构化产出。
- **自动结构化**：生成覆盖目标、学情、逻辑与脚手架搭建的教学地图。
- **Agent 分工审批**：由不同的生成节点（Generators）与校验节点（Validators）共同完成图流转。
- **过程追踪与回溯**：地图与侧边栏结合，完整呈现多智能体网络的思考路径和状态。
- **附件融合输入**：支持上传 txt/md/pdf/docx 与教材图片（png/jpg/webp 等），后端自动提取文本后注入工作流。

## 🛠️ 技术栈概览

- **后端架构**：Python, Flask, SQLAlchemy (SQLite)
- **大模型生态**：LangChain / LangGraph 编排工作流，各类主流大语言模型 API 接入封装。
- **前端实现**：HTML5, 原生 CSS3 响应式设计, Vanilla JS (结合 Jinja2 进行模板渲染)。

## 📁 核心目录结构

```text
open_arena/
├── app.py                      # 主应用入口，Flask 路由映射及应用注册
├── config.py                   # 全局环境变量及模型配置参数
├── init_db.py                  # 数据库初始化脚本
├── topics.py                   # 辩论场预置的 40+ 辩题独立配置文件
├── llm_api.py                  # 双模型辩论场 API 封装
├── lesson_llm_api.py           # 教案设计竞技场 API 封装
├── multi_agent_teaching/       # 【多智能体教学地图】独立子应用
│   ├── app.py                  # 子应用专属路由注册
│   ├── agents/                 # 图结构定义、状态管理及节点定义
│   ├── prompts/                # 对应节点使用的系统提示词（txt/md）
│   └── templates/ & static/    # 子应用的静态资源与页面
├── static/                     # 全局静态资源 (CSS/JS)
├── templates/                  # 全局 Jinja2 页面模板 (首页/历史记录等)
├── requirements.txt            # Python 依赖清单
└── .env                        # [需手建/配置] 本地环境变量（如各模型 API Key）
```

## 🚀 快速启动

### 1. 环境准备
推荐使用 Conda 隔离运行环境：
```bash
conda create -n StudentAgent python=3.10
conda activate StudentAgent
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 环境变量配置
在项目根目录编辑 `.env` 文件，填入所需的大模型 API Key。

### 4. 初始化数据库
首次运行或清除记录后，生成本地 `.db` 文件及相关表结构：
```bash
python init_db.py
```

### 5. 启动应用
使用 Python 启动主应用，访问内置的 Web 界面：
```bash
python app.py
```
> 控制台显示 `Running on http://127.0.0.1:5000` 后，用浏览器打开该地址即可。

### 6. 多智能体假 API 边界测试
当你想快速回放重试、校验失败、解析异常等边界情况，而不依赖真实大模型时，可启用内置 fake API：

```bash
set TEACHING_MAP_FAKE_API=1
我们把‘每年本金乘1.05’的规律，翻译成标准的数学表达式吧。如果底数不小心取成1或者负数，这个函数会出什么‘bug’？为什么必须规定a>0且a≠1？
```

可选：只跑部分场景

```bash
python multi_agent_teaching/run_fake_workflow_tests.py --scenarios all_pass main_retry_once
```

可选：加载自定义场景脚本（格式见 `multi_agent_teaching/fake_scenarios.example.json`）

```bash
set TEACHING_MAP_FAKE_SCENARIO_FILE=multi_agent_teaching/fake_scenarios.example.json
python multi_agent_teaching/run_fake_workflow_tests.py --scenarios custom_main_fail_twice
```

## 📝 规划扩展 (Coming Soon)
- 🌐 AI 智能翻译（支持泛上下文语言处理）
- 💻 AI 代码助手（编程辅导与重构）
- 📊 AI 数据分析（自动化清洗数据、生可视化图表）
