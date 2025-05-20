from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import pdfplumber
import pytesseract
from PIL import Image
import io
import sqlite3
import json
import csv
import re

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar banco de dados SQLite
def init_db():
    conn = sqlite3.connect("documents.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            processed_at TEXT,
            status TEXT,
            extracted_fields INTEGER,
            data TEXT
        )
    """)
    conn.commit()
    conn.close()

# Inicializar o banco de dados
init_db()

# Função para processar arquivos (PDFs ou imagens)
def process_document(file_content: bytes, filename: str) -> dict:
    try:
        text = ""
        extracted_data = []
        # Verificar o tipo de arquivo
        if filename.lower().endswith(".pdf"):
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    text += page_text.replace("\n", " ")
        elif filename.lower().endswith((".png", ".jpg", ".jpeg")):
            image = Image.open(io.BytesIO(file_content))
            text = pytesseract.image_to_string(image, lang="por").replace("\n", " ")
        else:
            raise HTTPException(status_code=400, detail="Formato de arquivo não suportado")

        # Extrair campos com regex (exemplo para NFS-e)
        cnpj = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", text)
        nome = re.search(r"Nome/NomeEmpresarial\s+([A-Z\s]+)", text)
        valor = re.search(r"ValordoServiço\s+R\$([\d,.]+)", text)
        extracted_data = [
            {"campo": "CNPJ", "valor": cnpj.group(0) if cnpj else "Não encontrado", "confiança": 0.95},
            {"campo": "Nome", "valor": nome.group(1).strip() if nome else "Não encontrado", "confiança": 0.90},
            {"campo": "Valor do Serviço", "valor": valor.group(1) if valor else "Não encontrado", "confiança": 0.90}
        ]
        return {"fields": extracted_data, "raw_text": text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar o arquivo: {str(e)}")

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()
    extracted_data = process_document(content, file.filename)
    doc_id = None
    try:
        conn = sqlite3.connect("documents.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO documents (filename, processed_at, status, extracted_fields, data) VALUES (?, ?, ?, ?, ?)",
            (
                file.filename,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Sucesso",
                len(extracted_data["fields"]),
                json.dumps(extracted_data)
            )
        )
        doc_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao salvar no banco: {str(e)}")
    finally:
        conn.close()
    return JSONResponse(content={"message": "Documento processado com sucesso", "data": extracted_data, "doc_id": doc_id})

@app.get("/api/documents")
async def list_documents():
    try:
        conn = sqlite3.connect("documents.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, filename, processed_at, status, extracted_fields, data FROM documents")
        documents = [
            {
                "id": row[0],
                "filename": row[1],
                "processed_at": row[2],
                "status": row[3],
                "extracted_fields": row[4],
                "data": json.loads(row[5])
            }
            for row in cursor.fetchall()
        ]
        return JSONResponse(content={"documents": documents})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar o banco: {str(e)}")
    finally:
        conn.close()

@app.get("/api/export/{doc_id}")
async def export_document(doc_id: int, format: str = "json"):
    try:
        conn = sqlite3.connect("documents.db")
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Documento não encontrado")
        data = json.loads(row[0])
        if format == "json":
            return JSONResponse(content=data)
        elif format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Campo", "Valor", "Confiança"])
            for field in data["fields"]:
                writer.writerow([field["campo"], field["valor"], field["confiança"]])
            return {"content": output.getvalue()}
        else:
            raise HTTPException(status_code=400, detail="Formato inválido")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao exportar: {str(e)}")
    finally:
        conn.close()

@app.post("/api/integrate/{platform}")
async def integrate_platform(platform: str, payload: dict):
    if platform.lower() in ["bubble", "airtable", "webflow"]:
        return JSONResponse(content={"message": f"Integrado com {platform} com sucesso"})
    raise HTTPException(status_code=400, detail="Plataforma não suportada")