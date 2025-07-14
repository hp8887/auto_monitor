import requests
import time
import pandas as pd
import json
from datetime import datetime, timedelta
from logger_setup import logger
from config_loader import config

# --- 配置 ---
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"
FEAR_GREED_API_URL = "https://api.alternative.me/fng/?limit=1"
# 使用 CryptoCompare API 代替 Binance，通常不会被墙
CRYPTOCOMPARE_API_URL = "https://min-api.cryptocompare.com/data"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


# --- 辅助函数 ---
def _make_request(url, params=None):
    """
    发起一个带重试机制的 GET 请求
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()  # 如果状态码不是 2xx，则抛出异常
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"请求 '{url}' 失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.error(f"请求 '{url}' 在 {MAX_RETRIES} 次尝试后最终失败。")
                return None


# --- 数据获取函数 ---


def get_btc_price_and_change():
    """
    从 CoinGecko 获取 BTC 的最新价格和 24 小时变化百分比
    """
    logger.info("正在从 CoinGecko 获取 BTC 价格和24小时变动...")
    params = {"ids": "bitcoin", "vs_currencies": "usd", "include_24hr_change": "true"}
    url = f"{COINGECKO_API_URL}/simple/price"
    data = _make_request(url, params)

    if data and "bitcoin" in data:
        price = data["bitcoin"].get("usd")
        change_24h = data["bitcoin"].get("usd_24h_change")
        if price is not None and change_24h is not None:
            logger.info(f"获取成功: 价格=${price}, 24h变化={change_24h:.2f}%")
            return {"price": price, "change_24h": change_24h}
    logger.error("无法从 CoinGecko 获取 BTC 数据。")
    return None


def get_fear_and_greed_index():
    """
    从 alternative.me 获取最新的恐惧贪婪指数
    """
    logger.info("正在从 alternative.me 获取恐惧贪婪指数...")
    data = _make_request(FEAR_GREED_API_URL)

    if data and "data" in data and len(data["data"]) > 0:
        index_value = int(data["data"][0].get("value"))
        classification = data["data"][0].get("value_classification")

        # 将英文分类翻译成中文
        translation_map = {
            "Extreme Greed": "极度贪婪",
            "Greed": "贪婪",
            "Neutral": "中性",
            "Fear": "恐惧",
            "Extreme Fear": "极度恐惧",
        }
        chinese_classification = translation_map.get(classification, classification)

        logger.info(f"获取成功: 恐惧贪婪指数={index_value} ({chinese_classification})")
        return {"value": index_value, "classification": chinese_classification}
    logger.error("无法从 alternative.me 获取恐惧贪婪指数。")
    return None


def _convert_timeframe_to_cryptocompare(interval):
    """
    将通用时间周期格式转换为 CryptoCompare API 所需的格式
    """
    # CryptoCompare 使用以下格式：
    # minute, hour, day
    if interval == "15m":
        return "minute", 15  # 15分钟
    elif interval == "4h":
        return "hour", 4  # 4小时
    elif interval == "1d":
        return "day", 1  # 1天
    else:
        # 默认返回日线
        logger.warning(f"不支持的时间周期 '{interval}'，使用默认值 '1d'")
        return "day", 1


def get_klines(symbol="BTCUSDT", interval="1d", limit=100):
    """
    从 CryptoCompare 获取 K 线数据
    :param symbol: 交易对, e.g., 'BTCUSDT'
    :param interval: K线间隔, e.g., '15m', '4h', '1d'
    :param limit: 数据点数量
    :return: 模拟币安格式的K线数据列表
    """
    # 提取交易对的基础货币和计价货币
    base_currency = symbol[:3] if symbol.endswith("USDT") else symbol.split("USDT")[0]
    quote_currency = "USDT"

    # 转换为 CryptoCompare 格式
    unit, multiplier = _convert_timeframe_to_cryptocompare(interval)

    logger.info(
        f"正在从 CryptoCompare 获取 {symbol} 的 {interval} K线数据 (最近 {limit} 条)..."
    )

    # 构建 API 请求
    if unit == "minute":
        endpoint = f"{CRYPTOCOMPARE_API_URL}/v2/histominute"
        params = {
            "fsym": base_currency,
            "tsym": quote_currency,
            "limit": limit,
            "aggregate": multiplier,
        }
    elif unit == "hour":
        endpoint = f"{CRYPTOCOMPARE_API_URL}/v2/histohour"
        params = {
            "fsym": base_currency,
            "tsym": quote_currency,
            "limit": limit,
            "aggregate": multiplier,
        }
    else:  # day
        endpoint = f"{CRYPTOCOMPARE_API_URL}/v2/histoday"
        params = {"fsym": base_currency, "tsym": quote_currency, "limit": limit}

    data = _make_request(endpoint, params)

    if data and data.get("Response") == "Success" and "Data" in data:
        # 转换为币安格式的 K 线数据
        klines = []
        for candle in data["Data"]["Data"]:
            # CryptoCompare 格式: {time, high, low, open, close, volumefrom, volumeto}
            # 币安格式: [open_time, open, high, low, close, volume, ...]
            timestamp = candle["time"] * 1000  # 转换为毫秒
            kline_row = [
                timestamp,  # 开盘时间
                str(candle["open"]),  # 开盘价
                str(candle["high"]),  # 最高价
                str(candle["low"]),  # 最低价
                str(candle["close"]),  # 收盘价
                str(candle["volumeto"]),  # 交易量
                timestamp
                + (
                    multiplier
                    * (
                        60000
                        if unit == "minute"
                        else 3600000 if unit == "hour" else 86400000
                    )
                )
                - 1,  # 收盘时间
                "0",  # 报价资产交易量
                "0",  # 交易笔数
                "0",  # 买方基础资产交易量
                "0",  # 买方报价资产交易量
                "0",  # 忽略
            ]
            klines.append(kline_row)

        logger.info(f"成功获取 {len(klines)} 条K线数据。")
        return klines

    logger.error(f"无法从 CryptoCompare 获取 {symbol} 的K线数据。")
    return None


def get_multi_timeframe_data(symbol="BTCUSDT", timeframes=None, limits=None):
    """
    获取多个时间周期的 K 线数据
    :param symbol: 交易对，例如 'BTCUSDT'
    :param timeframes: 时间周期列表，例如 ['15m', '4h', '1d']
    :param limits: 每个时间周期对应的数据点数量，例如 [96, 60, 30]
    :return: 包含各个时间周期 K 线数据的字典
    """
    if timeframes is None:
        timeframes = ["15m", "4h", "1d"]

    if limits is None:
        limits = [
            96,
            60,
            30,
        ]  # 默认值：15分钟取96条(24小时)，4小时取60条(10天)，日线取30条

    if len(timeframes) != len(limits):
        logger.warning("时间周期列表和数据点数量列表长度不匹配，使用默认值")
        limits = [96, 60, 30]

    result = {}
    for tf, limit in zip(timeframes, limits):
        klines = get_klines(symbol=symbol, interval=tf, limit=limit)
        if klines:
            result[tf] = klines
        else:
            logger.error(f"无法获取 {symbol} 的 {tf} 周期数据")

    return result


def get_order_book_data(symbol="BTCUSDT", limit=20):
    """
    从 KuCoin 获取订单薄数据
    :param symbol: 交易对，例如 'BTCUSDT'，将自动转换为 'BTC-USDT'
    :param limit: 买卖盘深度 (KuCoin level2_20 or level2_100)
    :return: 包含订单薄信息的字典
    """
    logger.info(f"正在从 KuCoin 获取 {symbol} 的订单薄数据...")

    # KuCoin API 使用 "BTC-USDT" 格式
    kucoin_symbol = symbol.replace("USDT", "-USDT")

    # 构建API请求
    KUCOIN_API_URL = "https://api.kucoin.com"
    endpoint = f"{KUCOIN_API_URL}/api/v1/market/orderbook/level2_{limit}"
    params = {"symbol": kucoin_symbol}

    data = _make_request(endpoint, params)

    # 检查从 KuCoin API 返回的错误
    if not data or data.get("code") != "200000" or not data.get("data"):
        logger.error(
            f"从 KuCoin 获取 {kucoin_symbol} 的订单薄数据失败: {data.get('msg', '无详细错误信息')}"
        )
        return {
            "bids": [],
            "asks": [],
            "bid_ask_ratio": 1.0,
            "spread": 0.0,
            "timestamp": int(time.time()),
            "data_available": False,  # 明确标记数据不可用
        }

    order_book = data["data"]
    bids = [
        {"price": float(p), "amount": float(a)} for p, a in order_book.get("bids", [])
    ]
    asks = [
        {"price": float(p), "amount": float(a)} for p, a in order_book.get("asks", [])
    ]

    # 计算买卖比例
    total_bid_volume = sum(item["amount"] for item in bids)
    total_ask_volume = sum(item["amount"] for item in asks)
    bid_ask_ratio = total_bid_volume / total_ask_volume if total_ask_volume > 0 else 1.0

    # 计算买一卖一价差
    # Asks 按价格升序排序, bids 按价格降序排序
    spread = (asks[0]["price"] - bids[0]["price"]) / asks[0]["price"] * 100

    result = {
        "bids": bids,
        "asks": asks,
        "bid_ask_ratio": bid_ask_ratio,
        "spread": spread,
        "timestamp": int(order_book.get("time")),
        "data_available": True,
    }

    logger.info(
        f"成功从 KuCoin 获取订单薄数据，买卖比: {bid_ask_ratio:.2f}, 价差: {spread:.2f}%"
    )
    return result


# --- Pivot Points 计算 ---


def calc_pivot_levels(high, low, close):
    """
    根据给定的高、低、收盘价计算标准 Pivot Point 及其支撑位和压力位。
    """
    pivot = (high + low + close) / 3
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high
    r2 = pivot + (high - low)  # 经典公式 R2 = Pivot + (R1 - S1)
    s2 = pivot - (high - low)  # 经典公式 S2 = Pivot - (R1 - S1)
    r3 = high + 2 * (pivot - low)
    s3 = low - 2 * (high - pivot)

    # 返回一个字典，键是支撑/阻力位的名称，值是计算结果，保留两位小数
    return {
        "pivot": round(pivot, 2),
        "resistance": {
            "R1": round(r1, 2),
            "R2": round(r2, 2),
            "R3": round(r3, 2),
        },
        "support": {
            "S1": round(s1, 2),
            "S2": round(s2, 2),
            "S3": round(s3, 2),
        },
    }


def get_pivot_points_for_all_timeframes(symbol="BTCUSDT", timeframes=None):
    """
    为指定的时间周期列表计算 Pivot Point。
    使用每个周期的前一根K线来计算当前周期的支撑/压力位。
    """
    if timeframes is None:
        timeframes = ["15m", "4h", "1d"]

    logger.info(f"开始为周期 {timeframes} 计算 Pivot Points...")

    all_pivots = {}

    for tf in timeframes:
        # 我们需要前一根K线来计算，所以获取最近的两根
        klines = get_klines(symbol=symbol, interval=tf, limit=2)

        if klines and len(klines) >= 2:
            # 使用倒数第二根K线 (即前一个完整周期的K线)
            previous_kline = klines[-2]

            # K线数据格式: [timestamp, open, high, low, close, volume, ...]
            high = float(previous_kline[2])
            low = float(previous_kline[3])
            close = float(previous_kline[4])

            logger.info(
                f"周期 {tf}: 使用前一根K线数据 (High={high}, Low={low}, Close={close})"
            )

            pivot_levels = calc_pivot_levels(high, low, close)
            all_pivots[tf] = pivot_levels
        else:
            logger.warning(f"无法获取足够的K线数据来为周期 {tf} 计算 Pivot Points。")
            all_pivots[tf] = None  # 或者可以提供一个默认的空结构

    logger.info("所有周期的 Pivot Points 计算完成。")
    return all_pivots


if __name__ == "__main__":
    # --- 测试 ---
    print("\n--- 测试 CoinGecko API ---")
    btc_data = get_btc_price_and_change()
    if btc_data:
        print(f"BTC 价格: ${btc_data['price']}")
        print(f"24小时变化: {btc_data['change_24h']:.2f}%")

    print("\n--- 测试 Fear & Greed API ---")
    fng_data = get_fear_and_greed_index()
    if fng_data:
        print(f"恐惧贪婪指数: {fng_data['value']} ({fng_data['classification']})")

    print("\n--- 测试 CryptoCompare K-lines API ---")
    for interval in ["15m", "4h", "1d"]:
        klines = get_klines(interval=interval, limit=5)
        if klines:
            print(f"\n获取到 {len(klines)} 条 {interval} K线数据:")
            for k in klines:
                print(
                    f"  - 时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(k[0]/1000))}, 收盘价: {k[4]}"
                )

    print("\n--- 测试多时间周期数据获取 ---")
    mtf_data = get_multi_timeframe_data(
        timeframes=["15m", "4h", "1d"], limits=[10, 10, 10]
    )
    for tf, data in mtf_data.items():
        print(f"\n{tf} 周期数据: {len(data)} 条")

    print("\n--- 测试获取订单薄数据 ---")
    order_book = get_order_book_data()
    if order_book:
        print(f"买卖比: {order_book['bid_ask_ratio']:.2f}")
        print(f"价差: {order_book['spread']:.2f}%")
        print("买盘前5档:", order_book["bids"][:5])
        print("卖盘前5档:", order_book["asks"][:5])
