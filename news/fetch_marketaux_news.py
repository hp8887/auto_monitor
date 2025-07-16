import os
import requests
from logger_setup import logger


def get_news_with_scores(symbols: str = "BTC", max_items: int = 3) -> list:
    """
    从 Marketaux API 获取新闻，并根据其自带的情绪和影响力分数进行排序。
    V2: 修正解析逻辑，从 'entities' 字段中提取与请求符号匹配的分数。
    """
    api_token = os.getenv("MARKETAUX_API_TOKEN")
    if not api_token:
        logger.error("未找到环境变量 MARKETAUX_API_TOKEN，无法请求新闻数据。")
        return []

    # API 文档: https://www.marketaux.com/documentation
    # 我们需要 'sentiment_score' 和 'impact_score'，它们是付费计划的功能。
    api_url = "https://api.marketaux.com/v1/news/all"

    # 将字符串格式的 symbols 转换为列表，以便后续处理
    requested_symbols = [s.strip().upper() for s in symbols.split(",")]

    params = {
        "api_token": api_token,
        "symbols": symbols,  # API 请求仍然使用原始字符串
        "filter_entities": "true",
        "language": "en",
    }

    logger.info(f"正在从 Marketaux API 获取 {symbols} 的新闻...")
    try:
        response = requests.get(api_url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        raw_news_items = data.get("data", [])
        logger.info(f"成功从 Marketaux 获取到 {len(raw_news_items)} 条原始新闻。")
    except requests.exceptions.RequestException as e:
        logger.error(f"请求 Marketaux API 失败: {e}")
        return []

    if not raw_news_items:
        return []

    processed_news = []
    for item in raw_news_items:
        # 遍历每条新闻中的所有实体
        for entity in item.get("entities", []):
            entity_symbol = entity.get("symbol", "").upper()

            # 检查该实体的 symbol 是否在我们请求的列表中
            if entity_symbol in requested_symbols:
                # 从实体中提取情绪分数
                sentiment_score = entity.get("sentiment_score", 0.0)

                # impact_score 通常在顶层，但我们的API计划可能不返回它
                impact_score = item.get("impact_score", 0.0)

                processed_news.append(
                    {
                        "title": item.get("title"),
                        "published_at": item.get("published_at"),
                        "symbol": entity_symbol,  # 使用匹配到的实体符号
                        "sentiment_score": sentiment_score,
                        "sentiment_level": (
                            "positive"
                            if sentiment_score > 0.15
                            else "negative" if sentiment_score < -0.15 else "neutral"
                        ),
                        "impact_score": impact_score,
                        # 主要排序依据改为情绪分的绝对值，因为影响力分可能不存在
                        "sorting_score": abs(sentiment_score),
                    }
                )
                # 假设每条新闻只关联一个我们感兴趣的符号，跳出内层循环
                break

    if not processed_news:
        logger.warning(
            f"在返回的 {len(raw_news_items)} 条新闻中，未找到与符号 {symbols} 直接相关的新闻实体。"
        )
        return []

    # 按情绪分的绝对值进行降序排序
    sorted_news = sorted(processed_news, key=lambda x: x["sorting_score"], reverse=True)

    # 只需要返回部分字段，并直接从已处理的item中获取数据
    final_news_list = [
        {
            "title": item["title"],
            "published_at": item["published_at"],
            "symbol": item["symbol"],
            "sentiment_score": item["sentiment_score"],
            "sentiment_level": item["sentiment_level"],
            "impact_score": item["impact_score"],
        }
        for item in sorted_news
    ]

    logger.info(f"新闻处理和排序完成，找到 {len(final_news_list)} 条有效新闻。")

    return final_news_list[:max_items]


if __name__ == "__main__":
    # 用于直接测试此模块
    # 需要在项目根目录运行 `python -m news.fetch_marketaux_news`
    print("--- 新闻模块测试 ---")
    # 同时测试 BTC 和 ETH
    top_news = get_news_with_scores(symbols="BTC,ETH", max_items=5)
    if top_news:
        for i, news in enumerate(top_news):
            print(
                f"{i+1}. [{news['symbol']}] {news['title']}\n"
                f"   (Sentiment: {news['sentiment_score']:.2f} ({news['sentiment_level']}), "
                f"Impact: {news['impact_score']:.2f})"
            )
    else:
        print("未能获取或处理相关新闻。")
