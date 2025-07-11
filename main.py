import time
from logger_setup import logger
from config_loader import config
from data_provider import (
    get_btc_price_and_change,
    get_fear_and_greed_index,
    get_binance_klines,
)
from strategy import calculate_indicators, make_decision
from notifier import format_feishu_message, send_to_feishu


def run_once():
    """
    执行一次完整的播报流程：获取数据 -> 计算指标 -> 做出决策 -> 发送通知
    """
    logger.info("=" * 20 + " 开始执行新一轮播报 " + "=" * 20)

    # 1. 获取所有原始数据
    price_data = get_btc_price_and_change()
    fear_greed_index = get_fear_and_greed_index()
    # 获取最近100天的日K线数据来计算指标
    klines = get_binance_klines(interval="1d", limit=100)

    # 检查数据完整性
    if not all([price_data, fear_greed_index, klines]):
        logger.error("由于部分数据源获取失败，本轮播报中止。")
        # （可选）发送一个失败通知
        error_msg = format_feishu_message(None, None, None, "数据获取失败")
        send_to_feishu(error_msg)
        logger.info("=" * 20 + " 本轮播报执行结束 " + "=" * 20 + "\n")
        return

    # 2. 计算技术指标
    indicators = calculate_indicators(klines)
    if not indicators:
        logger.error("由于技术指标计算失败，本轮播报中止。")
        error_msg = format_feishu_message(
            price_data, None, fear_greed_index, "指标计算失败"
        )
        send_to_feishu(error_msg)
        logger.info("=" * 20 + " 本轮播报执行结束 " + "=" * 20 + "\n")
        return

    # 3. 做出决策
    decision = make_decision(price_data, indicators, fear_greed_index)

    # 4. 格式化并发送消息
    message = format_feishu_message(price_data, indicators, fear_greed_index, decision)
    send_to_feishu(message)

    logger.info(f"最终决策: {decision}")
    logger.info("=" * 20 + " 本轮播报执行结束 " + "=" * 20 + "\n")


if __name__ == "__main__":
    try:
        run_once()
    except KeyboardInterrupt:
        logger.info("程序被手动中断。正在退出...")
    except Exception as e:
        logger.critical(f"程序遇到未处理的严重错误: {e}", exc_info=True)
