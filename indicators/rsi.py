import pandas as pd
import pandas_ta as ta
from logger_setup import logger
from config_loader import config
from data_provider import get_multi_timeframe_data


def calculate_rsi(symbol="BTCUSDT", timeframes=None) -> dict:
    """
    为指定的时间周期计算RSI值。

    :param symbol: 交易对, e.g., 'BTCUSDT'
    :param timeframes: 时间周期列表, e.g., ['15m', '4h', '1d']
    :return: 包含各周期RSI值的字典, 格式为 {'15m': {'rsi': 35.4}, ...}
    """
    if timeframes is None:
        timeframes = list(config.get("periods", {}).keys())

    # 为了计算RSI，需要比周期更多的K线数据，这里请求100条以确保充足
    kline_data = get_multi_timeframe_data(
        symbol=symbol,
        timeframes=timeframes,
        limits=[100] * len(timeframes),
    )

    if not kline_data:
        logger.error("无法获取用于计算RSI的K线数据。")
        return {}

    all_rsi_values = {}
    for tf in timeframes:
        klines = kline_data.get(tf)
        period_config = config.get("periods", {}).get(tf)

        if not klines or not period_config:
            logger.warning(f"周期 {tf} 的K线数据或配置不足，无法计算RSI。")
            continue

        rsi_period = period_config.get("rsi_period", 14)

        if len(klines) < rsi_period:
            logger.warning(
                f"周期 {tf} 的K线数据量 ({len(klines)}) 小于RSI周期 ({rsi_period})，无法计算。"
            )
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
        df["close"] = pd.to_numeric(df["close"])

        # 使用 pandas-ta 计算 RSI
        df.ta.rsi(length=rsi_period, append=True)

        latest_rsi = df[f"RSI_{rsi_period}"].iloc[-1]
        if pd.notna(latest_rsi):
            all_rsi_values[tf] = {"rsi": round(latest_rsi, 2)}
        else:
            logger.warning(f"周期 {tf} 的最新RSI值为NaN。")

    return all_rsi_values


if __name__ == "__main__":
    # 用于直接测试此模块
    print("--- RSI 指标模块测试 ---")
    rsi_values = calculate_rsi()
    import json

    print(json.dumps(rsi_values, indent=2))
