FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUTF8=1 PYTHONIOENCODING=utf-8

# 使用与本地相同的核心依赖，包含截图页面所需的 Pillow。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 启动脚本可执行
RUN chmod +x start.sh

EXPOSE 8080

CMD ["./start.sh"]
