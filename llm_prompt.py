from config_loader import config
import datetime


def build_llm_prompt_text(
    price_data, fng_data, rule_breakdown, technical_indicators, news_data=None
):
    """
    构建最终版（V8）的、用于 curl 调用的纯文本 Prompt。
    V8 版本新增了对新闻数据的处理逻辑。
    """
    # 1. 准备宏观数据
    price = price_data.get("price", 0)
    change24h_pct = price_data.get("change_24h", 0) / 100
    fg_value = fng_data.get("value", "N/A")
    fg_class = fng_data.get("classification", "N/A")

    # 2. 准备量化规则信号
    positive_signals = (
        "\n".join(
            [
                f"  - {item['name']}: +{item['score']:.1f}"
                for item in rule_breakdown
                if item["score"] > 0
            ]
        )
        or "  无明显看涨信号"
    )

    negative_signals = (
        "\n".join(
            [
                f"  - {item['name']}: {item['score']:.1f}"
                for item in rule_breakdown
                if item["score"] < 0
            ]
        )
        or "  无明显看跌信号"
    )

    # 3. 准备结构化的技术指标文本
    indicators_text_parts = []
    for tf in ["1d", "4h", "15m"]:  # 从大周期到小周期排列
        tf_data = technical_indicators.get(tf, {})
        if not tf_data:
            continue

        # 提取指标值，提供默认值以防万一
        rsi = tf_data.get("rsi", "N/A")
        sma = tf_data.get("sma", "N/A")
        k = tf_data.get("k", "N/A")
        d = tf_data.get("d", "N/A")

        # 提取信号
        signals = tf_data.get("signals", {})
        ema_cross = (
            "金叉"
            if signals.get("golden_cross")
            else "死叉" if signals.get("death_cross") else "无"
        )
        kdj_cross = (
            "金叉"
            if signals.get("kdj_golden_cross")
            else "死叉" if signals.get("kdj_death_cross") else "无"
        )

        # 提取支撑/压力
        support = tf_data.get("support", ["N/A"])[0]
        resistance = tf_data.get("resistance", ["N/A"])[0]

        indicators_text_parts.append(
            f"""- **{tf} 周期**:
  - RSI: {rsi} | SMA: {sma}
  - KDJ: K={k}, D={d} | KDJ交叉: {kdj_cross}
  - EMA交叉: {ema_cross}
  - 支撑/压力: S1={support} | R1={resistance}"""
        )
    indicators_text = "\n\n".join(indicators_text_parts)

    # 4. 准备新闻或分析指令
    news_or_instruction_section = ""
    if news_data:
        news_items_text = []
        for item in news_data:
            title = item.get("title", "N/A")
            sentiment = item.get("sentiment_level", "neutral")
            sentiment_score = item.get("sentiment_score", 0.0)
            news_items_text.append(
                f"- {title} (情绪: {sentiment}, 分数: {sentiment_score:.2f})"
            )

        news_text = "\n".join(news_items_text)
        news_or_instruction_section = f"""📰 **最新新闻**
{news_text}"""
    else:
        today = datetime.date.today()
        one_week_ago = today - datetime.timedelta(days=7)
        date_range_str = (
            f"{one_week_ago.strftime('%Y年%m月%d日')}至{today.strftime('%Y年%m月%d日')}"
        )
        news_or_instruction_section = f"""🧠 **分析指令**
1.  分析 **{date_range_str}** 关键新闻，判断利多/空。
2.  分析各周期信号是否一致或存在背离。
3.  结合支撑/压力位，判断当前价格所处区间及潜在动能。
4.  综合以上信息，给出明确操作建议并说明潜在风险。"""

    # 5. 组装最终 Prompt
    prompt = f"""作为专业的BTC分析师，请结合以下数据、信号、关键位及最新新闻，分析趋势并给出操作建议（买入/卖出/观望）。

---

📊 **宏观市场**
- BTC 现价: ${price:,.2f}
- 24小时涨跌: {change24h_pct:+.2%}
- 恐慌贪婪指数: {fg_value} ({fg_class})

🧮 **量化规则信号**
- 看涨信号:
{positive_signals}
- 看跌信号:
{negative_signals}

📈 **技术指标**
{indicators_text}

---

{news_or_instruction_section}

✳️ **注意**: 信号和点位是决策的辅助参考，你需要基于所有信息进行独立的、有深度的判断。

---

📋 **请严格按照此格式输出**

决策：<强烈买入 / 买入 / 观望 / 卖出 / 强烈卖出>

理由：
**1. 技术分析**：<深入解读各周期指标（RSI状态、均线关系、KDJ/EMA交叉信号），并点出是否存在共振或背离>
**2. 市场情绪**：<评估当前F&G指数反映的贪婪或恐慌程度，及其对短期走势的潜在影响>
**3. 新闻驱动**：<（如果获取到新闻）提及关键新闻事件，并分析其如何影响市场预期>
**4. 支撑/压力位评估**：<分析当前价格与关键S1/R1位的相对关系，推演价格可能遇到的阻力或支撑强度>
**5. 综合判断与建议**：<总结上述所有分析，形成最终的核心观点，并给出明确的操作建议（如：在何种条件下买入/卖出）>
**潜在风险**：
- <风险点1的描述，例如：若价格跌破关键支撑位，则看涨判断可能失效>
- <风险点2的描述，例如：警惕某个即将发生的宏观事件可能带来的市场波动>
"""
    return prompt.strip()
