import pandas as pd
import pandas_ta as ta
from config_loader import config
from logger_setup import logger


def calculate_indicators(klines):
    """
    根据币安返回的 K 线数据计算技术指标 (SMA, RSI)
    :param klines: 从 get_binance_klines 获取的K线列表
    :return: 包含最新指标的字典，例如 {'sma_30': 12345.6, 'rsi_14': 45.6}
    """
    # 由于API返回数据点可能不足, 将指标计算所需天数降低
    sma_period = 20
    if not klines or len(klines) < sma_period:  # 确保有足够数据计算
        logger.warning(
            f"K线数据不足 (需要{sma_period}条, 实际{len(klines)}条)，无法计算技术指标。"
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
    # 使用 pandas_ta 库可以非常方便地计算
    # 计算 20 日简单移动平均线 (SMA)
    df.ta.sma(length=sma_period, append=True)
    # 计算 14 日相对强弱指数 (RSI)
    df.ta.rsi(length=14, append=True)

    # 获取最新的指标值
    # 注意：为了避免修改其他文件，这里仍使用 'sma_30' 作为键名
    latest_indicators = {
        "sma_30": df[f"SMA_{sma_period}"].iloc[-1],
        "rsi_14": df["RSI_14"].iloc[-1],
    }

    logger.info(
        f"技术指标计算完成: SMA_{sma_period}={latest_indicators['sma_30']:.2f}, RSI_14={latest_indicators['rsi_14']:.2f}"
    )
    return latest_indicators


def make_decision(price_data, indicators, fear_greed_index):
    """
    根据所有输入数据和配置的阈值，做出最终决策。
    :return: 一个决策字符串，如 '大量买入', '观望' 等.
    """
    if not all([price_data, indicators, fear_greed_index]):
        logger.error("数据不完整，无法做出决策。")
        return "数据不足"

    thresholds = config["thresholds"]
    current_price = price_data["price"]
    sma_30 = indicators["sma_30"]
    rsi_14 = indicators["rsi_14"]
    fng_value = fear_greed_index["value"]

    logger.info("开始决策...")
    logger.info(
        f"当前价格: {current_price}, SMA_30: {sma_30:.2f}, RSI_14: {rsi_14:.2f}, F&G指数: {fng_value}"
    )

    # --- 决策逻辑 ---
    # 这是一个简单的决策逻辑示例，您可以根据需要扩展

    # 恐惧贪婪指数作为强信号
    if fng_value <= thresholds["fear_index"]["buy_large"]:
        logger.info(
            f"决策：大量买入 (原因: 恐惧贪婪指数 <= {thresholds['fear_index']['buy_large']})"
        )
        return "大量买入"
    if fng_value >= thresholds["greed_index"]["sell_large"]:
        logger.info(
            f"决策：大量卖出 (原因: 恐惧贪婪指数 >= {thresholds['greed_index']['sell_large']})"
        )
        return "大量卖出"

    # 根据RSI判断
    if rsi_14 <= thresholds["rsi"]["buy_large"]:
        logger.info(f"决策：大量买入 (原因: RSI <= {thresholds['rsi']['buy_large']})")
        return "大量买入"
    if rsi_14 <= thresholds["rsi"]["buy_small"]:
        logger.info(f"决策：少量买入 (原因: RSI <= {thresholds['rsi']['buy_small']})")
        return "少量买入"
    if rsi_14 >= thresholds["rsi"]["sell_large"]:
        logger.info(f"决策：大量卖出 (原因: RSI >= {thresholds['rsi']['sell_large']})")
        return "大量卖出"
    if rsi_14 >= thresholds["rsi"]["sell_small"]:
        logger.info(f"决策：少量卖出 (原因: RSI >= {thresholds['rsi']['sell_small']})")
        return "少量卖出"

    # 如果其他指标没有触发，可以参考价格与SMA的关系
    sma_buy_threshold = sma_30 * thresholds["sma30_multiplier"]["buy_small"]
    sma_sell_threshold = sma_30 * thresholds["sma30_multiplier"]["sell_small"]

    if current_price < sma_buy_threshold:
        logger.info(
            f"决策：少量买入 (原因: 价格 < SMA_30 * {thresholds['sma30_multiplier']['buy_small']})"
        )
        return "少量买入"
    if current_price > sma_sell_threshold:
        logger.info(
            f"决策：少量卖出 (原因: 价格 > SMA_30 * {thresholds['sma30_multiplier']['sell_small']})"
        )
        return "少量卖出"

    logger.info("决策：观望 (未触发任何买卖信号)")
    return "观望"


if __name__ == "__main__":
    # --- 测试 ---
    from data_provider import (
        get_klines,
        get_btc_price_and_change,
        get_fear_and_greed_index,
    )

    print("\n--- 测试指标计算 ---")
    # 1. 获取K线数据
    test_klines = get_klines(limit=50)  # 获取50条数据以确保能计算
    if test_klines:
        # 2. 计算指标
        test_indicators = calculate_indicators(test_klines)
        if test_indicators:
            print(f"计算出的指标: {test_indicators}")

    print("\n--- 测试决策逻辑 ---")
    # 3. 获取实时数据
    test_price = get_btc_price_and_change()
    test_fng = get_fear_and_greed_index()

    # 4. 模拟数据进行决策
    if test_price and test_indicators and test_fng:
        decision = make_decision(test_price, test_indicators, test_fng)
        print(f"\n最终决策: {decision}")
    else:
        print("\n无法进行决策，因为部分数据获取失败。")
