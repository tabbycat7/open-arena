# -*- coding: utf-8 -*-
"""
教案设计竞技场 - 提示词模板字段定义
每个字段包含:
  - key:          字段唯一标识
  - label:        字段中文名
  - placeholder:  输入提示
  - hint:         字段说明（帮助用户填写）
  - required:     是否必填
  - type:         输入类型 (text / textarea / select)
  - options:      仅 select 类型使用，可选项列表
"""

PROMPT_FIELDS = [
    {
        "key": "grade_subject",
        "label": "学段与学科",
        "placeholder": "如：小学五年级语文",
        "hint": '明确教学身份，如"小学五年级语文""初中二年级数学"。',
        "required": True,
        "type": "text",
    },
    {
        "key": "teaching_style",
        "label": "教学风格/特点",
        "placeholder": "如：善于创设生活情境",
        "hint": '描述你的教学特色，如"善于创设生活情境""注重探究式学习""语言幽默生动"。',
        "required": True,
        "type": "text",
    },
    {
        "key": "semester_unit",
        "label": "学期阶段与单元",
        "placeholder": "如：上学期第三单元",
        "hint": '说明教学进度，如"上学期第三单元""下学期期中复习阶段"。',
        "required": True,
        "type": "text",
    },
    {
        "key": "knowledge_point",
        "label": "具体知识点",
        "placeholder": "如：两位数乘法的竖式计算",
        "hint": '明确本节课的核心内容，避免笼统。例如："两位数乘法的竖式计算"而非"乘法"。',
        "required": True,
        "type": "text",
    },
    {
        "key": "student_profile",
        "label": "学情描述",
        "placeholder": "如：已掌握加法进位，但乘法进位易出错",
        "hint": '简述学生已有基础、常见困难或兴趣点，如"已掌握加法进位，但乘法进位易出错""对古诗词意境想象较弱"。',
        "required": True,
        "type": "textarea",
    },
    {
        "key": "school_type",
        "label": "学校类型与地域",
        "placeholder": "如：乡镇中心小学",
        "hint": '填写学校背景，如"乡镇中心小学""城市实验学校""山区寄宿制学校"。',
        "required": True,
        "type": "text",
    },
    {
        "key": "tech_resources",
        "label": "技术设备与资源条件",
        "placeholder": "如：只有投影仪+黑板",
        "hint": '如实填写可用设备，如"只有投影仪+黑板""拥有智慧课堂平板系统""网络信号不稳定"。',
        "required": True,
        "type": "text",
    },
    {
        "key": "teaching_stage",
        "label": "其他要求",
        "placeholder": "如：加入XXX教育观",
        "hint": '补充说明对教案的进一步要求，如"加入XXX教育观""与前一课时衔接""突出实验探究"等。避免只写"设计一整节课"这类过宽表述。',
        "required": True,
        "type": "text",
    },
    {
        "key": "duration",
        "label": "时间",
        "placeholder": "如：8分钟",
        "hint": '明确时长，如"8分钟""15分钟"。控制生成内容的篇幅与复杂度。',
        "required": True,
        "type": "text",
    },
    {
        "key": "local_element",
        "label": "本土/地方元素",
        "placeholder": "如：用本地方言朗读童谣",
        "hint": '融入本地资源，如"用本地方言朗读童谣""结合本地红色景点讲解历史""引入本地传统手工艺案例"。',
        "required": True,
        "type": "text",
    },
    {
        "key": "output_format",
        "label": "呈现格式",
        "placeholder": "如：分步操作清单",
        "hint": '指定输出形式，如"分步操作清单""对话脚本""PPT大纲""学习任务单"。确保生成内容即拿即用。',
        "required": True,
        "type": "text",
    },
    {
        "key": "language_style",
        "label": "风格要求",
        "placeholder": "如：亲切口语化",
        "hint": '明确语言调性，如"亲切口语化""简洁指令式""富有感染力"。匹配教学对象与环节氛围。',
        "required": True,
        "type": "text",
    },
]

PROMPT_TEMPLATE = (
    "你是一位{grade_subject}教师，擅长{teaching_style}。"
    "本学期正处于{semester_unit}，教学内容为{knowledge_point}，"
    "学生{student_profile}。"
    "我所在的{school_type}学校现有{tech_resources}。"
    "请设计一个{teaching_stage}活动，时长约{duration}，"
    "要求融入{local_element}，以{output_format}呈现，"
    "语言风格{language_style}。"
)

RATING_DIMENSIONS = [
    {"key": "executable", "label": "是否可执行", "description": "教案设计是否具有可操作性，教师能否直接拿来使用"},
    {"key": "student_fit", "label": "是否符合学情", "description": "是否契合所描述的学生基础和学习特点"},
    {"key": "practical", "label": "是否扎实有用", "description": "教学内容是否扎实、有实际教学价值"},
    {"key": "local_integration", "label": "是否融合本土", "description": "是否有效融入了本土/地方元素"},
    {"key": "tech_usage", "label": "是否善用技术", "description": "是否合理利用了所描述的技术设备与资源"},
]


def get_prompt_fields():
    return PROMPT_FIELDS


def get_rating_dimensions():
    return RATING_DIMENSIONS


def build_prompt(form_data):
    """根据表单数据构建完整的提示词"""
    return PROMPT_TEMPLATE.format(**form_data)
