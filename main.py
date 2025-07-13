import time
from logger_setup import logger
from config_loader import config
from data_provider import (
    get_multi_timeframe_data,
    get_btc_price_and_change,
    get_fear_and_greed_index,
    get_order_book_data,
)
from strategy import (
    calculate_indicators,
    compute_signal_for_period,
    make_weighted_score,
    interpret_score,
)
from llm_prompt import build_llm_prompt_text
from llm_curl_compound_beta import ask_llm_by_curl
from notifier_feishu import format_and_send_message


def main():
    """
    主函数，执行整个监控和播报流程
    """
    logger.info("================ 主流程开始 ================")

    # 1. 获取所有需要的数据
    logger.info("--- 步骤 1: 获取市场数据 ---")
    multi_timeframe_klines = get_multi_timeframe_data(timeframes=["15m", "4h", "1d"])
    price_data = get_btc_price_and_change()
    fng_data = get_fear_and_greed_index()
    order_book_data = get_order_book_data()

    if not all([multi_timeframe_klines, price_data, fng_data, order_book_data]):
        logger.error("获取基础数据失败，无法继续执行。")
        return

    # 2. 计算所有周期的技术指标
    logger.info("--- 步骤 2: 计算技术指标 ---")
    all_indicators = {}
    for timeframe, klines in multi_timeframe_klines.items():
        indicators = calculate_indicators(klines, timeframe)
        if indicators:
            all_indicators.update(indicators)

    if not all_indicators:
        logger.error("所有周期的指标均计算失败，流程中止。")
        return

    # 3. 为每个周期生成初步信号 (给LLM用)
    logger.info("--- 步骤 3: 生成分周期初步信号 ---")
    period_signals = {}
    for tf in ["15m", "4h", "1d"]:
        period_signals[tf] = compute_signal_for_period(all_indicators, tf)
        logger.info(f"周期 {tf} 初步信号: {period_signals[tf]}")

    # 4. 构建 Prompt 并调用 LLM (通过 curl)
    logger.info("--- 步骤 4: 调用大语言模型进行决策 (curl 方式) ---")
    prompt_text = build_llm_prompt_text(price_data, fng_data, period_signals)
    llm_response_text = ask_llm_by_curl(prompt_text)

    # 5. 计算规则系统决策（现在总是需要计算，为UI提供数据和LLM失败时兜底）
    logger.info("--- 步骤 5: 计算规则系统决策 (用于UI展示和失败兜底) ---")
    score, breakdown = make_weighted_score(all_indicators, fng_data, order_book_data)
    rule_decision = interpret_score(score)
    rule_decision_data = {
        "decision": rule_decision,
        "score": score,
        "breakdown": breakdown,
    }
    logger.info(f"规则决策结果: {rule_decision} (得分: {score})")

    # 6. 解析LLM响应，如果失败则使用规则决策
    logger.info("--- 步骤 6: 解析LLM响应并准备最终决策 ---")

    final_llm_decision = "决策辅助失败"
    final_llm_reason = f"LLM调用异常 ({llm_response_text})，下方为纯规则系统分析结果。"

    if "决策：" in llm_response_text and "理由：" in llm_response_text:
        try:
            parts = llm_response_text.split("\n")
            decision_part = parts[0]
            reason_part = parts[1]
            final_llm_decision = decision_part.replace("决策：", "").strip()
            final_llm_reason = reason_part.replace("理由：", "").strip()
            logger.info(f"LLM决策解析成功: {final_llm_decision}")
        except Exception as e:
            logger.error(f"解析LLM响应时出错: {e}")
            final_llm_reason = f"LLM响应格式不规范 ({llm_response_text})"

    final_llm_decision_data = {
        "decision": final_llm_decision,
        "reason": final_llm_reason,
    }

    # 7. 发送到飞书
    logger.info("--- 步骤 7: 格式化并发送播报到飞书 ---")
    format_and_send_message(
        price_data=price_data,
        all_indicators=all_indicators,
        fng_data=fng_data,
        order_book_data=order_book_data,
        rule_decision_data=rule_decision_data,
        llm_decision_data=final_llm_decision_data,  # 将最终处理过的LLM结果传入
    )

    logger.info("================ 主流程结束 ================\n")


if __name__ == "__main__":
    main()
