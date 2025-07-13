from config_loader import config


def build_llm_prompt_text(price_data, fng_index, breakdown):
    """
    构建最终版（V3）的、用于 curl 调用的纯文本 Prompt。
    采纳用户提供的强引导、结构化专业 Prompt 设计。
    """
    # 1. 准备宏观数据
    price = price_data.get("price", 0)
    change24h = price_data.get("change_24h", 0.0)
    fg_value = fng_index.get("value", "N/A")
    fg_class = fng_index.get("classification", "N/A")

    macro_data_text = (
        f"📊 【宏观市场数据】\n"
        f"- 当前 BTC 价格：${price:,.2f}\n"
        f"- 24h 涨跌幅：{change24h:+.2f}%\n"
        f"- 市场情绪（F&G 指数）：{fg_value}（{fg_class}）"
    )

    # 2. 准备量化信号
    bullish_signals = [
        f"- {item['name']}：+{item['score']:.1f}"
        for item in breakdown
        if item["score"] > 0
    ]
    bearish_signals = [
        f"- {item['name']}：{item['score']:.1f}"
        for item in breakdown
        if item["score"] < 0
    ]
    neutral_signals = [f"- {item['name']}" for item in breakdown if item["score"] == 0]

    quant_signals_text = "🧮 【量化规则模型初步评分】\n以下为基于多周期技术指标分析得到的信号评分结果，仅供你参考：\n"
    if bullish_signals:
        quant_signals_text += "\n✅ 看涨信号（Positive Signals）：\n" + "\n".join(
            bullish_signals
        )
    if bearish_signals:
        quant_signals_text += "\n❌ 看跌信号（Negative Signals）：\n" + "\n".join(
            bearish_signals
        )
    if neutral_signals:
        quant_signals_text += "\n😐 中性信号（Neutral Signals）：\n" + "\n".join(
            neutral_signals
        )
    if not bullish_signals and not bearish_signals and not neutral_signals:
        quant_signals_text += "\n无明显的多空信号。"

    # 3. 组装最终 Prompt
    return (
        f"你是一位专业的比特币市场策略分析师，具备宏观经济、技术分析和新闻解读能力。现在请你综合分析以下市场数据、技术信号以及你可以访问的最新新闻资讯，给出当前BTC市场的操作建议。\n\n"
        f"---\n\n"
        f"{macro_data_text}\n\n"
        f"{quant_signals_text}\n\n"
        f"---\n\n"
        f"请将我们提供的“宏观市场数据”和“量化规则模型评分”作为你分析的核心基石。你的所有判断都必须优先基于这些内部数据，然后再结合你获取的外部新闻进行深化。\n\n"
        f"🧠 请你执行以下任务（所有内容为强制要求）：\n\n"
        f"🔎 请主动回顾你可以访问的最新加密新闻或宏观事件（如美联储政策、通胀数据、大额资金异动等），并明确指出是否对当前市场产生实质影响。\n\n"
        f"📈 对比不同时间周期的技术信号（短期15m、中期4h、长期1d），分析它们是否一致，是否存在背离。\n\n"
        f"🧠 综合：量化信号、市场情绪、新闻驱动，进行多维度交叉验证后给出你的判断。\n\n"
        f"✳️ 请注意：你看到的是规则引擎的初步量化结果，你可以借助它，但请基于更高层次的理解做出独立判断。\n\n"
        f"---\n\n"
        f"📋 请严格按照以下格式输出你的分析结果：\n"
        f"决策：<强烈买入 / 买入 / 观望 / 卖出 / 强烈卖出>\n\n"
        f"理由：\n"
        f"1. 技术分析：\n"
        f"   - 必须严格依据我们提供的量化信号，对15m、4h、1d三个周期的信号进行解读，并说明它们之间是否存在冲突或一致性。\n"
        f"2. 市场情绪：\n"
        f"   - F&G 情绪及其含义。\n"
        f"3. 新闻事件影响：\n"
        f"   - 明确提及1~2条你识别的重要新闻，并说明对BTC的潜在影响。\n"
        f"4. 综合判断：\n"
        f"   - 你的最终建议，并指出可能的风险点。"
    )
