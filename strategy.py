import pandas as pd
import pandas_ta as ta
from config_loader import config
from logger_setup import logger


def calculate_indicators(klines, timeframe="1d"):
    """
    根据K线数据计算所有需要的技术指标。
    """
    cfg = config["periods"][timeframe]
    rsi_period = cfg["rsi_period"]
    sma_period = cfg["sma_period"]

    if not klines or len(klines) < max(rsi_period, sma_period):
        logger.warning(f"{timeframe} 周期K线数据不足，无法计算技术指标。")
        return None

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

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])

    # --- 计算所有需要的指标 ---
    df.ta.sma(length=sma_period, append=True)
    df.ta.rsi(length=rsi_period, append=True)
    df.ta.kdj(append=True)
    df.ta.ema(length=12, append=True)
    df.ta.ema(length=26, append=True)

    # --- 提取最新指标值 ---
    latest_indicators = {
        "price": df["close"].iloc[-1],
        "sma": df[f"SMA_{sma_period}"].iloc[-1],
        "rsi": df[f"RSI_{rsi_period}"].iloc[-1],
        "k": df["K_9_3"].iloc[-1],
        "d": df["D_9_3"].iloc[-1],
        "ema12": df["EMA_12"].iloc[-1],
        "ema26": df["EMA_26"].iloc[-1],
    }

    # --- 计算交叉信号 ---
    if len(df) >= 2:
        prev_row = df.iloc[-2]
        latest_row = df.iloc[-1]

        # EMA 交叉
        latest_indicators["golden_cross"] = (
            prev_row["EMA_12"] < prev_row["EMA_26"]
            and latest_row["EMA_12"] > latest_row["EMA_26"]
        )
        latest_indicators["death_cross"] = (
            prev_row["EMA_12"] > prev_row["EMA_26"]
            and latest_row["EMA_12"] < latest_row["EMA_26"]
        )

        # KDJ 交叉
        latest_indicators["kdj_golden_cross"] = (
            prev_row["K_9_3"] < prev_row["D_9_3"]
            and latest_row["K_9_3"] > latest_row["D_9_3"]
        )
        latest_indicators["kdj_death_cross"] = (
            prev_row["K_9_3"] > prev_row["D_9_3"]
            and latest_row["K_9_3"] < latest_row["D_9_3"]
        )

    # --- 计算 EMA 排列信号 (仅用于 4h, 1d) ---
    if timeframe in ["4h", "1d"]:
        price = latest_indicators["price"]
        ema12 = latest_indicators["ema12"]
        ema26 = latest_indicators["ema26"]
        latest_indicators["ema_bullish_trend"] = price > ema12 > ema26
        latest_indicators["ema_bearish_trend"] = price < ema12 < ema26

    # 为键名添加周期后缀以便区分
    return {f"{key}_{timeframe}": value for key, value in latest_indicators.items()}


def compute_signal_for_period(indicators, timeframe):
    """
    根据单个周期的指标，生成初步的"买入"、"卖出"、"观望"信号。
    这是一个简化的逻辑，主要用于给LLM一个初步的参考。
    """
    cfg = config["periods"][timeframe]

    rsi = indicators.get(f"rsi_{timeframe}")
    price = indicators.get(f"price_{timeframe}")
    sma = indicators.get(f"sma_{timeframe}")

    if rsi is None or price is None or sma is None:
        return "信号不足"

    # 主要基于RSI和SMA进行简单判断
    if rsi < cfg["rsi_buy"] and price < sma * cfg["sma_buy_mult"]:
        return "买入"
    elif rsi > cfg["rsi_sell"] and price > sma * cfg["sma_sell_mult"]:
        return "卖出"
    else:
        return "观望"


def make_weighted_score(all_indicators, fear_greed_index, order_book_data):
    """
    计算用于兜底决策的规则总分和得分细则。
    """
    total_score = 0
    breakdown = []

    weights = config["weights"]
    timeframe_weights = config["timeframe_weights"]

    # 1. 恐惧贪婪指数 (仅影响日线权重)
    if fear_greed_index and fear_greed_index["value"] is not None:
        fng_value = fear_greed_index["value"]
        classification = fear_greed_index["classification"]
        fng_score = 0
        if fng_value < 25:
            fng_score = weights["fng_extreme"]
        elif fng_value < 40:
            fng_score = weights["fng_normal"]
        elif fng_value > 75:
            fng_score = -weights["fng_extreme"]
        elif fng_value > 60:
            fng_score = -weights["fng_normal"]

        if fng_score != 0:
            final_score = fng_score * timeframe_weights["1d"]
            total_score += final_score
            breakdown.append(
                {"name": f"F&G指数({fng_value}-{classification})", "score": final_score}
            )

    # 2. 订单薄数据
    if order_book_data and order_book_data.get("data_available", False):
        ratio = order_book_data.get("bid_ask_ratio", 1.0)
        order_book_score = 0
        if ratio > 2.0:
            order_book_score = weights["order_book"]
        elif ratio < 0.5:
            order_book_score = -weights["order_book"]

        if order_book_score != 0:
            total_score += order_book_score
            breakdown.append(
                {"name": f"订单薄买卖比({ratio:.2f})", "score": order_book_score}
            )

    # 3. 多周期技术指标
    for tf in ["15m", "4h", "1d"]:
        tf_weight = timeframe_weights[tf]

        # EMA 交叉
        if all_indicators.get(f"golden_cross_{tf}"):
            score = weights["ema_cross"] * tf_weight
            total_score += score
            breakdown.append({"name": f"{tf} EMA金叉", "score": score})
        if all_indicators.get(f"death_cross_{tf}"):
            score = -weights["ema_cross"] * tf_weight
            total_score += score
            breakdown.append({"name": f"{tf} EMA死叉", "score": score})

        # RSI 极限
        rsi = all_indicators.get(f"rsi_{tf}")
        if rsi:
            rsi_cfg = config["periods"][tf]
            if rsi < rsi_cfg["rsi_buy"]:
                score = weights["rsi_extreme"] * tf_weight
                total_score += score
                breakdown.append({"name": f"{tf} RSI超卖({rsi:.1f})", "score": score})
            elif rsi > rsi_cfg["rsi_sell"]:
                score = -weights["rsi_extreme"] * tf_weight
                total_score += score
                breakdown.append({"name": f"{tf} RSI超买({rsi:.1f})", "score": score})

        # KDJ 交叉
        if all_indicators.get(f"kdj_golden_cross_{tf}"):
            score = weights["kdj_cross"] * tf_weight
            total_score += score
            breakdown.append({"name": f"{tf} KDJ金叉", "score": score})
        if all_indicators.get(f"kdj_death_cross_{tf}"):
            score = -weights["kdj_cross"] * tf_weight
            total_score += score
            breakdown.append({"name": f"{tf} KDJ死叉", "score": score})

        # EMA 排列 (仅 4h, 1d)
        if tf in ["4h", "1d"]:
            if all_indicators.get(f"ema_bullish_trend_{tf}"):
                score = weights["ema_trend"] * tf_weight
                total_score += score
                breakdown.append({"name": f"{tf} EMA多头排列", "score": score})
            if all_indicators.get(f"ema_bearish_trend_{tf}"):
                score = -weights["ema_trend"] * tf_weight
                total_score += score
                breakdown.append({"name": f"{tf} EMA空头排列", "score": score})

    return total_score, breakdown


def interpret_score(score):
    """
    根据总分解释为五档决策。
    """
    strong_threshold = config["thresholds"]["strong"]
    normal_threshold = config["thresholds"]["normal"]

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
            fng_data = get_fear_greed_index()
            order_book_data = get_order_book_data()

            # 4. 模拟数据进行决策
            if price_data and fng_data:
                # 使用新的决策函数
                total_score, breakdown = make_weighted_score(
                    all_indicators, fng_data, order_book_data
                )
                decision = interpret_score(total_score)
                print(f"\n最终决策: {decision}")
                print(f"总分: {total_score}")
                print(f"归因: {breakdown}")
            else:
                print("\n无法进行决策，因为部分数据获取失败。")
        else:
            print("\n无法计算多时间周期指标。")
    else:
        print("\n无法获取多时间周期K线数据。")
