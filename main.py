import time
from logger_setup import logger
from config_loader import config
from data_provider import (
    get_btc_price_and_change,
    get_fear_and_greed_index,
    get_multi_timeframe_data,
    get_order_book_data,
)
from strategy import calculate_multi_timeframe_indicators, make_decision
from notifier import send_to_feishu, format_feishu_message


def run_once():
    """
    执行一次完整的播报流程：获取数据 -> 计算指标 -> 做出决策 -> 发送通知
    """
    logger.info("=" * 20 + " 开始执行新一轮播报 " + "=" * 20)

    # 1. 获取所有原始数据
    price_data = get_btc_price_and_change()
    fear_greed_index = get_fear_and_greed_index()
    order_book_data = get_order_book_data(symbol=config["kline"]["symbol"])

    # 获取多时间周期K线数据 (15分钟, 4小时, 1天)
    mtf_data = get_multi_timeframe_data(
        symbol=config["kline"]["symbol"],
        timeframes=["15m", "4h", "1d"],
        limits=[96, 60, 30],  # 15分钟取96条(24小时)，4小时取60条(10天)，日线取30条
    )

    # 检查数据完整性
    if not all([price_data, fear_greed_index]) or not mtf_data:
        logger.error("由于部分数据源获取失败，本轮播报中止。")
        # （可选）发送一个失败通知
        error_msg = format_feishu_message(
            None,
            None,
            None,
            None,
            {"decision": "数据获取失败", "score": 0, "breakdown": []},
        )
        send_to_feishu(error_msg)  # 启用飞书通知
        logger.info("=" * 20 + " 本轮播报执行结束 " + "=" * 20 + "\n")
        return

    # 2. 计算多时间周期技术指标
    all_indicators = calculate_multi_timeframe_indicators(mtf_data)
    if not all_indicators:
        logger.error("由于技术指标计算失败，本轮播报中止。")
        error_msg = format_feishu_message(
            price_data,
            None,
            fear_greed_index,
            order_book_data,
            {"decision": "指标计算失败", "score": 0, "breakdown": []},
        )
        send_to_feishu(error_msg)  # 启用飞书通知
        logger.info("=" * 20 + " 本轮播报执行结束 " + "=" * 20 + "\n")
        return

    # 3. 做出决策
    decision_data = make_decision(
        price_data, all_indicators, fear_greed_index, order_book_data
    )

    # 4. 格式化并发送消息
    # 直接传递所有时间周期的指标
    message = format_feishu_message(
        price_data, all_indicators, fear_greed_index, order_book_data, decision_data
    )
    send_to_feishu(message)  # 启用飞书通知

    logger.info(f"最终决策: {decision_data['decision']}")
    logger.info("=" * 20 + " 本轮播报执行结束 " + "=" * 20 + "\n")


if __name__ == "__main__":
    try:
        run_once()
    except KeyboardInterrupt:
        logger.info("程序被手动中断。正在退出...")
    except Exception as e:
        logger.critical(f"程序遇到未处理的严重错误: {e}", exc_info=True)
