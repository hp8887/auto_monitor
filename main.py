import time
import collections.abc
from logger_setup import logger
from config_loader import config
from data_provider import (
    get_btc_price_and_change,
    get_fear_and_greed_index,
    get_order_book_data,
)

# 从新的 decision_engine.py 导入规则引擎函数
from decision_engine import make_weighted_score, interpret_score

# 导入新的、模块化的指标函数
from indicators.pivot_point import calc_pivot_points
from indicators.rsi import calculate_rsi
from indicators.moving_average import calculate_moving_averages
from indicators.kdj import calculate_kdj

# 导入新闻获取函数
from news.fetch_marketaux_news import get_news_with_scores

from llm_prompt import build_llm_prompt_text
from llm_curl_compound_beta import ask_llm_by_curl
from notifier_feishu import format_and_send_message


def deep_merge(d, u):
    """
    递归合并字典。
    """
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = deep_merge(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def flatten_indicators(nested_indicators):
    """
    将新的嵌套指标字典展平为旧格式，以兼容 make_weighted_score 函数。
    e.g., {'15m': {'rsi': 30}} -> {'rsi_15m': 30}
    """
    flat_dict = {}
    for timeframe, indicators in nested_indicators.items():
        for key, value in indicators.items():
            if isinstance(value, dict):  # 处理 signals 等子字典
                for sub_key, sub_value in value.items():
                    flat_dict[f"{sub_key}_{timeframe}"] = sub_value
            else:
                flat_dict[f"{key}_{timeframe}"] = value
    return flat_dict


def main():
    """
    主函数，执行整个监控和播报流程
    """
    logger.info("================ 主流程开始 ================")

    # 1. 获取所有需要的数据 (非指标类)
    logger.info("--- 步骤 1: 获取基础市场数据 ---")
    price_data = get_btc_price_and_change()
    fng_data = get_fear_and_greed_index()
    order_book_data = get_order_book_data()
    news_data = get_news_with_scores()  # 获取新闻数据

    # 2. 计算所有周期的技术指标 (模块化调用)
    logger.info("--- 步骤 2: 计算所有技术指标 ---")
    pivot_points = calc_pivot_points()
    rsi_data = calculate_rsi()
    ma_data = calculate_moving_averages()
    kdj_data = calculate_kdj()

    # 将所有指标深度合并到一个字典中
    technical_indicators = {}
    deep_merge(technical_indicators, pivot_points)
    deep_merge(technical_indicators, rsi_data)
    deep_merge(technical_indicators, ma_data)
    deep_merge(technical_indicators, kdj_data)

    if not all([price_data, fng_data, order_book_data, technical_indicators]):
        logger.error("获取基础数据或计算技术指标失败，无法继续执行。")
        return

    # 步骤 3: 计算规则系统决策和详细归因
    logger.info("--- 步骤 3: 计算规则系统决策和详细归因 ---")
    # 为了兼容旧的 make_weighted_score，我们需要将新的嵌套字典展平
    flat_indicators_for_rules = flatten_indicators(technical_indicators)
    score, breakdown = make_weighted_score(
        flat_indicators_for_rules, fng_data, order_book_data, news_data
    )
    rule_decision = interpret_score(score)
    rule_decision_data = {
        "decision": rule_decision,
        "score": score,
        "breakdown": breakdown,
    }
    logger.info(f"规则决策结果: {rule_decision} (得分: {score})")

    # 步骤 4: 构建 Prompt 并调用 LLM (现在使用新的、结构化的技术指标)
    logger.info("--- 步骤 4: 调用大语言模型进行决策 ---")
    prompt_text = build_llm_prompt_text(
        price_data=price_data,
        fng_data=fng_data,
        rule_breakdown=breakdown,
        technical_indicators=technical_indicators,  # 传递新的嵌套字典
        news_data=news_data,  # 传递新闻数据
    )
    llm_response = ask_llm_by_curl(prompt_text)

    # ... (后续的 LLM 响应解析和飞书通知部分保持不变) ...
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
        all_indicators=technical_indicators,  # 传递新的嵌套字典
        fng_data=fng_data,
        order_book_data=order_book_data,
        rule_decision_data=rule_decision_data,
        llm_decision_data=final_llm_decision_data,
        # pivot_points_data 不再需要单独传递
    )

    logger.info("================ 主流程结束 ================\n")


if __name__ == "__main__":
    main()
