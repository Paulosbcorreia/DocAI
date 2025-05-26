import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import sqlite3
import json
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conexão com o banco SQLite
def get_db_connection():
    conn = sqlite3.connect('documents.db')
    conn.row_factory = sqlite3.Row
    return conn

# Função para processar o documento (apenas PDFs)
def process_document(file_content, filename):
    try:
        if not filename.lower().endswith('.pdf'):
            return {"error": "Apenas arquivos PDF são suportados no momento"}

        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            text = ''.join(page.extract_text() for page in pdf.pages if page.extract_text())

        # Expressões regulares para extrair os campos
        patterns = {
            "placa": r"[A-Z]{3}\d[A-Z]\d{3}",  # Ex.: NZV2F04
            "nome_vendedor": r"[A-Z\s]+(?=\sDO\sPRADO|\sDE\sSOUZA)",  # Ex.: JOSE CARLOS DO PRADO SOUZA JUNIO
            "renavam": r"\d{11}(?=\sCPF)",  # Ex.: 00466456352
            "cpf_cnpj_vendedor": r"\d{3}\.\d{3}\.\d{3}-\d{2}",  # Ex.: 124.991.626-78
            "email_vendedor": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",  # Ex.: GVMUDI@GMAIL.COM
            "municipio_vendedor": r"[A-Z\s]+(?=\sMG)",  # Ex.: UBERLANDIA
            "uf_vendedor": r"MG(?=\sANO)",  # Ex.: MG
            "ano_fabricacao": r"\d{4}(?=\s\d{4})",  # Ex.: 2012
            "ano_modelo": r"\d{4}(?=\sValor)",  # Ex.: 2013
            "valor_venda": r"R\$\s?\d{1,3}(?:\.\d{3})*,\d{2}",  # Ex.: R$ 25.391,12
            "marca_modelo_versao": r"[A-Z]+/[A-Z\s]+(?=\sAutorizo)",  # Ex.: FIAT/PALIO FIRE ECONOMY
            "cor": r"[A-Z\s]+(?=\s9BD)",  # Ex.: PRATA
            "chassi": r"9BD\d{14}",  # Ex.: 9BD17164LD5827924
            "data_venda": r"\d{2}/\d{2}/\d{4}(?=\sNÚMERO)",  # Ex.: 10/03/2025
            "numero_crv": r"\d{12}(?=\s\d{11})",  # Ex.: 223389785779
            "codigo_seguranca_crv": r"\d{11}(?=\sNÚMERO)",  # Ex.: 25531084607
            "numero_atpve": r"\d{15}",  # Ex.: 250691017456352
            "data_emissao_crv": r"\d{2}/\d{2}/\d{4}(?=\sASSINATURA)",  # Ex.: 30/03/2022
            "hodometro": r"\d+(?=\sIDENTIFICAÇÃO)",  # Ex.: 0
            "nome_comprador": r"[A-Z\s]+(?=\sDE\sMELO)",  # Ex.: RAFAELA FARIA DE MELO
            "cpf_cnpj_comprador": r"\d{3}\.\d{3}\.\d{3}-\d{2}(?=\sGVMUDI)",  # Ex.: 065.391.846-11
            "email_comprador": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?=\sMUNICÍPIO)",  # Ex.: GVMUDI@GMAIL.COM
            "municipio_comprador": r"[A-Z\s]+(?=\sMG)",  # Ex.: UBERLANDIA
            "uf_comprador": r"MG(?=\sENDEREÇO)",  # Ex.: MG
            "endereco_comprador": r"[A-Z\s\d]+(?=\sCEP)",  # Ex.: R VERIDIANO TEODORO DOS SANTOS 1080 LUIZOTE DE FREITAS
            "cep_comprador": r"\d{5}-\d{3}"  # Ex.: 38414-315
        }

        # Dicionário para armazenar os resultados
        extracted_data = {}

        # Extrair os campos
        for campo, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            extracted_data[campo] = match.group().strip() if match else "Não encontrado"

        return {
            "extracted_data": extracted_data,
            "raw_text": text
        }

    except Exception as e:
        return {"error": str(e)}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    result = process_document(content, file.filename)

    if "error" in result:
        return {"message": "Erro ao processar o documento", "error": result["error"]}

    # Salvar no banco SQLite
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS documents 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, processed_at TIMESTAMP, status TEXT, extracted_fields INTEGER, data TEXT)''')
    cursor.execute('INSERT INTO documents (filename, processed_at, status, extracted_fields, data) VALUES (?, datetime('now'), ?, ?, ?)',
                   (file.filename, "Sucesso", len([v for v in result["extracted_data"].values() if v != "Não encontrado"]), json.dumps(result)))
    conn.commit()
    doc_id = cursor.lastrowid
    conn.close()

    # Retornar a resposta no formato desejado
    return {
        "message": "Documento processado com sucesso",
        "doc_id": doc_id,
        **result["extracted_data"]
    }

@app.get("/api/documents")
def get_documents():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents")
    documents = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"documents": documents}