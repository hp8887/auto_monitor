import subprocess
import json
import os
import requests
from logger_setup import logger
import random
from llm_state_manager import (
    get_next_available_credential,
    report_invalid_key,
    get_valid_key_count,
)

# --- 配置 ---
# 模型优先级列表保持不变
MODEL_PRIORITY_LIST = ["compound-beta", "compound-beta-mini", "llama-3.1-8b-instant"]

# KEY_ENV_VAR_LIST 和 USER_AGENT_POOL 已被移至 llm_state_manager

# --- 模拟人类开场白 (保持不变) ---
HUMAN_INTRO_POOL = [
    "Hi, can you help me with a quick Bitcoin outlook?",
    "What's your take on the current BTC market situation?",
    "Please provide a professional analysis of the Bitcoin market.",
    "Could you give me a summary of the current Bitcoin trend?",
]


def _call_groq_api(
    prompt: str, model_name: str, api_key: str, key_env_var: str, user_agent: str
) -> dict:
    """
    内部函数，负责调用一次 Groq API。
    使用传入的 API Key 和 User-Agent。
    返回一个包含成功状态和结果/错误信息的字典。
    """
    logger.info(f"准备使用模型 '{model_name}' (通过 {key_env_var}) 调用 API...")

    # 随机化参数
    temperature = 0.6 + random.random() * 0.3  # 0.6 to 0.9
    max_tokens = 280 + random.randint(0, 50)  # 280 to 330

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": round(temperature, 2),
        "max_tokens": max_tokens,
    }

    curl_command = [
        "curl",
        "-s",
        "--location",
        "https://api.groq.com/openai/v1/chat/completions",
        "--header",
        f"Authorization: Bearer {api_key}",
        "--header",
        "Content-Type: application/json",
        "--header",
        f"User-Agent: {user_agent}",
        "--data",
        json.dumps(payload),
    ]

    try:
        result = subprocess.run(
            curl_command, capture_output=True, text=True, timeout=45, check=False
        )

        if result.returncode != 0:
            error_output = result.stderr or result.stdout
            logger.error(
                f"curl 命令执行失败 (模型: {model_name}, Key: {key_env_var}, UA: {user_agent})，返回码: {result.returncode}, 错误输出: {error_output}"
            )
            return {
                "success": False,
                "decision": f"命令执行错误 (返回码: {result.returncode})",
                "is_skippable_error": False,  # curl本身执行失败，通常是严重问题
            }

        response_text = result.stdout
        response_json = json.loads(response_text)

        if "error" in response_json:
            error_details = response_json["error"]
            error_message = error_details.get("message", "未知错误")
            error_code = error_details.get("code", "")
            logger.warning(
                f"API 返回错误 (模型: {model_name}, Key: {key_env_var}, UA: {user_agent}): {error_message}"
            )

            # 增强可跳过错误的判断
            is_skippable = (
                "rate_limit_exceeded" in error_code
                or "invalid_api_key" in error_code
                or "insufficient_quota" in error_code
                or "Request Entity Too Large" in error_message
                or "context_length_exceeded" in error_code
            )
            # 增加一个字段，专门用于识别需要禁用Key的错误
            is_invalid_key = "invalid_api_key" in error_code

            return {
                "success": False,
                "decision": error_message,
                "is_skippable_error": is_skippable,
                "is_invalid_key": is_invalid_key,  # 返回是否为Key失效错误
            }

        content = (
            response_json.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not content:
            logger.error(
                f"无法从API响应中提取到 'content' (模型: {model_name}, Key: {key_env_var}, UA: {user_agent})。响应: {response_json}"
            )
            return {
                "success": False,
                "decision": f"未能提取content: {response_json}",
                "is_skippable_error": False,  # 响应结构不符，可能是API变更，判定为严重错误
            }

        logger.info(f"模型 '{model_name}' 使用 Key '{key_env_var}' 调用成功。")
        return {"success": True, "decision": content}

    except subprocess.TimeoutExpired:
        logger.warning(f"模型 '{model_name}' 使用 Key '{key_env_var}' 调用超时。")
        return {
            "success": False,
            "decision": "请求超时",
            "is_skippable_error": True,
            "is_invalid_key": False,
        }
    except json.JSONDecodeError:
        logger.error(
            f"无法解析API响应 (模型: {model_name}, Key: {key_env_var})。响应: {response_text}"
        )
        return {
            "success": False,
            "decision": f"JSON解析错误: {response_text}",
            "is_skippable_error": True,  # Cloudflare等拦截HTML页面时会触发
            "is_invalid_key": False,
        }
    except Exception as e:
        logger.error(
            f"处理 curl 调用时发生未知异常 (模型: {model_name}, Key: {key_env_var}): {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "decision": f"未知异常: {e}",
            "is_skippable_error": False,
            "is_invalid_key": False,
        }


def ask_llm_by_curl(prompt: str) -> dict:
    """
    使用新的状态管理器进行API调用。
    按模型优先级进行尝试，并在每个模型内部使用轮询和频率控制的Key。
    """
    last_error = "没有可用的模型或API Key。"

    # 人性化开场白逻辑保持不变
    final_prompt = prompt
    if random.random() < 0.25:
        intro = random.choice(HUMAN_INTRO_POOL)
        final_prompt = f"{intro}\n\nHere is the data for my main request:\n\n{prompt}"
        logger.info(f"添加人性化开场白: '{intro}'")

    # 外层循环：按优先级遍历模型
    for model in MODEL_PRIORITY_LIST:
        logger.info(f"--- 正在锁定模型: {model} ---")

        # 获取当前所有有效Key的数量，作为最大尝试次数
        # 注意：这里我们不能简单地用一个 for 循环，因为Key池是动态变化的
        # 我们需要在每次失败后，都从状态管理器获取“下一个”
        num_valid_keys = get_valid_key_count()

        if num_valid_keys == 0:
            logger.warning(f"模型 {model} 没有任何有效的Key可供尝试，跳过。")
            continue

        # 为每个模型进行最多 `num_valid_keys` 次尝试
        for attempt in range(num_valid_keys):
            logger.info(f"模型 {model} - 尝试次数 {attempt + 1}/{num_valid_keys}...")

            # 从状态管理器获取下一个可用凭证
            key_env_var, api_key, user_agent = get_next_available_credential()

            if not key_env_var:
                last_error = "所有API Key均已失效。"
                logger.error("状态管理器未能提供有效Key，终止尝试。")
                break  # 中断对此模型的所有尝试

            # 调用API
            result = _call_groq_api(
                final_prompt, model, api_key, key_env_var, user_agent
            )

            if result.get("success"):
                return {
                    "success": True,
                    "decision": result["decision"],
                    "model_used": model,
                }

            last_error = result.get("decision", "未知错误")

            # 如果是Key失效的特定错误，报告给状态管理器
            if result.get("is_invalid_key"):
                report_invalid_key(key_env_var)

            if not result.get("is_skippable_error"):
                logger.error(
                    f"遭遇不可恢复错误，终止所有尝试。模型: {model}, Key: {key_env_var}. 错误: {last_error}"
                )
                return {
                    "success": False,
                    "decision": last_error,
                    "model_used": model,
                }

            logger.warning(
                f"调用失败 (可跳过)，将尝试下一个可用Key。模型: {model}, Key: {key_env_var}. 原因: {last_error}"
            )

        logger.warning(f"模型 {model} 已尝试所有可用Key但均失败，将降级到下一个模型。")

    logger.error(f"所有模型均尝试失败。最后一个错误是: {last_error}")
    return {
        "success": False,
        "decision": f"所有可用模型和Key均尝试失败。最后错误: {last_error}",
        "model_used": "无",
    }
