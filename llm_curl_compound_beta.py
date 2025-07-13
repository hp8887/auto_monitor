import subprocess
import json
import os
from logger_setup import logger
from config_loader import config


def ask_llm_by_curl(prompt: str) -> dict:
    """
    通过直接调用 curl 命令与 Groq API 对话。
    返回一个字典，格式为: {"success": bool, "decision": str}
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or "gsk_" not in api_key:
        logger.error("未在环境变量中找到有效的 GROQ_API_KEY。请设置该环境变量。")
        return {"success": False, "decision": "LLM调用失败 (GROQ_API_KEY 未配置)"}

    payload = {
        "model": "llama3-8b-8192",  # 切换到稳定且经济高效的模型
        # "model": "compound-beta",  # 按照您的要求指定此模型
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 250,
    }
    logger.info(f"正在使用 API Key: {api_key[:7]}...{api_key[-4:]}")

    curl_command = [
        "curl",
        "-s",  # 静默模式，不输出进度条
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
        logger.info("正在通过 curl 命令调用 Groq API...")
        result = subprocess.run(
            curl_command,
            capture_output=True,  # 捕获 stdout 和 stderr
            text=True,  # 以文本模式处理输出
            timeout=30,
            check=False,  # 我们手动检查返回码
        )

        if result.returncode != 0:
            logger.error(f"curl 命令执行失败，返回码: {result.returncode}")
            logger.error(f"错误输出 (stderr): {result.stderr}")
            logger.error(f"标准输出 (stdout): {result.stdout}")
            return {
                "success": False,
                "decision": f"LLM调用失败 (命令执行错误)，原始响应: {result.stdout or result.stderr}",
            }

        response_text = result.stdout
        response_json = json.loads(response_text)

        # 尝试提取内容
        content = (
            response_json.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not content:
            logger.error(f"无法从API响应中提取到 'content'。")
            logger.error(f"收到的原始JSON内容: {response_json}")
            return {
                "success": False,
                "decision": f"LLM调用异常 (未能提取content)，原始响应: {response_json}",
            }

        logger.info("成功从 Groq (via curl) 获取到 LLM 响应。")
        return {"success": True, "decision": content}

    except FileNotFoundError:
        logger.error("错误：系统中未找到 curl 命令。")
        return {"success": False, "decision": "LLM调用失败 (curl 命令不存在)"}
    except subprocess.TimeoutExpired:
        logger.error("通过 curl 调用 Groq API 超时。")
        return {"success": False, "decision": "LLM调用失败 (请求超时)"}
    except json.JSONDecodeError:
        logger.error(f"无法将API响应解析为JSON。")
        logger.error(f"收到的原始响应内容: {response_text}")
        return {
            "success": False,
            "decision": f"LLM调用失败 (JSON解析错误)，原始响应: {response_text}",
        }
    except Exception as e:
        logger.error(f"处理 curl 调用时发生未知异常: {e}", exc_info=True)
        # 捕获所有其他可能的异常
        return {"success": False, "decision": f"LLM调用失败 (未知异常: {e})"}
