FROM python:3.12-slim

WORKDIR /app

COPY frontend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    && pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

COPY frontend/ ./

EXPOSE 8501

# Streamlit needs to find pages/ directory
CMD ["streamlit", "run", "app.py", \
     "--server.port", "8501", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true"]
