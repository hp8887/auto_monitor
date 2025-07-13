import subprocess
import json
import os
from logger_setup import logger
from config_loader import config


def ask_llm_by_curl(prompt: str) -> str:
    """
    通过直接调用 curl 命令与 Groq API 对话。
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("未找到 GROQ_API_KEY 环境变量，尝试从 config.yaml 中获取...")
        api_key = config.get("api_keys", {}).get("groq")

    if not api_key or "gsk_" not in api_key:
        logger.error("Groq API Key 未配置或格式不正确。")
        return "错误：API Key未配置"

    payload = {
        "model": "compound-beta",  # 按照您的要求指定此模型
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 250,
    }

    curl_command = [
        "curl",
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=True,  # 如果返回码非0，则抛出异常
        )
        response_text = result.stdout.decode("utf-8")
        response_json = json.loads(response_text)
        content = response_json["choices"][0]["message"]["content"].strip()
        logger.info(f"成功从 Groq (via curl) 获取到 LLM 响应: {content}")
        return content

    except FileNotFoundError:
        logger.error("错误：系统中未找到 curl 命令。")
        return "错误：curl 命令不存在"
    except subprocess.TimeoutExpired:
        logger.error("通过 curl 调用 Groq API 超时。")
        return "错误：请求超时"
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.decode("utf-8")
        logger.error(f"curl 命令执行失败，返回码非零: {error_message}")
        return f"错误：LLM调用失败 ({error_message})"
    except Exception as e:
        logger.error(f"处理 curl 调用时发生未知错误: {e}", exc_info=True)
        return f"错误：未知错误 ({e})"
