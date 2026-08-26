FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 파이썬 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# requirements.txt에 누락되었을 수 있는 필수 패키지 명시적 추가 설치
RUN pip install --no-cache-dir timm
RUN pip install --no-cache-dir fastapi uvicorn python-multipart qwen-vl-utils[decord]
RUN pip install --no-cache-dir git+https://github.com/myshell-ai/MeloTTS.git
RUN python -m unidic download
RUN python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng'); nltk.download('punkt_tab'); nltk.download('averaged_perceptron_tagger'); nltk.download('cmudict')"

# 소스 복사 (가중치 파일 weights/ 등 모두 포함)
RUN pip install --no-cache-dir --upgrade transformers soxr
COPY . .

# 포트 노출
EXPOSE 8000

# 서버 실행 (명시적으로 MOCK_MODE=False 권장)
ENV MOCK_MODE=False
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
