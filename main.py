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

    # 步骤 3: 计算规则系统决策和详细归因 (提前计算，为LLM提供素材)
    logger.info("--- 步骤 3: 计算规则系统决策和详细归因 ---")
    score, breakdown = make_weighted_score(all_indicators, fng_data, order_book_data)
    rule_decision = interpret_score(score)
    rule_decision_data = {
        "decision": rule_decision,
        "score": score,
        "breakdown": breakdown,
    }
    logger.info(f"规则决策结果: {rule_decision} (得分: {score})")

    # 步骤 4: 构建 Prompt 并调用 LLM (现在使用详细归因作为输入)
    logger.info("--- 步骤 4: 调用大语言模型进行决策 ---")
    # 注意：现在传递的是 breakdown 列表
    prompt_text = build_llm_prompt_text(price_data, fng_data, breakdown)
    llm_response = ask_llm_by_curl(prompt_text)

    # 初始化LLM决策的最终数据结构
    final_llm_decision_data = {
        "decision": "决策辅助失败",  # 默认值
        "reason": "",  # 默认值
        "success": False,  # 标记是否成功获取并解析
        "model_used": "无",  # 新增字段，记录使用的模型
    }

    if llm_response.get("success"):
        raw_text = llm_response.get("decision", "")
        final_llm_decision_data["model_used"] = llm_response.get("model_used", "未知")
        # 尝试解析 "决策："
        if "决策：" in raw_text:
            try:
                # 简单分割，提取“决策：”后的部分，并去除前后空格
                decision_part = raw_text.split("决策：")[1].split("\n")[0].strip()

                # 提取理由部分
                reason_part = raw_text
                if "理由：" in raw_text:
                    try:
                        reason_part = raw_text.split("理由：", 1)[1].strip()
                    except IndexError:
                        reason_part = "无法提取理由详情。"

                final_llm_decision_data["decision"] = decision_part
                final_llm_decision_data["reason"] = reason_part  # 理由是解析后的
                final_llm_decision_data["success"] = True
                logger.info(f"LLM 决策解析成功: {decision_part}")
            except IndexError:
                logger.error(
                    f"解析LLM响应格式时出错，虽然包含'决策：'但无法提取。响应: {raw_text}"
                )
                final_llm_decision_data["reason"] = f"LLM响应格式不规范 ({raw_text})"
        else:
            logger.warning(f"LLM响应中未找到'决策：'关键词。响应: {raw_text}")
            final_llm_decision_data["reason"] = f"LLM响应格式不规范 ({raw_text})"
    else:
        # 如果调用失败，decision 字段会包含具体的错误信息
        error_info = llm_response.get("decision", "决策辅助失败 (未知原因)")
        final_llm_decision_data["reason"] = (
            f"LLM调用异常 ({error_info})，下方为纯规则系统分析结果。"
        )
        final_llm_decision_data["model_used"] = llm_response.get("model_used", "无")
        logger.error(f"LLM 调用失败，原因: {error_info}")

    # 步骤 5: 此步骤已合并
    logger.info("--- 步骤 5: 决策数据准备完毕 ---")

    # 步骤 6: 发送到飞书
    logger.info("--- 步骤 6: 格式化并发送播报到飞书 ---")
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
