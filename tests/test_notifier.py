import pytest
from notifier import format_feishu_message


def test_format_feishu_message_structure_and_content():
    """
    测试格式化函数在给定标准数据时能否生成正确的结构和内容。
    """
    # 1. 准备模拟数据 (Arrange)
    price_data = {"price": 50000, "change_24h": 2.5}
    indicators = {
        "RSI": {"value": 60, "signal": "中性"},
        "MACD": {"value": 150, "signal": "看涨"},
        "MA": {"value": 48000, "signal": "高于均线"},
    }
    fear_greed_index = {"value": 70, "classification": "贪婪"}
    decision = "建议持有"

    # 2. 调用函数 (Act)
    result = format_feishu_message(price_data, indicators, fear_greed_index, decision)

    # 3. 断言结果 (Assert)
    # 检查基本结构
    assert "msg_type" in result
    assert result["msg_type"] == "interactive"
    assert "card" in result
    card = result["card"]
    assert "header" in card
    assert "elements" in card
    assert card["header"]["template"] == "green"

    # 检查关键内容是否在卡片JSON字符串中 (简单检查)
    import json

    card_json_string = json.dumps(card)

    assert "¥ 50000" in card_json_string
    assert "+2.50%" in card_json_string
    assert "贪婪 (70)" in card_json_string
    assert "RSI" in card_json_string
    assert "60" in card_json_string
    assert "MACD" in card_json_string
    assert "高于均线" in card_json_string
    assert "最终决策" in card_json_string
    assert "建议持有" in card_json_string


def test_format_feishu_message_with_missing_data():
    """
    测试当部分数据缺失时（例如，API失败），函数能否优雅地处理。
    """
    # 1. 准备模拟数据
    price_data = {"price": 50000, "change_24h": -1.2}
    decision = "数据获取失败"

    # 2. 调用函数 (传入 None for indicators and fear_greed_index)
    result = format_feishu_message(price_data, None, None, decision)

    # 3. 断言结果
    assert result is not None
    assert result["card"]["header"]["template"] == "red"  # 失败时应为红色

    import json

    card_json_string = json.dumps(result["card"])

    assert "¥ 50000" in card_json_string
    assert "-1.20%" in card_json_string
    assert "数据获取失败" in card_json_string
    # 确保指标相关的文本不会出现
    assert "RSI" not in card_json_string
    assert "恐惧贪婪指数" not in card_json_string
