from config_loader import config
import datetime


def build_llm_prompt_text(price_data, fng_index, breakdown, pivot_points_data):
    """
    构建最终版（V5）的、用于 curl 调用的纯文本 Prompt。
    V5版本对文本进行了精简，以避免超出模型的请求大小限制。
    """
    # 1. 准备宏观数据
    price = price_data.get("price", 0)
    change24h_pct = price_data.get("change_24h", 0.0) / 100  # 转换为百分比小数
    fg_value = fng_index.get("value", "N/A")
    fg_class = fng_index.get("classification", "N/A")

    # 2. 准备量化信号
    positive_signals = (
        "\n".join(
            [
                f"  - {item['name']}: +{item['score']:.1f}"
                for item in breakdown
                if item["score"] > 0
            ]
        )
        or "  无明显看涨信号"
    )

    negative_signals = (
        "\n".join(
            [
                f"  - {item['name']}: {item['score']:.1f}"
                for item in breakdown
                if item["score"] < 0
            ]
        )
        or "  无明显看跌信号"
    )

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

    # 4. 动态生成日期范围
    today = datetime.date.today()
    one_week_ago = today - datetime.timedelta(days=7)
    date_range_str = (
        f"{one_week_ago.strftime('%Y年%m月%d日')}至{today.strftime('%Y年%m月%d日')}"
    )

    # 5. 组装最终 Prompt (V6 增强版)
    prompt = f"""作为专业的比特币市场策略分析师，请结合以下数据、信号、关键位及最新新闻，分析BTC市场趋势并给出操作建议（买入/卖出/观望）。

---

📊 **宏观市场**
- BTC 价格: ${price:,.2f}
- 24h 涨跌: {change24h_pct:+.2%}
- 恐慌贪婪指数: {fg_value} ({fg_class})

🧮 **量化信号评分**
- 看涨信号:
{positive_signals}
- 看跌信号:
{negative_signals}

📐 **支撑与压力位**
请结合当前价格与这些关键位，自主分析市场动能。
- 15m: S1={pivots_15m['s1']}, P={pivots_15m['pivot']}, R1={pivots_15m['r1']}
- 4h:  S1={pivots_4h['s1']},  P={pivots_4h['pivot']},  R1={pivots_4h['r1']}
- 1d:  S1={pivots_1d['s1']},  P={pivots_1d['pivot']},  R1={pivots_1d['r1']}

---

🧠 **任务指令**
1.  分析**{date_range_str}期间的关键加密新闻**，判断其利多或利空影响。
2.  分析各周期信号是否一致或存在背离。
3.  结合支撑/压力位，判断当前价格所处区间及潜在动能。
4.  综合以上信息，给出明确操作建议并说明潜在风险。

✳️ **注意**: 我们提供的信号和点位是参考，你必须独立判断。

---

📋 **请严格按此格式输出**

决策：<强烈买入 / 买入 / 观望 / 卖出 / 强烈卖出>

理由：
1. 技术分析（解读周期信号）
2. 市场情绪（F&G指数评估）
3. 新闻驱动（提及关键事件及其影响）
4. 支撑/压力位评估（对各周期，分析价格与R1/S1的关系，并给出突破或回落后的情景推演）
5. 综合判断与建议（明确风险）
"""
    return prompt.strip()
