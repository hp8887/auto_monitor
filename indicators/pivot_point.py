# indicators/pivot_point.py

import pandas as pd
from logger_setup import logger
from data_provider import get_multi_timeframe_data


def _calc_pivot_levels(high: float, low: float, close: float) -> dict:
    """
    根据给定的高、低、收盘价计算枢轴点位。
    """
    pivot = (high + low + close) / 3
    r1 = (2 * pivot) - low
    s1 = (2 * pivot) - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    r3 = high + 2 * (pivot - low)
    s3 = low - 2 * (high - pivot)
    return {
        "pivot": round(pivot, 2),
        "resistance": {
            "R1": round(r1, 2),
            "R2": round(r2, 2),
            "R3": round(r3, 2),
        },
        "support": {"S1": round(s1, 2), "S2": round(s2, 2), "S3": round(s3, 2)},
    }


def calc_pivot_points(symbol="BTCUSDT", timeframes=None) -> dict:
    """
    为所有指定的时间周期计算枢轴点，并返回新方案指定的格式。
    """
    if timeframes is None:
        timeframes = ["15m", "4h", "1d"]

    # K线数量：只需要前一根K线来计算，所以请求2条数据
    limits = [2] * len(timeframes)
    kline_data = get_multi_timeframe_data(
        symbol=symbol, timeframes=timeframes, limits=limits
    )

    if not kline_data:
        logger.error("无法获取用于计算枢轴点的K线数据。")
        return {}

    all_pivot_points = {}
    for tf, klines in kline_data.items():
        if len(klines) < 2:
            logger.warning(f"周期 {tf} 的K线数据不足，无法计算枢轴点。")
            continue

        # 使用前一根K线 (倒数第二条)
        previous_kline = klines[-2]
        high = float(previous_kline[2])
        low = float(previous_kline[3])
        close = float(previous_kline[4])

        levels = _calc_pivot_levels(high, low, close)

        # 按照新方案的格式进行组织
        all_pivot_points[tf] = {
            "resistance": [
                levels["resistance"]["R1"],
                levels["resistance"]["R2"],
                levels["resistance"]["R3"],
            ],
            "support": [
                levels["support"]["S1"],
                levels["support"]["S2"],
                levels["support"]["S3"],
            ],
        }

    return all_pivot_points


if __name__ == "__main__":
    # 用于直接测试此模块
    # 需要能够访问到 data_provider.py 中的函数
    print("--- 枢轴点模块测试 ---")
    pivots = calc_pivot_points()
    import json

    print(json.dumps(pivots, indent=2))
