import os
import requests
import json
from logger_setup import logger
from config_loader import config


def ask_llm(messages, model="llama3-8b-8192", temperature=0.7, max_tokens=250):
    """
    调用 Groq API 与指定的 LLM 进行对话。
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("未找到 GROQ_API_KEY 环境变量，尝试从 config.yaml 中获取...")
        api_key = config.get("api_keys", {}).get("groq")

    if not api_key or "gsk_" not in api_key:
        logger.error("Groq API Key 未配置或格式不正确。")
        return "错误：API Key未配置"

    try:
        response = requests.post(
            url="https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=15,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        logger.info(f"成功从 Groq 获取到 LLM 响应: {content}")
        return content

    except requests.exceptions.Timeout:
        logger.error("请求 Groq API 超时。")
        return "错误：请求超时"
    except Exception as e:
        logger.error(f"调用 Groq API 失败: {e}", exc_info=True)
        return f"错误：{e}"


def extract_decision_and_reason(llm_response_text):
    """
    从LLM返回的原始文本中解析出"决策"和"理由"。
    """
    if "错误：" in llm_response_text:
        return "解析失败", llm_response_text

    try:
        lines = llm_response_text.strip().split("\n")
        decision = "解析失败"
        reason = "无法从文本中提取有效理由"

        for line in lines:
            if line.startswith("决策："):
                decision = line.replace("决策：", "").strip()
            elif line.startswith("理由："):
                reason = line.replace("理由：", "").strip()

        if decision == "解析失败":
            return "格式错误", "LLM未按指定格式返回"

        return decision, reason
    except Exception as e:
        logger.error(f"解析LLM响应文本失败: {e}", exc_info=True)
        return "解析失败", str(e)


if __name__ == "__main__":
    # --- 测试 extract_decision_and_reason ---
    print("--- 测试解析函数 ---")
    test_text_ok = "决策：买入\n理由：市场情绪转好，技术指标看涨。"
    decision, reason = extract_decision_and_reason(test_text_ok)
    print(f"决策: {decision}, 理由: {reason}")

    test_text_bad = "这是一个不规范的回答"
    decision, reason = extract_decision_and_reason(test_text_bad)
    print(f"决策: {decision}, 理由: {reason}")

    test_text_error = "错误：API Key未配置"
    decision, reason = extract_decision_and_reason(test_text_error)
    print(f"决策: {decision}, 理由: {reason}")

    # --- 测试 ask_llm (需要配置GROQ_API_KEY) ---
    print("\n--- 测试 API 调用 ---")
    if os.getenv("GROQ_API_KEY") or config.get("api_keys", {}).get("groq"):
        test_messages = [
            {"role": "system", "content": "你是一个乐于助人的助手。"},
            {"role": "user", "content": "你好，请问你是谁？"},
        ]
        response_text = ask_llm(test_messages)
        print(f"LLM 响应: {response_text}")
    else:
        print("请设置 GROQ_API_KEY 环境变量或在 config.yaml 中配置以进行真实API测试。")
