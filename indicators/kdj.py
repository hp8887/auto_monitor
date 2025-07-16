import pandas as pd
import pandas_ta as ta
from logger_setup import logger
from data_provider import get_multi_timeframe_data


def calculate_kdj(symbol="BTCUSDT", timeframes=None) -> dict:
    """
    为指定的时间周期计算KDJ指标和交叉信号。

    :param symbol: 交易对, e.g., 'BTCUSDT'
    :param timeframes: 时间周期列表, e.g., ['15m', '4h', '1d']
    :return: 包含各周期KDJ指标的字典。
    """
    # KDJ默认周期通常是9,3,3，这里硬编码，因为config里没有
    # pandas-ta默认就是(9, 3, 3)
    kdj_period = 9

    if timeframes is None:
        # 默认从config读取周期，和其它指标保持一致
        from config_loader import config

        timeframes = list(config.get("periods", {}).keys())

    kline_data = get_multi_timeframe_data(
        symbol=symbol,
        timeframes=timeframes,
        limits=[kdj_period + 5] * len(timeframes),  # 需要的数据量不多，周期+5即可
    )

    if not kline_data:
        logger.error("无法获取用于计算KDJ的K线数据。")
        return {}

    all_kdj_values = {}
    for tf in timeframes:
        klines = kline_data.get(tf)
        if not klines or len(klines) < kdj_period:
            logger.warning(f"周期 {tf} 的K线数据不足，无法计算KDJ。")
            continue

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

        # 使用 pandas-ta 计算 KDJ
        df.ta.kdj(append=True)

        # --- 提取最新值 ---
        latest_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        k = latest_row["K_9_3"]
        d = latest_row["D_9_3"]
        j = latest_row["J_9_3"]

        # --- 计算交叉信号 ---
        golden_cross = (
            prev_row["K_9_3"] < prev_row["D_9_3"]
            and latest_row["K_9_3"] > latest_row["D_9_3"]
        )
        death_cross = (
            prev_row["K_9_3"] > prev_row["D_9_3"]
            and latest_row["K_9_3"] < latest_row["D_9_3"]
        )

        # --- KDJ 状态 ---
        kdj_golden_state = k > d
        kdj_death_state = k < d

        # --- 组织返回结果 ---
        all_kdj_values[tf] = {
            "k": round(k, 2) if pd.notna(k) else None,
            "d": round(d, 2) if pd.notna(d) else None,
            "j": round(j, 2) if pd.notna(j) else None,
            "signals": {
                "golden_cross": golden_cross,
                "death_cross": death_cross,
                "kdj_golden_state": kdj_golden_state,
                "kdj_death_state": kdj_death_state,
            },
        }

    return all_kdj_values


if __name__ == "__main__":
    # 用于直接测试此模块
    print("--- KDJ 指标模块测试 ---")
    kdj_values = calculate_kdj()
    import json

    print(json.dumps(kdj_values, indent=2))
