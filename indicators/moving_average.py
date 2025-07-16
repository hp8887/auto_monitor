import pandas as pd
import pandas_ta as ta
from logger_setup import logger
from config_loader import config
from data_provider import get_multi_timeframe_data


def calculate_moving_averages(symbol="BTCUSDT", timeframes=None) -> dict:
    """
    为指定的时间周期计算移动平均线相关指标 (SMA, EMA, Crosses)。

    :param symbol: 交易对, e.g., 'BTCUSDT'
    :param timeframes: 时间周期列表, e.g., ['15m', '4h', '1d']
    :return: 包含各周期移动平均线指标的字典。
    """
    if timeframes is None:
        timeframes = list(config.get("periods", {}).keys())

    # 请求足够的数据用于计算
    kline_data = get_multi_timeframe_data(
        symbol=symbol,
        timeframes=timeframes,
        limits=[100] * len(timeframes),
    )

    if not kline_data:
        logger.error("无法获取用于计算移动平均线的K线数据。")
        return {}

    all_ma_values = {}
    for tf in timeframes:
        klines = kline_data.get(tf)
        period_config = config.get("periods", {}).get(tf)

        if not klines or not period_config or len(klines) < 2:
            logger.warning(f"周期 {tf} 的K线数据或配置不足，无法计算移动平均线。")
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

        # --- 计算指标 ---
        sma_period = period_config.get("sma_period", 20)
        df.ta.sma(length=sma_period, append=True)
        df.ta.ema(length=12, append=True)
        df.ta.ema(length=26, append=True)

        # --- 提取最新值 ---
        latest_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        price = latest_row["close"]
        sma = latest_row[f"SMA_{sma_period}"]
        ema12 = latest_row["EMA_12"]
        ema26 = latest_row["EMA_26"]

        # --- 计算交叉信号 ---
        golden_cross = (
            prev_row["EMA_12"] < prev_row["EMA_26"]
            and latest_row["EMA_12"] > latest_row["EMA_26"]
        )
        death_cross = (
            prev_row["EMA_12"] > prev_row["EMA_26"]
            and latest_row["EMA_12"] < latest_row["EMA_26"]
        )

        # --- EMA 状态 ---
        ema_golden_state = ema12 > ema26
        ema_death_state = ema12 < ema26

        # --- EMA 排列趋势 ---
        ema_bullish_trend = price > ema12 > ema26
        ema_bearish_trend = price < ema12 < ema26

        # --- 组织返回结果 ---
        all_ma_values[tf] = {
            "sma": round(sma, 2) if pd.notna(sma) else None,
            "ema12": round(ema12, 2) if pd.notna(ema12) else None,
            "ema26": round(ema26, 2) if pd.notna(ema26) else None,
            "signals": {
                "golden_cross": golden_cross,
                "death_cross": death_cross,
                "ema_golden_state": ema_golden_state,
                "ema_death_state": ema_death_state,
                "ema_bullish_trend": ema_bullish_trend,
                "ema_bearish_trend": ema_bearish_trend,
            },
        }

    return all_ma_values


if __name__ == "__main__":
    # 用于直接测试此模块
    print("--- 移动平均线指标模块测试 ---")
    ma_values = calculate_moving_averages()
    import json

    print(json.dumps(ma_values, indent=2))
