import logging
import logging.handlers
from config_loader import config


def setup_logger():
    """根据配置设置日志记录器"""
    log_config = config.get("log", {})
    log_path = log_config.get("path", "./logs/app.log")
    log_level_str = log_config.get("level", "INFO").upper()

    log_level = getattr(logging, log_level_str, logging.INFO)

    # 创建 logger
    logger = logging.getLogger("BtcBroadcast")
    logger.setLevel(log_level)

    # 防止重复添加 handler
    if logger.hasHandlers():
        logger.handlers.clear()

    # 创建 formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 创建 console handler
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 创建 file handler (带轮转)
    # 10MB per file, keep 5 backup files
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(log_level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


# 创建一个全局 logger 实例
logger = setup_logger()

if __name__ == "__main__":
    # 测试日志记录
    logger.debug("这是一条 debug 日志")
    logger.info("这是一条 info 日志")
    logger.warning("这是一条 warning 日志")
    logger.error("这是一条 error 日志")
    logger.critical("这是一条 critical 日志")
    print(f"日志已记录到: {config['log']['path']}")
