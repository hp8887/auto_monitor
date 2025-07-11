import requests
import json
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


def format_feishu_message(price_data, indicators, fear_greed_index, decision):
    """
    将所有数据格式化为飞书卡片消息
    """
    if not all([price_data, indicators, fear_greed_index, decision]):
        logger.error("数据不完整，无法格式化飞书消息。")
        # 返回一个简单的文本消息作为备用
        return {
            "msg_type": "text",
            "content": {"text": "BTC播报失败：数据获取不完整。"},
        }

    color = get_decision_color(decision)

    card_content = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": color,
                "title": {"content": f"BTC 市场观察: {decision}", "tag": "plain_text"},
            },
            "elements": [
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
                                "content": f"**RSI (14D)**\n{indicators['rsi_14']:.2f}",
                                "tag": "lark_md",
                            },
                        },
                    ],
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "content": f"**SMA (30D)**\n${indicators['sma_30']:,.2f}",
                                "tag": "lark_md",
                            },
                        }
                    ],
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {
                            "content": "数据来源: CoinGecko, alternative.me, Binance. 仅供参考。",
                            "tag": "plain_text",
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
    mock_indicators = {"sma_30": 66000.50, "rsi_14": 38.5}
    mock_fng = {"value": 28, "classification": "Fear"}
    mock_decision = "少量买入"

    # 2. 格式化消息
    feishu_message = format_feishu_message(
        mock_price, mock_indicators, mock_fng, mock_decision
    )
    print("--- 格式化后的飞书卡片消息 ---")
    print(json.dumps(feishu_message, indent=2, ensure_ascii=False))

    # 3. 发送消息 (请确保 config.yaml 中的 webhook_url 是有效的)
    print("\n--- 尝试发送到飞书 ---")
    # 注意：下面这行代码默认是注释的，以防误发。
    # send_to_feishu(feishu_message)
    print("请取消注释 `send_to_feishu` 行并配置有效的URL以进行真实发送测试。")
