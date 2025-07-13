import requests
import json
from datetime import datetime
import pytz
from config_loader import config
from logger_setup import logger
import os


def get_decision_color(decision):
    """根据决策返回不同的颜色"""
    if "买入" in decision:
        return "green"
    if "卖出" in decision:
        return "red"
    return "blue"


def get_decision_emoji(decision):
    """根据决策返回不同的 emoji 前缀"""
    if "强烈买入" in decision:
        return "🟢🟢"
    if "买入" in decision:
        return "🟢"
    if "强烈卖出" in decision:
        return "🔴🔴"
    if "卖出" in decision:
        return "🔴"
    return "🟡"


def format_and_send_message(
    price_data,
    all_indicators,
    fng_data,
    order_book_data,
    rule_decision_data,
    llm_decision_data=None,
):
    """
    格式化所有数据为飞书卡片，并直接发送。
    这是一个集成的函数，包含了格式化和发送两个步骤。
    """
    # --------------------------------------------------------------------------
    # 1. 准备所有需要展示的数据
    # --------------------------------------------------------------------------
    rule_decision = rule_decision_data["decision"]
    total_score = rule_decision_data["score"]
    score_breakdown = sorted(
        rule_decision_data["breakdown"], key=lambda x: abs(x["score"]), reverse=True
    )
    color = get_decision_color(rule_decision)
    tz = pytz.timezone("Asia/Shanghai")
    current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    def get_rsi_status(rsi):
        if rsi > 70:
            return " (超买区)"
        if rsi < 30:
            return " (超卖区)"
        return " (中性区)"

    def get_simple_signal(rsi):
        if rsi < 30:
            return "🟢 买入"
        if rsi > 70:
            return "🔴 卖出"
        return "观望"

    def get_cross_status(golden, death):
        if golden:
            return "🔼金叉"
        if death:
            return "🔽死叉"
        return "无"

    # 准备各周期详细数据
    periods_data = {}
    for tf in ["15m", "4h", "1d"]:
        rsi = all_indicators.get(f"rsi_{tf}", 0)
        periods_data[tf] = {
            "rsi_text": f"{rsi:.2f}{get_rsi_status(rsi)}",
            "sma_text": f"${all_indicators.get(f'sma_{tf}', 0):,.2f}",
            "signal_text": get_simple_signal(rsi),
            "ema_cross": get_cross_status(
                all_indicators.get(f"golden_cross_{tf}"),
                all_indicators.get(f"death_cross_{tf}"),
            ),
            "kdj_cross": get_cross_status(
                all_indicators.get(f"kdj_golden_cross_{tf}"),
                all_indicators.get(f"kdj_death_cross_{tf}"),
            ),
        }

    # 准备归因和解释文本
    attribution_items = [
        f"{item['name']}: {'+' if item['score'] > 0 else ''}{item['score']}"
        for item in score_breakdown
        if item["score"] != 0
    ]
    attribution_text = ", ".join(attribution_items)

    top_signals = [item["name"] for item in score_breakdown[:2]]
    explanation_text = (
        f"👉 **主要信号来源**: {', '.join(top_signals)}"
        if "观望" not in rule_decision and top_signals
        else "👉 **决策解释**: 多数指标方向不一致，或无强烈信号。"
    )

    # 准备订单薄文本
    if order_book_data and order_book_data.get("data_available", False):
        order_book_text = f"买卖比 {order_book_data.get('bid_ask_ratio', 0):.2f} | 价差 {order_book_data.get('spread', 0):.2f}% | 买一 ${order_book_data.get('bids', [{'price': 0}])[0]['price']:,.2f} | 卖一 ${order_book_data.get('asks', [{'price': 0}])[0]['price']:,.2f}"
    else:
        order_book_text = "数据获取失败"

    # --------------------------------------------------------------------------
    # 2. 构建飞书卡片
    # --------------------------------------------------------------------------

    # --- 决定主标题和最终决策 ---
    # 优先使用 LLM 的决策，如果LLM调用失败，则使用规则系统的决策
    if llm_decision_data and llm_decision_data.get("success"):
        final_decision_source = "AI综合决策"
        final_decision_text = llm_decision_data.get("decision", "决策失败")
        # 从核心决策文本构建带表情符号的完整决策文本
        verbose_decision_text = (
            f"{get_decision_emoji(final_decision_text)} {final_decision_text}"
        )
    else:
        final_decision_source = "规则系统决策"
        final_decision_text = rule_decision
        # 规则决策本身已包含表情符号
        verbose_decision_text = final_decision_text

    card_color = get_decision_color(final_decision_text)

    elements = [
        # 基础信息
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**BTC 价格**\n${price_data['price']:,}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**24h 涨跌**\n{price_data['change_24h']:.2f}%",
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
                        "tag": "lark_md",
                        "content": f"**F&G 指数**\n{fng_data['value']} ({fng_data['classification']})",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**更新时间**\n{current_time}",
                    },
                },
            ],
        },
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": False,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**订单薄数据**: {order_book_text}",
                    },
                }
            ],
        },
        {"tag": "hr"},
    ]

    # 添加各周期指标
    for tf_key, tf_name in [("15m", "15分钟"), ("4h", "4小时"), ("1d", "日线")]:
        data = periods_data[tf_key]
        elements.extend(
            [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**{tf_name}周期**\nRSI: {data['rsi_text']}\nSMA20: {data['sma_text']}\n信号: {data['signal_text']}",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**{tf_name}交叉信号**\nEMA交叉: {data['ema_cross']}\nKDJ交叉: {data['kdj_cross']}",
                            },
                        },
                    ],
                },
            ]
        )

    elements.append({"tag": "hr"})

    # --- 构建 LLM 决策模块 ---
    if llm_decision_data and llm_decision_data.get("success"):
        llm_decision = llm_decision_data.get("decision", "解析错误")
        llm_reason = llm_decision_data.get("reason", "无详细理由")
        model_used = llm_decision_data.get("model_used", "未知模型")
        llm_decision_with_emoji = f"{get_decision_emoji(llm_decision)} {llm_decision}"

        llm_section_content = (
            f"**大模型综合决策 (AI-{model_used}): {llm_decision_with_emoji}**"
        )

        # 将解析后的理由作为正文内容添加
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": llm_section_content}}
        )
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": llm_reason,  # 这里是解析后的理由
                },
            }
        )
    else:
        # LLM 调用失败或解析失败
        error_reason = llm_decision_data.get("reason", "未知错误")
        model_used = llm_decision_data.get("model_used", "无")
        llm_section_content = f"**大模型综合决策 (AI-{model_used}):** {get_decision_emoji('失败')} 决策辅助失败\n{error_reason}"
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": llm_section_content}}
        )

    # --- 构建规则系统决策模块 ---
    elements.extend(
        [
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**规则系统决策 (传统技术指标决策): {rule_decision}**",
                },
            },
            {"tag": "div", "text": {"tag": "lark_md", "content": explanation_text}},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": attribution_text,
                },
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "风险提示：本内容仅为AI生成的技术指标分析，不构成任何投资建议。",
                    }
                ],
            },
        ]
    )

    card = {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"市场观察 · {final_decision_source}: {verbose_decision_text}",
            },
            "template": card_color,
        },
        "elements": elements,
    }

    # --------------------------------------------------------------------------
    # 3. 发送飞书消息
    # --------------------------------------------------------------------------
    send_to_feishu(card)


def send_to_feishu(card_data):
    """
    将构建好的飞书卡片数据发送到 webhook 地址。
    """
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        logger.error(
            "未在环境变量中找到 FEISHU_WEBHOOK_URL。请设置该环境变量。消息发送失败。"
        )
        return

    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(
            webhook_url, json={"msg_type": "interactive", "card": card_data}
        )
        response.raise_for_status()  # 如果请求失败 (非2xx响应), 则抛出异常

        response_json = response.json()
        if response_json.get("StatusCode") == 0 or response_json.get("code") == 0:
            logger.info("成功发送格式化消息到飞书。")
        else:
            logger.error(f"发送飞书消息失败，响应: {response.text}")

    except requests.exceptions.RequestException as e:
        logger.error(f"请求飞书 API 时发生网络错误: {e}")
    except json.JSONDecodeError:
        logger.error(f"无法解析飞书 API 的响应: {response.text}")


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
    # 模拟决策数据 (符合最新的加权评分模型和5档决策)
    mock_decision_data = {
        "decision": "🔴🔴 强烈卖出",
        "score": -12.5,
        "breakdown": [
            {"name": "1d EMA交叉", "score": -6.0},
            {"name": "F&G指数(82-极度贪婪)", "score": -4.0},
            {"name": "4h RSI(78.2)", "score": -3.0},
            {"name": "订单薄买卖比(0.45)", "score": -2.0},
            {"name": "1d KDJ交叉", "score": -2.0},
            {"name": "1d EMA排列", "score": 2.0},
            {"name": "4h EMA交叉", "score": 4.5},
            {"name": "15m KDJ交叉", "score": -1.0},
        ],
    }

    # 2. 格式化消息
    # The format_feishu_message function is removed, so this line will cause an error.
    # feishu_message = format_feishu_message(
    #     mock_price, mock_indicators, mock_fng, mock_order_book, mock_decision_data
    # )
    # print("--- 格式化后的飞书卡片消息 ---")
    # print(json.dumps(feishu_message, indent=2, ensure_ascii=False))

    # 3. 发送消息 (请确保 config.yaml 中的 webhook_url 是有效的)
    print("\n--- 尝试发送到飞书 ---")
    # 注意：下面这行代码默认是注释的，以防误发。
    format_and_send_message(
        mock_price,
        mock_indicators,
        mock_fng,
        mock_order_book,
        mock_decision_data,
    )
    print("请取消注释 `send_to_feishu` 行并配置有效的URL以进行真实发送测试。")
