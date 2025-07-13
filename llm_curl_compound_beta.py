import subprocess
import json
import os
from logger_setup import logger

# --- 配置 ---
MODEL_PRIORITY_LIST = ["compound-beta", "compound-beta-mini", "llama-3.1-8b-instant"]


def _call_groq_api(prompt: str, model_name: str) -> dict:
    """
    内部函数，负责调用一次 Groq API。
    返回一个包含成功状态和结果/错误信息的字典。
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or "gsk_" not in api_key:
        # 这个错误是致命的，直接返回，不需要重试
        logger.error("未在环境变量中找到有效的 GROQ_API_KEY。")
        return {
            "success": False,
            "decision": "LLM 调用失败 (GROQ_API_KEY 未配置)",
            "is_rate_limit": False,
        }

    logger.info(f"准备使用模型 '{model_name}' 调用 API...")
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 300,  # 稍微增加 max_tokens
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
                f"curl 命令执行失败，返回码: {result.returncode}, 错误输出: {error_output}"
            )
            return {
                "success": False,
                "decision": f"命令执行错误 (返回码: {result.returncode})",
                "is_rate_limit": False,
            }

        response_text = result.stdout
        response_json = json.loads(response_text)

        # 检查是否有错误，特别是速率限制错误
        if "error" in response_json:
            error_details = response_json["error"]
            error_message = error_details.get("message", "未知错误")
            logger.warning(f"API 返回错误 (模型: {model_name}): {error_message}")
            is_rate_limit = "rate_limit_exceeded" in error_details.get("code", "")
            return {
                "success": False,
                "decision": error_message,
                "is_rate_limit": is_rate_limit,
            }

        content = (
            response_json.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not content:
            logger.error(
                f"无法从API响应中提取到 'content' (模型: {model_name})。响应: {response_json}"
            )
            return {
                "success": False,
                "decision": f"未能提取content: {response_json}",
                "is_rate_limit": False,
            }

        logger.info(f"模型 '{model_name}' 调用成功。")
        return {"success": True, "decision": content}

    except subprocess.TimeoutExpired:
        logger.warning(f"模型 '{model_name}' 调用超时。")
        return {"success": False, "decision": "请求超时", "is_rate_limit": False}
    except json.JSONDecodeError:
        logger.error(f"无法解析API响应 (模型: {model_name})。响应: {response_text}")
        return {
            "success": False,
            "decision": f"JSON解析错误: {response_text}",
            "is_rate_limit": False,
        }
    except Exception as e:
        logger.error(
            f"处理 curl 调用时发生未知异常 (模型: {model_name}): {e}", exc_info=True
        )
        return {"success": False, "decision": f"未知异常: {e}", "is_rate_limit": False}


def ask_llm_by_curl(prompt: str) -> dict:
    """
    按优先级尝试多个模型，直到成功或全部失败。
    如果遇到速率限制错误，则自动切换到下一个模型。
    返回: {"success": bool, "decision": str, "model_used": str}
    """
    for model in MODEL_PRIORITY_LIST:
        logger.info(f"--- 正在尝试模型: {model} ---")
        result = _call_groq_api(prompt, model)

        if result.get("success"):
            return {
                "success": True,
                "decision": result["decision"],
                "model_used": model,
            }

        # 如果不是速率限制错误，则直接失败，不尝试下一个模型
        if not result.get("is_rate_limit"):
            logger.error(
                f"模型 {model} 遭遇不可恢复的错误，终止尝试。错误: {result.get('decision')}"
            )
            return {
                "success": False,
                "decision": result.get("decision"),
                "model_used": model,  # 记录下是哪个模型失败了
            }

        logger.warning(
            f"模型 {model} 已达速率限制，将在下一个周期尝试更低优先级的模型。"
        )

    # 如果所有模型都因速率限制而失败
    logger.error("所有备选模型均已达到速率限制或调用失败。")
    return {
        "success": False,
        "decision": "所有可用模型均达到速率限制，请稍后重试或检查账户状态。",
        "model_used": "无",
    }
