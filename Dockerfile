FROM python:3.10-slim

# Instalar dependências do sistema para o Tesseract
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libleptonica-dev \
    && rm -rf /var/lib/apt/lists/*

# Definir o diretório de trabalho
WORKDIR /app

# Copiar os arquivos da API
COPY . .

# Instalar as dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Expor a porta
EXPOSE 8000

# Comando para iniciar a API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]