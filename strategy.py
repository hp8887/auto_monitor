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


def make_decision(indicators, fear_greed_index, order_book_data):
    """
    根据所有输入数据做出最终决策
    """
    total_score = 0
    breakdown = []

    # 定义周期权重，使决策更偏向长期趋势
    cycle_weights = {"1d": 2.0, "4h": 1.5, "15m": 1.0}

    # 1. 恐惧贪婪指数 (仅影响日线权重)
    # F&G 指数是日线级别情绪，其分数应被日线权重放大
    fng_score = 0
    if fear_greed_index and fear_greed_index["value"] is not None:
        fng_value = fear_greed_index["value"]
        classification = fear_greed_index["classification"]
        if fng_value < 25:
            fng_score = 2  # 基础分2
        elif fng_value < 40:
            fng_score = 1  # 基础分1
        elif fng_value > 75:
            fng_score = -2  # 基础分-2
        elif fng_value > 60:
            fng_score = -1  # 基础分-1

        if fng_score != 0:
            total_score += fng_score * cycle_weights["1d"]
            breakdown.append(
                {
                    "name": f"F&G指数({fng_value}-{classification})",
                    "score": fng_score * cycle_weights["1d"],
                }
            )

    # 2. 订单薄数据
    # 作为一个独立的实时补充信号，不乘以周期权重，但提高触发阈值
    if order_book_data and order_book_data.get("data_available", False):
        ratio = order_book_data.get("bid_ask_ratio", 1.0)
        order_book_score = 0
        if ratio > 2.0:  # 提高买卖比阈值，捕捉更强的信号
            order_book_score = 2
        elif ratio < 0.5:
            order_book_score = -2

        if order_book_score != 0:
            total_score += order_book_score
            breakdown.append(
                {"name": f"订单薄买卖比({ratio:.2f})", "score": order_book_score}
            )

    # 3. 多周期指标分析 (RSI, EMA, KDJ)
    for cycle in ["15m", "4h", "1d"]:
        rsi = indicators.get(f"rsi_{cycle}")
        golden_cross = indicators.get(f"golden_cross_{cycle}")
        death_cross = indicators.get(f"death_cross_{cycle}")
        kdj_golden_cross = indicators.get(f"kdj_golden_cross_{cycle}")
        kdj_death_cross = indicators.get(f"kdj_death_cross_{cycle}")
        close_price = indicators.get(f"close_{cycle}")
        ema12 = indicators.get(f"ema12_{cycle}")
        ema26 = indicators.get(f"ema26_{cycle}")

        # RSI 评分 (基础分 ±2)
        rsi_score = 0
        if rsi is not None:
            if rsi > 75:
                rsi_score = -2
            elif rsi < 25:
                rsi_score = 2
            if rsi_score != 0:
                total_score += rsi_score * cycle_weights[cycle]
                breakdown.append(
                    {
                        "name": f"{cycle} RSI({rsi:.2f})",
                        "score": rsi_score * cycle_weights[cycle],
                    }
                )

        # EMA 交叉评分 (基础分 ±3，趋势信号权重更高)
        ema_cross_score = 0
        if golden_cross:
            ema_cross_score = 3
        elif death_cross:
            ema_cross_score = -3
        if ema_cross_score != 0:
            total_score += ema_cross_score * cycle_weights[cycle]
            breakdown.append(
                {
                    "name": f"{cycle} EMA交叉",
                    "score": ema_cross_score * cycle_weights[cycle],
                }
            )

        # KDJ 交叉评分 (基础分 ±1)
        kdj_cross_score = 0
        if kdj_golden_cross:
            kdj_cross_score = 1
        elif kdj_death_cross:
            kdj_cross_score = -1
        if kdj_cross_score != 0:
            total_score += kdj_cross_score * cycle_weights[cycle]
            breakdown.append(
                {
                    "name": f"{cycle} KDJ交叉",
                    "score": kdj_cross_score * cycle_weights[cycle],
                }
            )

        # EMA 排列 (仅日线和4h)
        if cycle in ["1d", "4h"]:
            ema_trend_score = 0
            if close_price and ema12 and ema26:
                if close_price > ema12 > ema26:
                    ema_trend_score = 1  # 基础分1
                elif close_price < ema12 < ema26:
                    ema_trend_score = -1  # 基础分-1

            if ema_trend_score != 0:
                total_score += ema_trend_score * cycle_weights[cycle]
                breakdown.append(
                    {
                        "name": f"{cycle} EMA排列",
                        "score": ema_trend_score * cycle_weights[cycle],
                    }
                )

    # 最终决策
    decision = "🟡 观望"
    if total_score >= 10:
        decision = "🟢 超级买入"
    elif total_score >= 5:
        decision = "🟢 买入"
    elif total_score <= -10:
        decision = "💣 超级卖出"
    elif total_score <= -5:
        decision = "🔴 卖出"

    return {"decision": decision, "score": total_score, "breakdown": breakdown}


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
                decision_data = make_decision(all_indicators, fng_data, order_book_data)
                print(f"\n最终决策: {decision_data['decision']}")
                print(f"总分: {decision_data['score']}")
                print(f"归因: {decision_data['breakdown']}")
            else:
                print("\n无法进行决策，因为部分数据获取失败。")
        else:
            print("\n无法计算多时间周期指标。")
    else:
        print("\n无法获取多时间周期K线数据。")
