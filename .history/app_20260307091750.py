from flask import Flask, render_template, jsonify

app = Flask(__name__)

# AI 应用列表（后续可扩展）
AI_APPS = [
    {
        "id": "Q001",
        "title": "AI 文本生成",
        "description": "基于大语言模型，智能生成高质量文章、报告、邮件等各类文本内容。",
        "icon": "text",
        "tag": "文本处理",
        "tag_type": "primary",
        "url": "/app/text-gen",
        "status": "coming_soon",
    },
    {
        "id": "Q002",
        "title": "AI 图像分析",
        "description": "上传图片，AI 自动识别图像内容、场景描述，支持多种图像理解任务。",
        "icon": "image",
        "tag": "视觉理解",
        "tag_type": "success",
        "url": "/app/image-analysis",
        "status": "coming_soon",
    },
    {
        "id": "Q003",
        "title": "AI 语音转写",
        "description": "将语音文件或实时语音精准转换为文字，支持多语言识别与标点还原。",
        "icon": "audio",
        "tag": "语音处理",
        "tag_type": "warning",
        "url": "/app/speech-to-text",
        "status": "coming_soon",
    },
    {
        "id": "Q004",
        "title": "AI 智能翻译",
        "description": "支持 100+ 语言互译，结合上下文理解，提供更自然流畅的翻译结果。",
        "icon": "translate",
        "tag": "语言处理",
        "tag_type": "primary",
        "url": "/app/translate",
        "status": "coming_soon",
    },
    {
        "id": "Q005",
        "title": "AI 代码助手",
        "description": "智能代码补全、代码审查、Bug 修复与代码解释，提升开发效率。",
        "icon": "code",
        "tag": "开发工具",
        "tag_type": "danger",
        "url": "/app/code-assistant",
        "status": "coming_soon",
    },
    {
        "id": "Q006",
        "title": "AI 数据分析",
        "description": "上传数据文件，AI 自动完成数据清洗、统计分析并生成可视化报告。",
        "icon": "chart",
        "tag": "数据处理",
        "tag_type": "success",
        "url": "/app/data-analysis",
        "status": "coming_soon",
    },
]


@app.route("/")
def index():
    return render_template("index.html", apps=AI_APPS)


@app.route("/api/apps")
def get_apps():
    return jsonify(AI_APPS)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
