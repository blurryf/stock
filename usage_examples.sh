# 股票分析工具使用示例

# 1. 基本文本分析
python3 stock_analyzer.py --source demo

# 2. 生成带图表的分析报告
python3 stock_analyzer.py --source demo --chart

# 3. 分析真实股票并生成图表
python3 stock_analyzer.py AAPL --chart

# 4. 查看生成的图表文件
ls -la *_chart.png
