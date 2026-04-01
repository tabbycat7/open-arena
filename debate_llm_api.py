"""
大模型 API 调用封装
提供加持（润色）和反驳两个核心函数，统一调用 OpenAI 兼容接口。
支持多轮对话历史上下文。
"""

import requests
import config


def _call_chat_api(api_url, api_key, model, messages, temperature=0.7, max_tokens=4096):
    """
    调用 OpenAI 兼容的 Chat Completions API
    返回模型生成的文本内容，失败时抛出异常。
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    resp = requests.post(api_url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()

    data = resp.json()
    # 兼容 OpenAI 格式
    if "choices" in data and len(data["choices"]) > 0:
        return data["choices"][0]["message"]["content"].strip()

    raise ValueError(f"API 返回格式异常: {data}")


def _format_history_for_enhance(history):
    """
    将历史轮次格式化为加持模型可理解的上下文文本。
    history: [{"round": 1, "teacher": "...", "enhanced": "...", "rebuttal": "..."}, ...]
    """
    if not history:
        return ""

    lines = ["以下是之前的辩论历史："]
    for h in history:
        if h.get("enhanced") and h.get("rebuttal"):
            # 已完成的轮次
            lines.append(f"\n--- 第{h['round']}轮 ---")
            lines.append(f"教师原始观点：{h['teacher']}")
            lines.append(f"润色后观点：{h['enhanced']}")
            lines.append(f"对方反驳：{h['rebuttal']}")
        elif h.get("enhanced"):
            lines.append(f"\n--- 第{h['round']}轮 ---")
            lines.append(f"教师原始观点：{h['teacher']}")
            lines.append(f"润色后观点：{h['enhanced']}")
        else:
            # 当前轮次（尚未加持）
            lines.append(f"\n--- 第{h['round']}轮（当前） ---")
            lines.append(f"教师最新观点：{h['teacher']}")

    return "\n".join(lines)


def _format_history_for_refute(history):
    """
    将历史轮次格式化为反驳模型可理解的上下文文本。
    """
    if not history:
        return ""

    lines = ["以下是之前的辩论历史："]
    for h in history:
        if h.get("rebuttal"):
            lines.append(f"\n--- 第{h['round']}轮 ---")
            lines.append(f"对方观点（润色后）：{h['enhanced']}")
            lines.append(f"你的反驳：{h['rebuttal']}")
        elif h.get("enhanced"):
            # 当前轮次（已加持，等待反驳）
            lines.append(f"\n--- 第{h['round']}轮（当前） ---")
            lines.append(f"对方最新观点（润色后）：{h['enhanced']}")

    return "\n".join(lines)


def enhance_argument(topic_title, chosen_side_label, teacher_argument, history=None):
    """
    加持模型 —— 润色教师观点，使其论证更有力、逻辑更严密。
    支持多轮对话，包含历史上下文。

    参数:
        topic_title:       辩题标题
        chosen_side_label: 教师选择的立场描述
        teacher_argument:  教师本轮原始观点
        history:           历史轮次列表（可选）

    返回:
        str: 润色后的观点文本
    """
    history_text = _format_history_for_enhance(history) if history else ""

    system_content = (
        "你是一位资深的教育辩论专家。你的任务是对教师提出的辩论观点进行润色和增强。\n"
        "要求：\n"
        "1. 保持教师的核心立场不变\n"
        "2. 补充教育学理论依据（如建构主义、认知发展理论、社会学习理论等）\n"
        "3. 适当加入实证研究或权威数据支撑\n"
        "4. 优化论证结构，使逻辑更加严密\n"
        "5. 增强说服力和感染力\n"
        "6. 总字数严格控制在200-250字之间\n"
        "7. 直接输出润色后的观点，不要输出分析过程\n"
    )
    if history_text:
        system_content += (
            "8. 这是一场多轮辩论，请参考之前的辩论历史，特别是对方的反驳要点，"
            "帮助教师针对性地加强论证，弥补之前被反驳的薄弱环节\n"
        )

    user_content = ""
    if history_text:
        user_content += history_text + "\n\n"
    user_content += (
        f"辩题：{topic_title}\n"
        f"我的立场：{chosen_side_label}\n"
        f"我的本轮观点：{teacher_argument}\n\n"
        f"请对我的观点进行润色和增强："
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    return _call_chat_api(
        api_url=config.ENHANCE_MODEL_API_URL,
        api_key=config.ENHANCE_MODEL_API_KEY,
        model=config.ENHANCE_MODEL_NAME,
        messages=messages,
        temperature=0.7,
    )


def refute_argument(topic_title, enhanced_argument, opposite_side_label,
                    history=None, model_name=None):
    """
    反驳模型 —— 针对加持后的观点进行有力反驳。
    支持多轮对话，包含历史上下文。
    使用指定的模型名称（由会话锁定）。

    参数:
        topic_title:          辩题标题
        enhanced_argument:    加持后的观点（反驳对象）
        opposite_side_label:  反方立场描述
        history:              历史轮次列表（可选）
        model_name:           指定的反驳模型名称（可选，默认使用列表第一个）

    返回:
        str: 反驳内容文本
    """
    history_text = _format_history_for_refute(history) if history else ""

    system_content = (
        "你是一位犀利的教育辩论对手，擅长逻辑分析和批判性思维。你的任务是对对方的辩论观点进行有力反驳。\n"
        "要求：\n"
        "1. 找出对方论证中的逻辑漏洞或薄弱环节\n"
        "2. 适当引用反面的教育学理论或实证研究进行反驳\n"
        "3. 提出有力的反例或现实案例\n"
        "4. 论证结构清晰，层次分明\n"
        "5. 语气坚定但不失风度\n"
        "6. 总字数严格控制在200-250字之间\n"
        "7. 直接输出反驳内容，不要输出分析过程\n"
    )
    if history_text:
        system_content += (
            "8. 这是一场多轮辩论，请参考之前的辩论历史。注意对方可能已经针对你之前的反驳做了改进，"
            "你需要找到新的切入点进行反驳，避免简单重复之前的论点\n"
        )

    user_content = ""
    if history_text:
        user_content += history_text + "\n\n"
    user_content += (
        f"辩题：{topic_title}\n"
        f"对方的最新观点如下：\n{enhanced_argument}\n\n"
        f"你的立场：{opposite_side_label}\n"
        f"请对对方观点进行有力反驳："
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    # 使用指定的模型名称，若未指定则使用列表第一个
    if not model_name:
        model_name = config.REFUTE_MODEL_NAMES[0] if config.REFUTE_MODEL_NAMES else config.ENHANCE_MODEL_NAME

    return _call_chat_api(
        api_url=config.REFUTE_MODEL_API_URL,
        api_key=config.REFUTE_MODEL_API_KEY,
        model=model_name,
        messages=messages,
        temperature=0.8,
    )
