import subprocess
import json
import os
import requests
from logger_setup import logger

# --- 配置 ---
MODEL_PRIORITY_LIST = ["compound-beta", "compound-beta-mini", "llama-3.1-8b-instant"]

# --- API Key 列表 ---
# 定义所有可用的API Key对应的环境变量名称
# 程序将按照这个列表的顺序去尝试每一个Key
KEY_ENV_VAR_LIST = [
    "GROQ_API_KEY_1",
    "GROQ_API_KEY_2",
    "GROQ_API_KEY_3",
]


def _call_groq_api(
    prompt: str, model_name: str, api_key: str, key_env_var: str
) -> dict:
    """
    内部函数，负责调用一次 Groq API。
    使用传入的 API Key。
    返回一个包含成功状态和结果/错误信息的字典。
    """
    logger.info(f"准备使用模型 '{model_name}' (通过 {key_env_var}) 调用 API...")
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 300,
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
                f"curl 命令执行失败 (模型: {model_name}, Key: {key_env_var})，返回码: {result.returncode}, 错误输出: {error_output}"
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
                f"API 返回错误 (模型: {model_name}, Key: {key_env_var}): {error_message}"
            )

            is_skippable = (
                "rate_limit_exceeded" in error_code
                or "invalid_api_key" in error_code
                or "Request Entity Too Large" in error_message
            )
            return {
                "success": False,
                "decision": error_message,
                "is_skippable_error": is_skippable,
            }

        content = (
            response_json.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not content:
            logger.error(
                f"无法从API响应中提取到 'content' (模型: {model_name}, Key: {key_env_var})。响应: {response_json}"
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
        }
    except json.JSONDecodeError:
        logger.error(
            f"无法解析API响应 (模型: {model_name}, Key: {key_env_var})。响应: {response_text}"
        )
        return {
            "success": False,
            "decision": f"JSON解析错误: {response_text}",
            "is_skippable_error": False,
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
        }


def ask_llm_by_curl(prompt: str) -> dict:
    """
    按模型优先级(外层循环)和Key优先级(内层循环)尝试调用，直到成功或全部失败。
    如果遇到可跳过的错误（如速率限制、Key无效），则自动切换到下一个Key或下一个模型。
    返回: {"success": bool, "decision": str, "model_used": str}
    """
    last_error = "没有可用的模型或API Key。"

    # 外层循环：按优先级遍历模型
    for model in MODEL_PRIORITY_LIST:
        logger.info(f"--- 正在锁定模型: {model} ---")

        # 内层循环：按顺序遍历所有可用的Key
        for key_env_var in KEY_ENV_VAR_LIST:
            api_key = os.getenv(key_env_var)

            # 如果环境变量未设置或无效，则直接跳过这个Key
            if not api_key or "gsk_" not in api_key:
                logger.debug(f"环境变量 '{key_env_var}' 未设置或无效，跳过此Key。")
                continue

            logger.info(f"使用 Key (来自 {key_env_var}) 尝试模型 {model}...")

            # 调用API，传入模型、prompt和本次循环的Key
            result = _call_groq_api(prompt, model, api_key, key_env_var)

            if result.get("success"):
                # 只要成功一次，就立即返回最终结果
                return {
                    "success": True,
                    "decision": result["decision"],
                    "model_used": model,
                }

            # 记录下本次的错误信息，以备后续展示
            last_error = result.get("decision", "未知错误")

            # 如果是不可跳过的严重错误，则终止所有循环，直接返回失败
            if not result.get("is_skippable_error"):
                logger.error(
                    f"模型 {model} 使用 Key {key_env_var} 遭遇不可恢复的错误，终止所有尝试。错误: {last_error}"
                )
                return {
                    "success": False,
                    "decision": last_error,
                    "model_used": model,
                }

            # 如果是可跳过的错误，内层循环会继续，尝试下一个Key
            logger.warning(
                f"模型 {model} 使用 Key {key_env_var} 调用失败 (可跳过)，将尝试下一个Key。原因: {last_error}"
            )

        # 当一个模型的所有Key都尝试失败后，会跳出内层循环
        logger.warning(
            f"模型 {model} 已尝试所有可用Key但均失败，将降级到下一个优先级的模型。"
        )

    # 当所有模型的所有Key都尝试失败后，会跳出外层循环
    logger.error(f"所有备选模型及所有可用Key均调用失败。最后一个错误是: {last_error}")
    return {
        "success": False,
        "decision": f"所有可用模型和Key均尝试失败。最后错误: {last_error}",
        "model_used": "无",
    }
