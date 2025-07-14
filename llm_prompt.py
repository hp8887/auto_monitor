from config_loader import config


def build_llm_prompt_text(price_data, fng_index, breakdown, pivot_points_data):
    """
    构建最终版（V4）的、用于 curl 调用的纯文本 Prompt。
    整合了 Pivot Points 支撑/压力位，并强化了 AI 的主动性。
    """
    # 1. 准备宏观数据
    price = price_data.get("price", 0)
    change24h_pct = price_data.get("change_24h", 0.0) / 100  # 转换为百分比小数
    fg_value = fng_index.get("value", "N/A")
    fg_class = fng_index.get("classification", "N/A")

    # 2. 准备量化信号
    positive_signals = "\n".join(
        [
            f"  - {item['name']}：得分 +{item['score']:.1f}"
            for item in breakdown
            if item["score"] > 0
        ]
    )
    if not positive_signals:
        positive_signals = "  无明显看涨信号"

    negative_signals = "\n".join(
        [
            f"  - {item['name']}：得分 {item['score']:.1f}"
            for item in breakdown
            if item["score"] < 0
        ]
    )
    if not negative_signals:
        negative_signals = "  无明显看跌信号"

    # 3. 准备支撑与压力位数据
    def get_pivot_values(data, timeframe):
        tf_data = data.get(timeframe)
        if tf_data and isinstance(tf_data, dict):
            return {
                "s1": tf_data.get("support", {}).get("S1", "N/A"),
                "pivot": tf_data.get("pivot", "N/A"),
                "r1": tf_data.get("resistance", {}).get("R1", "N/A"),
            }
        return {"s1": "N/A", "pivot": "N/A", "r1": "N/A"}

    pivots_15m = get_pivot_values(pivot_points_data, "15m")
    pivots_4h = get_pivot_values(pivot_points_data, "4h")
    pivots_1d = get_pivot_values(pivot_points_data, "1d")

    # 4. 组装最终 Prompt (使用用户提供的最新模板)
    prompt = f"""
你是一位专业的比特币市场策略分析师，具备宏观经济、技术分析和新闻解读能力。请你结合以下市场数据、技术信号、支撑压力位和你可以访问的最新加密新闻，综合分析当前市场趋势，判断是否适合买入、卖出或观望。

---

📊 【宏观市场数据】
- 当前 BTC 价格：${price:,.2f}
- 24h 涨跌幅：{change24h_pct:+.2%}
- 市场情绪（F&G 指数）：{fg_value} ({fg_class})

🧮 【多周期量化信号评分】
- ✅ 看涨信号：
{positive_signals}
- ❌ 看跌信号：
{negative_signals}

📐 【支撑与压力位】（由系统自动生成，仅供参考）
请结合当前价格与以下关键点位的关系，自主分析市场动能。
- 15m：S1={pivots_15m['s1']}, Pivot={pivots_15m['pivot']}, R1={pivots_15m['r1']}
- 4h ：S1={pivots_4h['s1']},  Pivot={pivots_4h['pivot']},  R1={pivots_4h['r1']}
- 1d ：S1={pivots_1d['s1']},  Pivot={pivots_1d['pivot']},  R1={pivots_1d['r1']}

---

🧠 请你执行以下任务（请务必涵盖每一项）：

1. 主动回顾你可访问的**最新宏观或加密新闻**，判断是否对 BTC 价格构成利多或利空影响。
2. 分析 15m / 4h / 1d 三个周期的量化信号是否一致，是否存在短中期背离。
3. 结合支撑/压力位，判断当前价格是否面临关键阻力或存在支撑反弹机会。
4. 综合上述三类信息，给出操作建议，并指出潜在风险。

✳️ 注意：我们提供的信号与点位仅供参考，你必须发挥你的专业理解，独立做出判断。

---

📋 请严格按照以下格式输出：

决策：<强烈买入 / 买入 / 观望 / 卖出 / 强烈卖出>

理由：
1. 技术分析（基于各周期信号）
2. 市场情绪（F&G 指数评估）
3. 新闻驱动（提及1-2条关键事件并解释其影响）
4. 支撑/压力位评估（是否接近、突破或失守）
5. 综合判断与建议（明确风险点）
"""
    return prompt.strip()
