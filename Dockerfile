FROM python:3.11-slim

WORKDIR /app

# 安装依赖
RUN pip install --no-cache-dir requests

# 复制项目文件
COPY . .

# 启动脚本可执行
RUN chmod +x start.sh

EXPOSE 8080

CMD ["./start.sh"]
