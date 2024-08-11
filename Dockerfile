FROM python:3.9-alpine

# ENV HTTP_PROXY=http://192.168.49.1:8282
# ENV HTTPS_PROXY=http://192.168.49.1:8282

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

# RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
