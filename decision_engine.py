from config_loader import config
from logger_setup import logger


def make_weighted_score(
    flat_indicators, fear_greed_index, order_book_data, news_data=None
):
    """
    计算用于兜底决策的规则总分和得分细则。
    这个函数现在接收一个“扁平化”的指标字典，并可选地接收新闻数据。
    """
    total_score = 0
    breakdown = []

    weights = config.get("weights", {})
    timeframe_weights = config.get("timeframe_weights", {})
    periods_config = config.get("periods", {})

    # 0. 新闻情绪分数
    if news_data:
        # 计算平均情绪分
        sentiments = [
            item["sentiment_score"] for item in news_data if "sentiment_score" in item
        ]
        if sentiments:
            avg_sentiment = sum(sentiments) / len(sentiments)
            # 从配置获取权重，赋予一个相对较高的默认值以体现其影响力
            news_weight = weights.get("news_sentiment", 5)
            news_score = avg_sentiment * news_weight
            total_score += news_score
            breakdown.append(
                {"name": f"新闻平均情绪({avg_sentiment:.2f})", "score": news_score}
            )
        else:
            # 有新闻条目但无法提取情绪分
            breakdown.append({"name": "新闻情绪", "score": 0, "note": "无有效情绪分"})
    else:
        # 没有获取到任何新闻
        breakdown.append({"name": "新闻情绪", "score": 0, "note": "无相关新闻"})

    # 1. 恐惧贪婪指数 (仅影响日线权重)
    if fear_greed_index and fear_greed_index.get("value") is not None:
        fng_value = fear_greed_index["value"]
        classification = fear_greed_index["classification"]
        fng_score = 0
        if fng_value < config.get("thresholds", {}).get("fear_index", {}).get(
            "buy_large", 30
        ):
            fng_score = weights.get("fng_extreme", 2)
        elif fng_value < 45:  # A general "Fear" threshold
            fng_score = weights.get("fng_normal", 1)
        elif fng_value > config.get("thresholds", {}).get("greed_index", {}).get(
            "sell_large", 75
        ):
            fng_score = -weights.get("fng_extreme", 2)
        elif fng_value > 55:  # A general "Greed" threshold
            fng_score = -weights.get("fng_normal", 1)

        if fng_score != 0:
            final_score = fng_score * timeframe_weights.get("1d", 2.0)
            total_score += final_score
            breakdown.append(
                {"name": f"F&G指数({fng_value}-{classification})", "score": final_score}
            )

    # 2. 订单薄数据
    if order_book_data and order_book_data.get("data_available", False):
        ratio = order_book_data.get("bid_ask_ratio", 1.0)
        order_book_score = 0
        if ratio > 1.5:  # Buy pressure
            order_book_score = weights.get("order_book", 2)
        elif ratio < 0.7:  # Sell pressure
            order_book_score = -weights.get("order_book", 2)

        if order_book_score != 0:
            total_score += order_book_score
            breakdown.append(
                {"name": f"订单薄买卖比({ratio:.2f})", "score": order_book_score}
            )

    # 3. 多周期技术指标
    for tf in ["15m", "4h", "1d"]:
        tf_weight = timeframe_weights.get(tf, 1.0)
        tf_period_cfg = periods_config.get(tf, {})

        # EMA 交叉
        if flat_indicators.get(f"golden_cross_{tf}"):
            score = weights.get("ema_cross", 3) * tf_weight
            total_score += score
            breakdown.append({"name": f"{tf} EMA金叉", "score": score})
        if flat_indicators.get(f"death_cross_{tf}"):
            score = -weights.get("ema_cross", 3) * tf_weight
            total_score += score
            breakdown.append({"name": f"{tf} EMA死叉", "score": score})

        # RSI 极限
        rsi = flat_indicators.get(f"rsi_{tf}")
        if rsi is not None:
            rsi_buy_threshold = tf_period_cfg.get("rsi_buy", 30)
            rsi_sell_threshold = tf_period_cfg.get("rsi_sell", 70)
            if rsi < rsi_buy_threshold:
                score = weights.get("rsi_extreme", 4) * tf_weight
                total_score += score
                breakdown.append({"name": f"{tf} RSI超卖({rsi:.1f})", "score": score})
            elif rsi > rsi_sell_threshold:
                score = -weights.get("rsi_extreme", 4) * tf_weight
                total_score += score
                breakdown.append({"name": f"{tf} RSI超买({rsi:.1f})", "score": score})

        # KDJ 交叉
        if flat_indicators.get(f"kdj_golden_cross_{tf}"):
            score = weights.get("kdj_cross", 2) * tf_weight
            total_score += score
            breakdown.append({"name": f"{tf} KDJ金叉", "score": score})
        if flat_indicators.get(f"kdj_death_cross_{tf}"):
            score = -weights.get("kdj_cross", 2) * tf_weight
            total_score += score
            breakdown.append({"name": f"{tf} KDJ死叉", "score": score})

        # EMA 排列 (仅 4h, 1d)
        if tf in ["4h", "1d"]:
            if flat_indicators.get(f"ema_bullish_trend_{tf}"):
                score = weights.get("ema_trend", 1) * tf_weight
                total_score += score
                breakdown.append({"name": f"{tf} EMA多头排列", "score": score})
            if flat_indicators.get(f"ema_bearish_trend_{tf}"):
                score = -weights.get("ema_trend", 1) * tf_weight
                total_score += score
                breakdown.append({"name": f"{tf} EMA空头排列", "score": score})

    return total_score, breakdown


def interpret_score(score):
    """
    根据总分解释为五档决策。
    """
    thresholds = config.get("thresholds", {})
    strong_threshold = thresholds.get("strong", 10.0)
    normal_threshold = thresholds.get("normal", 5.0)

    if score >= strong_threshold:
        return "🟢🟢 强烈买入"
    elif score >= normal_threshold:
        return "🟢 买入"
    elif score <= -strong_threshold:
        return "🔴🔴 强烈卖出"
    elif score <= -normal_threshold:
        return "🔴 卖出"
    else:
        return "🟡 观望"
