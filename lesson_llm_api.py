"""
教案设计竞技场 - 大模型 API 调用封装
调用 OpenAI 兼容接口，根据用户填写的提示词模板生成教案。
支持多轮对话（追问 / 修改要求）。
"""

import requests
import config


def _call_chat_api(model, messages, temperature=0.7, max_tokens=4096):
    headers = {
        "Authorization": f"Bearer {config.LESSON_MODEL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    resp = requests.post(
        config.LESSON_MODEL_API_URL,
        json=payload,
        headers=headers,
        timeout=120,
    )
    resp.raise_for_status()

    data = resp.json()
    if "choices" in data and len(data["choices"]) > 0:
        return data["choices"][0]["message"]["content"].strip()

    raise ValueError(f"API 返回格式异常: {data}")


def generate_lesson_plan(prompt_text, history=None, model_name=None):
    """
    生成教案设计方案。

    参数:
        prompt_text:  用户根据模板组装好的完整提示词
        history:      多轮对话历史 [{"role":"user","content":"..."},{"role":"assistant","content":"..."}, ...]
        model_name:   使用的模型名称

    返回:
        str: 模型生成的教案文本
    """
    if not model_name:
        model_name = config.LESSON_MODEL_NAMES[0]

    system_content = (
        "你是一位经验丰富的教学设计专家，擅长根据教师提供的具体教学条件和需求，"
        "设计切实可行的教学活动方案。你的设计应当：\n"
        "1. 紧扣教师提供的知识点和教学环节\n"
        "2. 充分考虑学生的已有基础和学习困难\n"
        "3. 合理利用学校现有技术设备\n"
        "4. 有效融入本土/地方元素\n"
        "5. 按照指定的呈现格式输出，确保教师即拿即用\n"
        "6. 语言风格匹配教师的要求\n"
        "7. 设计内容在指定时间内可完成\n"
        "请直接输出教案内容，不要输出分析过程。"
    )

    messages = [{"role": "system", "content": system_content}]

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": prompt_text})

    return _call_chat_api(
        model=model_name,
        messages=messages,
        temperature=0.7,
    )
