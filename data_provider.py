import requests
import time
from logger_setup import logger

# --- 配置 ---
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"
FEAR_GREED_API_URL = "https://api.alternative.me/fng/?limit=1"
# 使用币安官方API
BINANCE_KLINE_API_URL = "https://api.binance.com/api/v3/klines"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


# --- 辅助函数 ---
def _make_request(url, params=None):
    """
    发起一个带重试机制的 GET 请求
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=10)
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
        logger.info(f"获取成功: 恐惧贪婪指数={index_value} ({classification})")
        return {"value": index_value, "classification": classification}
    logger.error("无法从 alternative.me 获取恐惧贪婪指数。")
    return None


def get_binance_klines(symbol="BTCUSDT", interval="1d", limit=100):
    """
    从币安获取 K 线数据
    :param symbol: 交易对, e.g., 'BTCUSDT'
    :param interval: K线间隔, e.g., '1h', '4h', '1d'
    :param limit: 数据点数量
    :return: K线数据列表
    """
    logger.info(f"正在从币安获取 {symbol} 的 {interval} K线数据 (最近 {limit} 条)...")
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    data = _make_request(BINANCE_KLINE_API_URL, params)

    if data:
        logger.info(f"成功获取 {len(data)} 条K线数据。")
        return data
    logger.error(f"无法从币安获取 {symbol} 的K线数据。")
    return None


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

    print("\n--- 测试 Binance K-lines API ---")
    klines = get_binance_klines(limit=5)
    if klines:
        print(f"获取到 {len(klines)} 条最新的K线数据:")
        # 每条K线数据是 [开盘时间, 开盘价, 最高价, 最低价, 收盘价, ...]
        for k in klines:
            print(
                f"  - 时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(k[0]/1000))}, 收盘价: {k[4]}"
            )
