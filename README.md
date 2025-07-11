# auto_monitor

[![pipeline status](https://gitlab.com/hp88871/auto_monitor/badges/main/pipeline.svg)](https://gitlab.com/hp88871/auto_monitor/-/commits/main)

这是一个用于加密货币（特别是比特币）市场监控和自动播报的机器人项目。

它会定时执行，自动完成以下工作流：
1.  从多个数据源获取市场数据（价格、恐惧贪婪指数、K线）。
2.  基于K线计算技术指标。
3.  根据预设策略形成决策。
4.  通过飞书（Feishu）机器人发送格式化的播报通知。

项目被配置为可以通过 GitHub Actions 或 GitLab CI/CD 进行自动化调度。