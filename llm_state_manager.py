import json
import os
import time
from logger_setup import logger

STATE_FILE_PATH = "llm_api_state.json"
COOLDOWN_SECONDS = 30  # 每个Key的冷却时间

# Key名称前缀，程序会自动发现所有以此开头的环境变量
KEY_PREFIX = "GROQ_API_KEY_"

# User-Agent列表现在内置在代码中
USER_AGENTS = [
    # Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.3",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    # macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    # Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0",
    # Android
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.88 Mobile Safari/537.36",
    # iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]


def _get_key_env_vars():
    """从环境变量中自动发现所有匹配前缀的Key名称。"""
    # 调试信息：打印所有环境变量
    logger.info("--- 调试: 环境变量检查开始 ---")
    groq_vars = [var for var in os.environ if var.startswith(KEY_PREFIX)]
    logger.info(f"找到的所有GROQ前缀变量: {groq_vars}")

    # 检查每个变量的值是否存在
    for var in groq_vars:
        value = os.getenv(var)
        logger.info(f"变量 {var} 的值: {'有值' if value else '为空'}")

    found_keys = [
        var for var in os.environ if var.startswith(KEY_PREFIX) and os.getenv(var)
    ]

    if not found_keys:
        logger.warning(f"在环境变量中未找到任何以 '{KEY_PREFIX}' 开头的密钥。")
    else:
        logger.info(f"最终找到的有效密钥: {found_keys}")

    logger.info("--- 调试: 环境变量检查结束 ---")
    return sorted(found_keys)  # 排序以保证每次运行顺序一致


def _load_state():
    """加载状态文件，如果不存在则创建默认状态。"""
    key_env_vars = _get_key_env_vars()
    if not os.path.exists(STATE_FILE_PATH):
        logger.info(f"状态文件 {STATE_FILE_PATH} 不存在，创建默认状态。")
        return {
            "current_key_index": 0,
            "current_ua_index": 0,
            "keys_info": {
                key_env: {"last_used": 0, "is_valid": True}
                for key_env in key_env_vars
                if key_env
            },
        }
    try:
        with open(STATE_FILE_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        logger.warning(f"无法读取或解析状态文件 {STATE_FILE_PATH}，将使用默认状态。")
        # 如果文件损坏，也返回默认状态
        return {
            "current_key_index": 0,
            "current_ua_index": 0,
            "keys_info": {
                key_env: {"last_used": 0, "is_valid": True}
                for key_env in key_env_vars
                if key_env
            },
        }


def _save_state(state):
    """保存状态到文件。"""
    try:
        with open(STATE_FILE_PATH, "w") as f:
            json.dump(state, f, indent=4)
    except IOError as e:
        logger.error(f"无法写入状态文件 {STATE_FILE_PATH}: {e}")


def get_next_available_credential():
    """
    获取下一个可用的、且满足冷却要求的API Key和User Agent。
    如果所有Key都在冷却中，将等待直到最近的一个可用。
    """
    state = _load_state()
    keys_info = state.get("keys_info", {})

    valid_keys = [k for k, v in keys_info.items() if v.get("is_valid", True)]
    if not valid_keys:
        logger.error("所有API Key均已被标记为无效。")
        return None, None, None

    start_index = state.get("current_key_index", 0) % len(valid_keys)

    # 轮询一圈寻找可用Key
    for i in range(len(valid_keys)):
        current_index = (start_index + i) % len(valid_keys)
        key_env = valid_keys[current_index]
        info = keys_info[key_env]

        now = time.time()
        if now - info.get("last_used", 0) > COOLDOWN_SECONDS:
            logger.info(
                f"找到可用Key: {key_env} (距离上次使用 {now - info.get('last_used', 0):.1f}秒)。"
            )
            # 更新状态
            state["current_key_index"] = (current_index + 1) % len(valid_keys)
            state["current_ua_index"] = (state.get("current_ua_index", 0) + 1) % len(
                USER_AGENTS
            )
            info["last_used"] = now
            _save_state(state)

            api_key_value = os.getenv(key_env)
            user_agent = USER_AGENTS[state["current_ua_index"]]
            return key_env, api_key_value, user_agent

    # 如果所有Key都在冷却中
    logger.warning("所有Key目前都在冷却中，将等待最近的一个可用...")

    # 计算需要等待的时间
    wait_times = []
    for key_env in valid_keys:
        info = keys_info[key_env]
        wait_time = COOLDOWN_SECONDS - (time.time() - info.get("last_used", 0))
        wait_times.append(wait_time)

    min_wait_time = max(0, min(wait_times))
    logger.info(f"需要等待 {min_wait_time:.2f} 秒...")
    time.sleep(min_wait_time + 0.1)  # 等待并增加一点缓冲

    # 再次调用自己，这次必定会有一个可用
    return get_next_available_credential()


def report_invalid_key(key_env_to_invalidate: str):
    """
    报告一个Key已失效，并将其在状态文件中标记为 in_valid。
    """
    if not key_env_to_invalidate:
        return

    state = _load_state()
    keys_info = state.get("keys_info", {})

    if key_env_to_invalidate in keys_info:
        if keys_info[key_env_to_invalidate].get("is_valid", True):
            logger.warning(f"将Key '{key_env_to_invalidate}' 标记为无效。")
            keys_info[key_env_to_invalidate]["is_valid"] = False
            _save_state(state)
        else:
            logger.info(f"Key '{key_env_to_invalidate}' 之前已被标记为无效。")
    else:
        logger.warning(f"尝试标记一个未在状态文件中追踪的Key: {key_env_to_invalidate}")


def get_valid_key_count():
    """返回当前状态下有效Key的数量。"""
    state = _load_state()
    keys_info = state.get("keys_info", {})
    valid_key_count = sum(
        1 for info in keys_info.values() if info.get("is_valid", True)
    )
    return valid_key_count


if __name__ == "__main__":
    # 测试用例
    print("--- 测试获取凭证 ---")

    # 模拟环境变量
    os.environ["GROQ_API_KEY_KEY_A"] = "key_value_a"
    os.environ["GROQ_API_KEY_KEY_B"] = "key_value_b"
    os.environ["GROQ_API_KEY_KEY_C"] = "key_value_c"

    # 重置状态文件
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)

    for i in range(5):
        print(f"\n--- 第 {i+1} 次请求 ---")
        key_name, key_val, ua = get_next_available_credential()
        print(f"获取到: Key Name={key_name}, Key Value={key_val}, User-Agent={ua}")
        if i == 2:
            print("\n>>> 模拟Key B失效...")
            report_invalid_key("GROQ_API_KEY_KEY_B")
            print(">>> Key B已被标记为无效。")

    print("\n--- 测试冷却 ---")
    print("由于所有Key在30秒内都用过，再次请求应会触发等待...")
    key_name, key_val, ua = get_next_available_credential()
    print(f"等待后获取到: Key Name={key_name}, Key Value={key_val}, User-Agent={ua}")
