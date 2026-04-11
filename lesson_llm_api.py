"""
教案设计竞技场 - 大模型 API 调用封装
调用 OpenAI 兼容接口，根据用户填写的提示词模板生成教案。
支持多轮对话（追问 / 修改要求）。
"""

from openai import APIError, APIStatusError, OpenAI
import config


def _normalize_openai_base_url(api_url):
    base_url = (api_url or "").strip().rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    if not base_url.endswith("/v1"):
        if base_url.endswith("/v1/"):
            base_url = base_url[:-1]
    return base_url + "/"


def _should_use_max_completion_tokens(model):
    model_name = (model or "").strip().lower()
    return model_name.startswith("gpt-5")


def _extract_status_error_body(error):
    if getattr(error, "response", None) is None:
        return ""
    try:
        return error.response.text or ""
    except Exception:
        return str(error.response)


def _call_chat_api(model, messages, temperature=0.7, max_tokens=4096):
    base_url = _normalize_openai_base_url(config.LESSON_MODEL_API_URL)
    api_key = (config.LESSON_MODEL_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError(f"上游模型接口请求失败: model={model}, detail=API Key 未配置")
    client = OpenAI(api_key=api_key, base_url=base_url)
    use_completion_tokens = _should_use_max_completion_tokens(model)
    request_kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "timeout": 120,
    }
    if use_completion_tokens:
        request_kwargs["max_completion_tokens"] = max_tokens
    else:
        request_kwargs["max_tokens"] = max_tokens

    try:
        completion = client.chat.completions.create(**request_kwargs)
    except APIStatusError as e:
        body = _extract_status_error_body(e)
        if (not use_completion_tokens) and ("max_completion_tokens" in body):
            retry_kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "timeout": 120,
                "max_completion_tokens": max_tokens,
            }
            try:
                completion = client.chat.completions.create(**retry_kwargs)
            except APIStatusError as retry_e:
                retry_body = _extract_status_error_body(retry_e)
                retry_preview = retry_body.strip()[:1000] if retry_body else "<empty body>"
                raise RuntimeError(
                    f"上游模型接口返回错误: status={retry_e.status_code}, model={model}, body={retry_preview}"
                ) from retry_e
            except APIError as retry_e:
                raise RuntimeError(f"上游模型接口请求失败: model={model}, detail={retry_e}") from retry_e
        else:
            body_preview = body.strip()[:1000] if body else "<empty body>"
            raise RuntimeError(
                f"上游模型接口返回错误: status={e.status_code}, model={model}, body={body_preview}"
            ) from e
    except APIError as e:
        raise RuntimeError(f"上游模型接口请求失败: model={model}, detail={e}") from e

    if completion.choices and completion.choices[0].message:
        content = completion.choices[0].message.content
        if isinstance(content, str):
            return content.strip()

    raise ValueError(f"API 返回格式异常: {completion}")


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
