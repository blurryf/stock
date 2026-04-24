#!/usr/bin/env python3
"""
Setup script for stock-analyzer package
"""

from setuptools import setup, find_packages

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="stock-analyzer",
    version="1.0.0",
    author="Stock Analyzer",
    author_email="",
    description="命令行股票分析工具，支持技术指标计算和图表生成",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    py_modules=["stock_analyzer"],
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "stock-analyzer=stock_analyzer:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    python_requires=">=3.8",
    keywords="stock analysis technical-indicators chart matplotlib",
)