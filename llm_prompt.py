from config_loader import config


def build_llm_prompt_zh(price_data, fng_index, period_signals):
    """
    构建用于调用中文LLM的Prompt (Groq Llama3 版本)。
    """
    # 提取数据
    price = price_data.get("price", 0)
    change24h = price_data.get("change_24h", 0.0)
    fg_index = (
        f"{fng_index.get('value', 'N/A')} ({fng_index.get('classification', 'N/A')})"
    )
    signals = {
        "15m": period_signals.get("15m", "信号不足"),
        "4h": period_signals.get("4h", "信号不足"),
        "1d": period_signals.get("1d", "信号不足"),
    }

    # System Prompt
    system_prompt = {
        "role": "system",
        "content": (
            "你是一位专业的比特币市场策略分析师，精通技术指标分析和市场情绪评估。"
            "请根据用户提供的价格、情绪指标和各时间周期技术信号，给出一个综合的操作建议（买入/卖出/观望）及简要理由。"
        ),
    }

    # User Prompt
    user_prompt = {
        "role": "user",
        "content": (
            f"当前 BTC 价格：${price:,.2f}，24小时涨跌：{change24h:+.2f}%\n"
            f"今日 F&G 指数：{fg_index}\n"
            "\n"
            f"技术周期信号：\n"
            f"- 15分钟：{signals['15m']}\n"
            f"- 4小时：{signals['4h']}\n"
            f"- 日线：{signals['1d']}\n"
            "\n"
            "请结合上述技术信号和价格信息，给出一个最终投资建议（买入/卖出/观望），并说明原因。\n"
            "请严格按照以下格式回答：\n"
            "决策：<买入/卖出/观望>\n"
            "理由：<一句话理由>"
        ),
    }

    return [system_prompt, user_prompt]


if __name__ == "__main__":
    # 示例用法
    mock_price = {"price": 68500.5, "change_24h": 1.25}
    mock_fng = {"value": 74, "classification": "Greed"}
    mock_signals = {"15m": "观望", "4h": "卖出", "1d": "卖出"}

    prompt = build_llm_prompt_zh(mock_price, mock_fng, mock_signals)

    import json

    print(json.dumps(prompt, indent=2, ensure_ascii=False))


def build_llm_prompt_text(price_data, fng_index, period_signals):
    """
    构建用于 curl 调用的纯文本 Prompt。
    """
    price = price_data.get("price", 0)
    change24h = price_data.get("change_24h", 0.0)
    fg_index = (
        f"{fng_index.get('value', 'N/A')} ({fng_index.get('classification', 'N/A')})"
    )
    signals = {
        "15m": period_signals.get("15m", "信号不足"),
        "4h": period_signals.get("4h", "信号不足"),
        "1d": period_signals.get("1d", "信号不足"),
    }

    return (
        f"当前 BTC 价格为 ${price:,.2f} 美元，24h 涨跌为 {change24h:+.2f}%。\n"
        f"今日 F&G 指数为 {fg_index}。\n\n"
        "技术指标如下：\n"
        f"- 15分钟周期信号：{signals['15m']}\n"
        f"- 4小时周期信号：{signals['4h']}\n"
        f"- 日线周期信号：{signals['1d']}\n\n"
        "请你结合最新比特币相关新闻，并分析这些技术指标，判断市场走势，并给出：\n"
        "- 最终操作建议（买入/卖出/观望）\n"
        "- 简洁的理由（结合技术 + 新闻）\n"
        "请中文作答，格式如下：\n"
        "决策：<买入/卖出/观望>\n"
        "理由：<简洁说明>"
    )
