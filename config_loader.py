import yaml
import os


def load_config(path="config.yaml"):
    """加载并解析 YAML 配置文件"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        print(f"错误：配置文件 '{path}' 未找到。")
        return None
    except yaml.YAMLError as e:
        print(f"错误：解析配置文件 '{path}' 时出错：{e}")
        return None


# 加载一次，以便其他模块可以直接导入
config = load_config()

# 优先从环境变量中读取敏感信息（例如 GitHub Actions Secrets）
# 这样就可以覆盖 config.yaml 中的值
if config:  # 确保配置已成功加载
    webhook_env = os.getenv("FEISHU_WEBHOOK_URL")
    if webhook_env:
        # 确保 'feishu' key 存在，避免 KeyErrors
        if "feishu" not in config:
            config["feishu"] = {}
        config["feishu"]["webhook_url"] = webhook_env


if __name__ == "__main__":
    # 用于测试
    if config:
        print("配置加载成功:")
        import json

        print(json.dumps(config, indent=2, ensure_ascii=False))
