import requests
import json
import time
from datetime import datetime
import pytz
from config_loader import config
from logger_setup import logger


def get_decision_color(decision):
    """根据决策返回不同的颜色"""
    if "买入" in decision:
        return "green"
    if "卖出" in decision:
        return "red"
    if "数据不足" in decision:
        return "grey"
    return "blue"


def format_feishu_message(
    price_data, indicators, fear_greed_index, order_book_data, decision_data
):
    """
    将所有数据格式化为飞书卡片消息
    """
    if not all([price_data, indicators, fear_greed_index, decision_data]):
        logger.error("数据不完整，无法格式化飞书消息。")
        # 返回一个简单的文本消息作为备用
        return {
            "msg_type": "text",
            "content": {"text": "BTC播报失败：数据获取不完整。"},
        }

    decision = decision_data["decision"]
    total_score = decision_data["score"]
    score_breakdown = decision_data["breakdown"]
    color = get_decision_color(decision)

    # 获取东八区当前时间
    tz = pytz.timezone("Asia/Shanghai")
    current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    # 获取各时间周期的RSI和SMA值
    rsi_15m = indicators.get("rsi_15m", 0)
    rsi_4h = indicators.get("rsi_4h", 0)
    rsi_1d = indicators.get("rsi_1d", 0)

    sma_15m = indicators.get("sma_15m", 0)
    sma_4h = indicators.get("sma_4h", 0)
    sma_1d = indicators.get("sma_1d", 0)

    # 获取各时间周期的EMA值和交叉信号
    ema12_15m = indicators.get("ema12_15m", 0)
    ema26_15m = indicators.get("ema26_15m", 0)
    golden_cross_15m = indicators.get("golden_cross_15m", False)
    death_cross_15m = indicators.get("death_cross_15m", False)

    ema12_4h = indicators.get("ema12_4h", 0)
    ema26_4h = indicators.get("ema26_4h", 0)
    golden_cross_4h = indicators.get("golden_cross_4h", False)
    death_cross_4h = indicators.get("death_cross_4h", False)

    ema12_1d = indicators.get("ema12_1d", 0)
    ema26_1d = indicators.get("ema26_1d", 0)
    golden_cross_1d = indicators.get("golden_cross_1d", False)
    death_cross_1d = indicators.get("death_cross_1d", False)

    # 获取各时间周期的KDJ值和交叉信号
    k_15m = indicators.get("k_15m", 0)
    d_15m = indicators.get("d_15m", 0)
    j_15m = indicators.get("j_15m", 0)
    kdj_golden_cross_15m = indicators.get("kdj_golden_cross_15m", False)
    kdj_death_cross_15m = indicators.get("kdj_death_cross_15m", False)

    k_4h = indicators.get("k_4h", 0)
    d_4h = indicators.get("d_4h", 0)
    j_4h = indicators.get("j_4h", 0)
    kdj_golden_cross_4h = indicators.get("kdj_golden_cross_4h", False)
    kdj_death_cross_4h = indicators.get("kdj_death_cross_4h", False)

    k_1d = indicators.get("k_1d", 0)
    d_1d = indicators.get("d_1d", 0)
    j_1d = indicators.get("j_1d", 0)
    kdj_golden_cross_1d = indicators.get("kdj_golden_cross_1d", False)
    kdj_death_cross_1d = indicators.get("kdj_death_cross_1d", False)

    # 生成各时间周期的简单信号
    signal_15m = "观望"
    if rsi_15m < 30:
        signal_15m = "🟢 买入"
    elif rsi_15m > 70:
        signal_15m = "🔴 卖出"

    signal_4h = "观望"
    if rsi_4h < 30:
        signal_4h = "🟢 买入"
    elif rsi_4h > 70:
        signal_4h = "🔴 卖出"

    signal_1d = "观望"
    if rsi_1d < 30:
        signal_1d = "🟢 买入"
    elif rsi_1d > 70:
        signal_1d = "🔴 卖出"

    # 组合归因信息
    # 按照分数绝对值排序，让影响更大的因素排在前面
    score_breakdown.sort(key=lambda x: abs(x["score"]), reverse=True)

    # 将打分信息格式化为美观的文本, 仅包含非零项
    attribution_items = []
    for item in score_breakdown:
        if item["score"] != 0:
            sign = "+" if item["score"] > 0 else ""
            attribution_items.append(f"{item['name']}: {sign}{item['score']}")

    # 准备订单薄数据展示
    if order_book_data and order_book_data.get("data_available", False):
        bid_ask_ratio = order_book_data.get("bid_ask_ratio", 1.0)
        spread = order_book_data.get("spread", 0.1)
        bids = order_book_data.get("bids", [])[:2]
        asks = order_book_data.get("asks", [])[:2]

        if bids:
            first_bid = f"${bids[0]['price']:,.2f}" if bids else "无数据"
        else:
            first_bid = "无数据"

        if asks:
            first_ask = f"${asks[0]['price']:,.2f}" if asks else "无数据"
        else:
            first_ask = "无数据"
    else:
        first_bid = "无数据"
        first_ask = "无数据"

    # 将归因信息合并为单行逗号分隔的文本
    attribution_text = ", ".join(attribution_items)

    # 生成决策解释或主要信号来源
    explanation_text = ""
    if "观望" in decision:
        explanation_text = "👉 **决策解释**: 多数指标方向不一致，或无强烈信号。"
    elif score_breakdown:
        # score_breakdown 已按分数绝对值排好序
        top_signals = [item["name"] for item in score_breakdown[:2]]
        if top_signals:
            explanation_text = f"👉 **主要信号来源**: {', '.join(top_signals)}"

    # 格式化价差和买卖比的显示
    spread_display = (
        f"{spread:.2f}%"
        if order_book_data and order_book_data.get("data_available", False)
        else "无数据"
    )
    ratio_display = (
        f"{bid_ask_ratio:.2f}"
        if order_book_data and order_book_data.get("data_available", False)
        else "无数据"
    )

    # 获取订单薄数据状态说明
    order_book_status = (
        "订单薄数据已获取"
        if order_book_data and order_book_data.get("data_available", False)
        else "订单薄数据获取失败"
    )

    # 构建卡片内容
    card_content = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": color,
                "title": {"content": f"BTC 市场观察: {decision}", "tag": "plain_text"},
            },
            "elements": [
                # 价格和基本信息
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**BTC 价格**\n${price_data['price']:,}",
                                "tag": "lark_md",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**24h 涨跌**\n{price_data['change_24h']:.2f}%",
                                "tag": "lark_md",
                            },
                        },
                    ],
                },
                # 恐惧贪婪指数和更新时间
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**F&G 指数**\n{fear_greed_index['value']} ({fear_greed_index['classification']})",
                                "tag": "lark_md",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**更新时间**\n{current_time}",
                                "tag": "lark_md",
                            },
                        },
                    ],
                },
                # 订单薄数据状态
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": False,
                            "text": {
                                "content": f"**订单薄数据**: 买卖比 {ratio_display} | 价差 {spread_display} | 买一 {first_bid} | 卖一 {first_ask}",
                                "tag": "lark_md",
                            },
                        },
                    ],
                },
                {"tag": "hr"},
                # 15分钟周期数据和EMA信息
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**15分钟周期**\nRSI: {rsi_15m:.2f}\nSMA20: ${sma_15m:,.2f}\n信号: {signal_15m}",
                                "tag": "lark_md",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**15分钟交叉信号**\nEMA交叉: {golden_cross_15m and '🔼金叉' or (death_cross_15m and '🔽死叉' or '无')}\nKDJ交叉: {kdj_golden_cross_15m and '🔼金叉' or (kdj_death_cross_15m and '🔽死叉' or '无')}",
                                "tag": "lark_md",
                            },
                        },
                    ],
                },
                # 4小时周期数据和EMA信息
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**4小时周期**\nRSI: {rsi_4h:.2f}\nSMA20: ${sma_4h:,.2f}\n信号: {signal_4h}",
                                "tag": "lark_md",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**4小时交叉信号**\nEMA交叉: {golden_cross_4h and '🔼金叉' or (death_cross_4h and '🔽死叉' or '无')}\nKDJ交叉: {kdj_golden_cross_4h and '🔼金叉' or (kdj_death_cross_4h and '🔽死叉' or '无')}",
                                "tag": "lark_md",
                            },
                        },
                    ],
                },
                # 日线周期数据和EMA信息
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**日线周期**\nRSI: {rsi_1d:.2f}\nSMA20: ${sma_1d:,.2f}\n信号: {signal_1d}",
                                "tag": "lark_md",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**日线交叉信号**\nEMA交叉: {golden_cross_1d and '🔼金叉' or (death_cross_1d and '🔽死叉' or '无')}\nKDJ交叉: {kdj_golden_cross_1d and '🔼金叉' or (kdj_death_cross_1d and '🔽死叉' or '无')}",
                                "tag": "lark_md",
                            },
                        },
                    ],
                },
                {"tag": "hr"},
                # 综合决策
                {
                    "tag": "div",
                    "text": {
                        "content": f"**综合决策: {decision}**",
                        "tag": "lark_md",
                    },
                },
                # 决策解释
                {
                    "tag": "div",
                    "text": {"content": explanation_text, "tag": "lark_md"},
                },
                # 决策归因
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "lark_md",
                            "content": f"📊 决策归因 (总分: {total_score}): {attribution_text}\n数据来源: CoinGecko, CryptoCompare, alternative.me. 仅供参考，非投资建议。",
                        }
                    ],
                },
            ],
        },
    }
    return card_content


def send_to_feishu(message_content):
    """
    将消息发送到飞书机器人
    """
    webhook_url = config.get("feishu", {}).get("webhook_url")
    if not webhook_url or "XXXXXXXX" in webhook_url:
        logger.error("飞书 Webhook URL 未配置或无效，无法发送消息。")
        return False

    logger.info("正在发送消息到飞书...")
    try:
        response = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(message_content),
            timeout=10,
        )
        response_data = response.json()
        if response.status_code == 200 and response_data.get("StatusCode") == 0:
            logger.info("消息成功发送到飞书。")
            return True
        else:
            logger.error(f"发送飞书消息失败: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"发送飞书消息时发生网络错误: {e}")
        return False


if __name__ == "__main__":
    # --- 测试 ---
    # 1. 准备模拟数据
    mock_price = {"price": 65000.88, "change_24h": -2.55}
    mock_indicators = {
        "sma_15m": 65000,
        "rsi_15m": 45,
        "golden_cross_15m": False,
        "death_cross_15m": True,
        "kdj_golden_cross_15m": False,
        "kdj_death_cross_15m": True,
        "ema12_15m": 65100,
        "ema26_15m": 65200,
        "sma_4h": 64000,
        "rsi_4h": 55,
        "golden_cross_4h": False,
        "death_cross_4h": False,
        "kdj_golden_cross_4h": True,
        "kdj_death_cross_4h": False,
        "ema12_4h": 64500,
        "ema26_4h": 64400,
        "sma_1d": 62000,
        "rsi_1d": 65,
        "golden_cross_1d": True,
        "death_cross_1d": False,
        "kdj_golden_cross_1d": True,
        "kdj_death_cross_1d": False,
        "ema12_1d": 63000,
        "ema26_1d": 62000,
        "k_15m": 20.1,
        "d_15m": 25.2,
        "j_15m": 10.3,
        "k_4h": 60.4,
        "d_4h": 55.5,
        "j_4h": 70.6,
        "k_1d": 80.7,
        "d_1d": 75.8,
        "j_1d": 90.9,
    }
    mock_fng = {"value": 28, "classification": "恐惧"}
    mock_order_book = {
        "bid_ask_ratio": 1.2,
        "spread": 0.15,
        "bids": [{"price": 64900, "quantity": 2.5}, {"price": 64800, "quantity": 3.1}],
        "asks": [{"price": 65100, "quantity": 1.8}, {"price": 65200, "quantity": 2.2}],
        "data_available": True,
    }
    # 模拟决策数据
    mock_decision_data = {
        "decision": "💣 超级卖出",
        "score": -11,
        "breakdown": [
            {"name": "F&G指数(79)", "score": -4},
            {"name": "日线RSI(76.6)", "score": -4},
            {"name": "4小时RSI(76.1)", "score": -3},
            {"name": "日线EMA多头排列", "score": 2},
            {"name": "买卖比(0.21)", "score": -2},
            {"name": "15分钟KDJ死叉", "score": -1},
            {"name": "15分钟EMA交叉", "score": 0},
            {"name": "4小时EMA交叉", "score": 0},
            {"name": "4小时KDJ金叉", "score": 2},
            {"name": "日线EMA金叉", "score": 3},
            {"name": "日线KDJ金叉", "score": 3},
        ],
    }

    # 2. 格式化消息
    feishu_message = format_feishu_message(
        mock_price, mock_indicators, mock_fng, mock_order_book, mock_decision_data
    )
    print("--- 格式化后的飞书卡片消息 ---")
    print(json.dumps(feishu_message, indent=2, ensure_ascii=False))

    # 3. 发送消息 (请确保 config.yaml 中的 webhook_url 是有效的)
    print("\n--- 尝试发送到飞书 ---")
    # 注意：下面这行代码默认是注释的，以防误发。
    # send_to_feishu(feishu_message)
    print("请取消注释 `send_to_feishu` 行并配置有效的URL以进行真实发送测试。")
