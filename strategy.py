import pandas as pd
import pandas_ta as ta
from config_loader import config
from logger_setup import logger


def calculate_indicators(klines, timeframe="1d"):
    """
    根据K线数据计算技术指标 (SMA, RSI, EMA, KDJ)
    :param klines: K线数据列表
    :param timeframe: 时间周期，如 '15m', '4h', '1d'
    :return: 包含最新指标的字典
    """
    # 根据不同时间周期设置不同的SMA周期
    if timeframe == "15m":
        sma_period = 20  # 15分钟数据用20周期SMA
        rsi_period = 14  # 标准RSI
    elif timeframe == "4h":
        sma_period = 20  # 4小时数据用20周期SMA
        rsi_period = 14  # 标准RSI
    else:  # 1d
        sma_period = 20  # 日线数据用20周期SMA
        rsi_period = 14  # 标准RSI

    if not klines or len(klines) < sma_period:
        logger.warning(
            f"{timeframe} 周期K线数据不足 (需要{sma_period}条, 实际{len(klines)}条)，无法计算技术指标。"
        )
        return None

    # 将 K 线数据转换为 pandas DataFrame
    df = pd.DataFrame(
        klines,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
            "ignore",
        ],
    )

    # 将价格和成交量列转换为数值类型
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])

    # --- 计算指标 ---
    # 计算简单移动平均线 (SMA)
    df.ta.sma(length=sma_period, append=True)

    # 计算相对强弱指数 (RSI)
    df.ta.rsi(length=rsi_period, append=True)

    # 计算KDJ指标
    df.ta.kdj(append=True)

    # 获取最新的指标值
    latest_indicators = {
        "sma": df[f"SMA_{sma_period}"].iloc[-1],
        "rsi": df[f"RSI_{rsi_period}"].iloc[-1],
        "k": df["K_9_3"].iloc[-1],
        "d": df["D_9_3"].iloc[-1],
        "j": df["J_9_3"].iloc[-1],
        "price": df["close"].iloc[-1],
    }

    # 为所有时间周期计算EMA指标
    # 计算EMA指标
    df.ta.ema(length=12, append=True)
    df.ta.ema(length=26, append=True)

    # 添加EMA指标
    latest_indicators["ema12"] = df["EMA_12"].iloc[-1]
    latest_indicators["ema26"] = df["EMA_26"].iloc[-1]

    # 检测均线金叉/死叉
    if len(df) >= 3:  # 确保有足够的数据点
        # 今天的EMA12和EMA26
        today_ema12 = df["EMA_12"].iloc[-1]
        today_ema26 = df["EMA_26"].iloc[-1]

        # 昨天的EMA12和EMA26
        yesterday_ema12 = df["EMA_12"].iloc[-2]
        yesterday_ema26 = df["EMA_26"].iloc[-2]

        # 检测金叉（EMA12从下方穿过EMA26）
        golden_cross = yesterday_ema12 < yesterday_ema26 and today_ema12 > today_ema26

        # 检测死叉（EMA12从上方穿过EMA26）
        death_cross = yesterday_ema12 > yesterday_ema26 and today_ema12 < today_ema26

        latest_indicators["golden_cross"] = golden_cross
        latest_indicators["death_cross"] = death_cross

    # 检测KDJ金叉/死叉
    if len(df) >= 3:
        # 当前K, D值
        today_k = df["K_9_3"].iloc[-1]
        today_d = df["D_9_3"].iloc[-1]
        # 前一天的K, D值
        yesterday_k = df["K_9_3"].iloc[-2]
        yesterday_d = df["D_9_3"].iloc[-2]

        # 金叉：K线从下向上穿过D线
        kdj_golden_cross = yesterday_k < yesterday_d and today_k > today_d
        # 死叉：K线从上向下穿过D线
        kdj_death_cross = yesterday_k > yesterday_d and today_k < today_d

        latest_indicators["kdj_golden_cross"] = kdj_golden_cross
        latest_indicators["kdj_death_cross"] = kdj_death_cross

    # 为了区分不同时间周期，在键名中加入时间周期标识
    result = {}
    for key, value in latest_indicators.items():
        result[f"{key}_{timeframe}"] = value

    logger.info(
        f"{timeframe} 周期技术指标计算完成: SMA_{sma_period}={latest_indicators['sma']:.2f}, RSI_{rsi_period}={latest_indicators['rsi']:.2f}"
    )
    return result


def calculate_multi_timeframe_indicators(multi_timeframe_klines):
    """
    计算多个时间周期的技术指标
    :param multi_timeframe_klines: 包含多个时间周期K线数据的字典
    :return: 包含所有时间周期指标的合并字典
    """
    all_indicators = {}

    for timeframe, klines in multi_timeframe_klines.items():
        indicators = calculate_indicators(klines, timeframe)
        if indicators:
            all_indicators.update(indicators)

    return all_indicators


def make_decision(price_data, indicators, fear_greed_index, order_book_data=None):
    """
    根据所有输入数据和配置的阈值，通过评分系统做出最终决策。
    :param price_data: 价格数据
    :param indicators: 技术指标数据
    :param fear_greed_index: 恐惧贪婪指数
    :param order_book_data: 订单薄数据
    :return: 包含决策、总分和归因明细的字典.
    """
    if not all([price_data, indicators, fear_greed_index]):
        logger.error("数据不完整，无法做出决策。")
        return {"decision": "数据不足", "score": 0, "breakdown": []}

    thresholds = config["thresholds"]
    current_price = price_data["price"]
    score = 0
    score_breakdown = []  # 决策归因明细

    logger.info("开始基于多时间周期评分系统进行决策...")
    logger.info(f"当前价格: {current_price:.2f}, F&G指数: {fear_greed_index['value']}")

    # 检查是否有所有需要的时间周期数据
    required_indicators = [
        "price_1d",
        "sma_1d",
        "rsi_1d",
        "price_4h",
        "sma_4h",
        "rsi_4h",
        "price_15m",
        "sma_15m",
        "rsi_15m",
    ]

    missing_indicators = [ind for ind in required_indicators if ind not in indicators]
    if missing_indicators:
        logger.warning(
            f"缺少以下指标: {missing_indicators}. 将使用可用的指标进行决策。"
        )

    # --- 评分逻辑 (多时间周期) ---

    # 1. 恐惧贪婪指数评分
    fng_value = fear_greed_index["value"]
    if fng_value <= thresholds["fear_index"]["buy_large"]:
        score += 4  # 极度恐惧，强烈买入信号
        reason = f"F&G指数 ({fng_value}) <= {thresholds['fear_index']['buy_large']}"
        score_breakdown.append({"name": f"F&G指数({fng_value})", "score": 4})
        logger.info(f"[得分] {reason}，分数 +4")
    elif fng_value >= thresholds["greed_index"]["sell_large"]:
        score -= 4  # 极度贪婪，强烈卖出信号
        reason = f"F&G 指数 ({fng_value}) >= {thresholds['greed_index']['sell_large']}"
        score_breakdown.append({"name": f"F&G指数({fng_value})", "score": -4})
        logger.info(f"[得分] {reason}，分数 -4")

    # 2. 15分钟周期评分
    if (
        "rsi_15m" in indicators
        and "price_15m" in indicators
        and "sma_15m" in indicators
    ):
        rsi_15m = indicators["rsi_15m"]
        price_15m = indicators["price_15m"]
        sma_15m = indicators["sma_15m"]

        # RSI评分
        if rsi_15m < 25:
            score += 2
            score_breakdown.append({"name": f"15分钟RSI({rsi_15m:.2f})", "score": 2})
            logger.info(f"[得分] 15分钟 RSI ({rsi_15m:.2f}) < 25，分数 +2")
        elif rsi_15m > 75:
            score -= 2
            score_breakdown.append({"name": f"15分钟RSI({rsi_15m:.2f})", "score": -2})
            logger.info(f"[得分] 15分钟 RSI ({rsi_15m:.2f}) > 75，分数 -2")

        # 价格与SMA关系
        price_to_sma_ratio = price_15m / sma_15m
        if price_to_sma_ratio < 0.98:
            score += 1
            score_breakdown.append(
                {"name": f"15分钟价格/SMA比率({price_to_sma_ratio:.2f})", "score": 1}
            )
            logger.info(
                f"[得分] 15分钟价格/SMA比率 ({price_to_sma_ratio:.2f}) < 0.98，分数 +1"
            )
        elif price_to_sma_ratio > 1.02:
            score -= 1
            score_breakdown.append(
                {"name": f"15分钟价格/SMA比率({price_to_sma_ratio:.2f})", "score": -1}
            )
            logger.info(
                f"[得分] 15分钟价格/SMA比率 ({price_to_sma_ratio:.2f}) > 1.02，分数 -1"
            )

        # 15分钟EMA交叉评分
        if indicators.get("golden_cross_15m", False):
            score += 1
            score_breakdown.append({"name": "15分钟EMA金叉", "score": 1})
            logger.info(f"[得分] 15分钟 EMA12/26 金叉，分数 +1")
        elif indicators.get("death_cross_15m", False):
            score -= 1
            score_breakdown.append({"name": "15分钟EMA死叉", "score": -1})
            logger.info(f"[得分] 15分钟 EMA12/26 死叉，分数 -1")
        else:
            score_breakdown.append({"name": "15分钟EMA交叉", "score": 0})

        # 15分钟KDJ交叉评分
        if indicators.get("kdj_golden_cross_15m", False):
            score += 1
            score_breakdown.append({"name": "15分钟KDJ金叉", "score": 1})
            logger.info(f"[得分] 15分钟 KDJ 金叉，分数 +1")
        elif indicators.get("kdj_death_cross_15m", False):
            score -= 1
            score_breakdown.append({"name": "15分钟KDJ死叉", "score": -1})
            logger.info(f"[得分] 15分钟 KDJ 死叉，分数 -1")
        else:
            score_breakdown.append({"name": "15分钟KDJ交叉", "score": 0})

    # 3. 4小时周期评分
    if "rsi_4h" in indicators and "price_4h" in indicators and "sma_4h" in indicators:
        rsi_4h = indicators["rsi_4h"]
        price_4h = indicators["price_4h"]
        sma_4h = indicators["sma_4h"]

        # RSI评分
        if rsi_4h < 30:
            score += 3
            score_breakdown.append({"name": f"4小时RSI({rsi_4h:.2f})", "score": 3})
            logger.info(f"[得分] 4小时 RSI ({rsi_4h:.2f}) < 30，分数 +3")
        elif rsi_4h > 70:
            score -= 3
            score_breakdown.append({"name": f"4小时RSI({rsi_4h:.2f})", "score": -3})
            logger.info(f"[得分] 4小时 RSI ({rsi_4h:.2f}) > 70，分数 -3")

        # 价格与SMA关系
        price_to_sma_ratio = price_4h / sma_4h
        if price_to_sma_ratio < 0.95:
            score += 2
            score_breakdown.append(
                {"name": f"4小时价格/SMA比率({price_to_sma_ratio:.2f})", "score": 2}
            )
            logger.info(
                f"[得分] 4小时价格/SMA比率 ({price_to_sma_ratio:.2f}) < 0.95，分数 +2"
            )
        elif price_to_sma_ratio > 1.05:
            score -= 2
            score_breakdown.append(
                {"name": f"4小时价格/SMA比率({price_to_sma_ratio:.2f})", "score": -2}
            )
            logger.info(
                f"[得分] 4小时价格/SMA比率 ({price_to_sma_ratio:.2f}) > 1.05，分数 -2"
            )

        # 4小时EMA交叉评分
        if indicators.get("golden_cross_4h", False):
            score += 2
            score_breakdown.append({"name": "4小时EMA金叉", "score": 2})
            logger.info(f"[得分] 4小时 EMA12/26 金叉，分数 +2")
        elif indicators.get("death_cross_4h", False):
            score -= 2
            score_breakdown.append({"name": "4小时EMA死叉", "score": -2})
            logger.info(f"[得分] 4小时 EMA12/26 死叉，分数 -2")
        else:
            score_breakdown.append({"name": "4小时EMA交叉", "score": 0})

        # 4小时KDJ交叉评分
        if indicators.get("kdj_golden_cross_4h", False):
            score += 2
            score_breakdown.append({"name": "4小时KDJ金叉", "score": 2})
            logger.info(f"[得分] 4小时 KDJ 金叉，分数 +2")
        elif indicators.get("kdj_death_cross_4h", False):
            score -= 2
            score_breakdown.append({"name": "4小时KDJ死叉", "score": -2})
            logger.info(f"[得分] 4小时 KDJ 死叉，分数 -2")
        else:
            score_breakdown.append({"name": "4小时KDJ交叉", "score": 0})

    # 4. 日线周期评分
    if "rsi_1d" in indicators and "price_1d" in indicators and "sma_1d" in indicators:
        rsi_1d = indicators["rsi_1d"]
        price_1d = indicators["price_1d"]
        sma_1d = indicators["sma_1d"]

        # RSI评分
        if rsi_1d < 30:
            score += 3
            score_breakdown.append({"name": f"日线RSI({rsi_1d:.2f})", "score": 3})
            logger.info(f"[得分] 日线 RSI ({rsi_1d:.2f}) < 30，分数 +3")
        elif rsi_1d >= 75:
            score -= 4
            score_breakdown.append({"name": f"日线RSI({rsi_1d:.2f})", "score": -4})
            logger.info(f"[得分] 日线 RSI ({rsi_1d:.2f}) >= 75，分数 -4")
        elif rsi_1d > 70:
            score -= 3
            score_breakdown.append({"name": f"日线RSI({rsi_1d:.2f})", "score": -3})
            logger.info(f"[得分] 日线 RSI ({rsi_1d:.2f}) > 70，分数 -3")

        # 价格与SMA关系
        price_to_sma_ratio = price_1d / sma_1d
        if price_to_sma_ratio < 0.9:
            score += 3
            score_breakdown.append(
                {"name": f"日线价格/SMA比率({price_to_sma_ratio:.2f})", "score": 3}
            )
            logger.info(
                f"[得分] 日线价格/SMA比率 ({price_to_sma_ratio:.2f}) < 0.9，分数 +3"
            )
        elif price_to_sma_ratio > 1.1:
            score -= 3
            score_breakdown.append(
                {"name": f"日线价格/SMA比率({price_to_sma_ratio:.2f})", "score": -3}
            )
            logger.info(
                f"[得分] 日线价格/SMA比率 ({price_to_sma_ratio:.2f}) > 1.1，分数 -3"
            )

        # 5. 均线排列和交叉（日线）
        if all(key in indicators for key in ["ema12_1d", "ema26_1d"]):
            ema12 = indicators["ema12_1d"]
            ema26 = indicators["ema26_1d"]

            # 均线多头排列
            if ema12 > ema26:
                score += 2
                score_breakdown.append({"name": "日线EMA多头排列", "score": 2})
                logger.info(f"[得分] 均线多头排列 (EMA12 > EMA26)，分数 +2")
            # 均线空头排列
            elif ema12 < ema26:
                score -= 2
                score_breakdown.append({"name": "日线EMA空头排列", "score": -2})
                logger.info(f"[得分] 均线空头排列 (EMA12 < EMA26)，分数 -2")

            # 金叉/死叉
            if indicators.get("golden_cross_1d", False):
                score += 3
                score_breakdown.append({"name": "日线EMA金叉", "score": 3})
                logger.info(f"[得分] EMA12/26 金叉，分数 +3")
            elif indicators.get("death_cross_1d", False):
                score -= 3
                score_breakdown.append({"name": "日线EMA死叉", "score": -3})
                logger.info(f"[得分] EMA12/26 死叉，分数 -3")
            else:
                score_breakdown.append({"name": "日线EMA交叉", "score": 0})

        # 日线KDJ交叉评分
        if indicators.get("kdj_golden_cross_1d", False):
            score += 3
            score_breakdown.append({"name": "日线KDJ金叉", "score": 3})
            logger.info(f"[得分] 日线 KDJ 金叉，分数 +3")
        elif indicators.get("kdj_death_cross_1d", False):
            score -= 3
            score_breakdown.append({"name": "日线KDJ死叉", "score": -3})
            logger.info(f"[得分] 日线 KDJ 死叉，分数 -3")
        else:
            score_breakdown.append({"name": "日线KDJ交叉", "score": 0})

    # 6. 订单薄数据评分
    if order_book_data and order_book_data.get("data_available", False):
        # 买卖比例评分
        bid_ask_ratio = order_book_data.get("bid_ask_ratio", 1.0)
        if bid_ask_ratio > 1.5:  # 买单明显多于卖单
            score += 2
            score_breakdown.append({"name": f"买卖比({bid_ask_ratio:.2f})", "score": 2})
            logger.info(f"[得分] 订单薄买卖比 ({bid_ask_ratio:.2f}) > 1.5，分数 +2")
        elif bid_ask_ratio < 0.7:  # 卖单明显多于买单
            score -= 2
            score_breakdown.append(
                {"name": f"买卖比({bid_ask_ratio:.2f})", "score": -2}
            )
            logger.info(f"[得分] 订单薄买卖比 ({bid_ask_ratio:.2f}) < 0.7，分数 -2")

        # 价差评分
        spread = order_book_data.get("spread", 0.1)
        if spread > 0.2:  # 价差较大，市场流动性不足
            score -= 1
            score_breakdown.append({"name": f"价差({spread:.2f}%)", "score": -1})
            logger.info(f"[得分] 订单薄价差 ({spread:.2f}%) > 0.2%，分数 -1")

    # --- 根据总分转换最终决策 ---
    logger.info(f"最终总分: {score}")

    if score >= 8:
        decision = "🚀 超级买入"
    elif score >= 4:
        decision = "🟢 大量买入"
    elif score > 0:
        decision = "🟩 少量买入"
    elif score == 0:
        decision = "⏸️ 观望"
    elif score > -4:
        decision = "🟥 少量卖出"
    elif score > -8:
        decision = "🔴 大量卖出"
    else:  # score <= -8
        decision = "💣 超级卖出"

    logger.info(f"最终决策: {decision}")
    return {"decision": decision, "score": score, "breakdown": score_breakdown}


if __name__ == "__main__":
    # --- 测试 ---
    from data_provider import (
        get_klines,
        get_multi_timeframe_data,
        get_btc_price_and_change,
        get_fear_and_greed_index,
        get_order_book_data,
    )

    print("\n--- 测试多时间周期指标计算 ---")
    # 1. 获取多时间周期K线数据
    mtf_data = get_multi_timeframe_data(
        timeframes=["15m", "4h", "1d"], limits=[96, 60, 30]
    )

    if mtf_data:
        # 2. 计算多时间周期指标
        all_indicators = calculate_multi_timeframe_indicators(mtf_data)
        if all_indicators:
            print(f"计算出的多时间周期指标: {all_indicators}")

            # 3. 获取实时数据
            price_data = get_btc_price_and_change()
            fng_data = get_fear_and_greed_index()
            order_book_data = get_order_book_data()

            # 4. 模拟数据进行决策
            if price_data and fng_data:
                decision_data = make_decision(
                    price_data, all_indicators, fng_data, order_book_data
                )
                print(f"\n最终决策: {decision_data['decision']}")
                print(f"总分: {decision_data['score']}")
                print(f"归因: {decision_data['breakdown']}")
            else:
                print("\n无法进行决策，因为部分数据获取失败。")
        else:
            print("\n无法计算多时间周期指标。")
    else:
        print("\n无法获取多时间周期K线数据。")
