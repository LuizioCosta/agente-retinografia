# ==========================================================================================
# Agente de Retinografia — servidor de inferência (FastAPI)
# ==========================================================================================
# O celular envia a retinografia; o servidor roda o pipeline EyeFlow V800 na GPU e devolve os
# dados do laudo. Como o Stage 2 leva 1–2 minutos, a análise é um "trabalho" assíncrono:
#   POST /api/analisar        → {"id": "..."}                (envio da imagem)
#   GET  /api/trabalhos/{id}  → {"estado","etapa","resultado"} (o app consulta a cada 2 s)
#   GET  /api/saude           → modelos carregados e desempenho medido
# Nenhuma imagem é gravada em disco: tudo fica na memória e o resultado é apagado após 1 hora.
#
# Variáveis de ambiente:
#   EYEFLOW_ROOT   pasta EyeFlow (padrão /content/drive/MyDrive/EyeFlow)
#   USAR_STAGE2    1 = carrega MedGemma-27B (padrão) | 0 = só Stage 1
#   HF_TOKEN       token do Hugging Face com acesso ao google/medgemma-27b-it
#   AGENTE_CHAVE   chave de acesso exigida no cabeçalho X-Chave (recomendado)
#   AGENTE_DEMO    1 = não carrega modelos e responde com o laudo de exemplo (teste do app)
# ==========================================================================================

import os, json, time, uuid, threading, queue, secrets, traceback
from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

CHAVE=os.environ.get("AGENTE_CHAVE","")
DEMO=os.environ.get("AGENTE_DEMO","0")=="1"
MAX_BYTES=25*1024*1024
TTL_S=3600
AQUI=Path(__file__).resolve().parent

app=FastAPI(title="Agente de Retinografia",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["GET","POST"],allow_headers=["*"])

MOTOR=None; ERRO_CARGA=None
TRABALHOS={}; FILA=queue.Queue(); LOCK=threading.Lock()

def carregar_motor():
    global MOTOR,ERRO_CARGA
    if DEMO: return
    try:
        from eyeflow_pipeline import Motor
        MOTOR=Motor().carregar()
    except Exception as e:
        ERRO_CARGA=f"{type(e).__name__}: {e}"; traceback.print_exc()

def resultado_demo(nome,paciente,olho):
    R=json.loads((AQUI.parent/"app"/"www"/"demo"/"exemplo.json").read_text(encoding="utf-8"))
    R["arquivo"]=nome; R["paciente"]=paciente
    if olho: R["olho"]=olho; R["nasal_direita"]=olho.upper().startswith("OD")
    time.sleep(3)
    return R

def trabalhador():
    """Uma única fila: a GPU processa um exame por vez, na ordem de chegada."""
    while True:
        jid=FILA.get()
        job=TRABALHOS.get(jid)
        if not job: continue
        def etapa(txt): job["etapa"]=txt
        job["estado"]="processando"; job["inicio"]=time.time()
        try:
            if DEMO: R=resultado_demo(job["nome"],job["paciente"],job["olho"])
            else: R=MOTOR.analisar(job.pop("dados"),job["nome"],job["paciente"],job["olho"],job["completo"],etapa)
            job["resultado"]=R; job["estado"]="concluido"
        except Exception as e:
            traceback.print_exc(); job["estado"]="erro"; job["erro"]=f"{type(e).__name__}: {e}"
        finally:
            job.pop("dados",None); job["fim"]=time.time()

def limpar():
    while True:
        time.sleep(300); agora=time.time()
        with LOCK:
            for k in [k for k,j in TRABALHOS.items() if agora-j["criado"]>TTL_S]: TRABALHOS.pop(k,None)

@app.on_event("startup")
def partida():
    threading.Thread(target=carregar_motor,daemon=True).start()
    threading.Thread(target=trabalhador,daemon=True).start()
    threading.Thread(target=limpar,daemon=True).start()

def checar_chave(x_chave):
    if CHAVE and not secrets.compare_digest(x_chave or "",CHAVE):
        raise HTTPException(401,"Chave de acesso inválida.")

@app.get("/api/saude")
def saude(x_chave:str|None=Header(None)):
    checar_chave(x_chave)
    if DEMO: return {"pronto":True,"demo":True,"stage2":True,"mensagem":"Servidor em modo demonstração (sem modelos)."}
    if ERRO_CARGA: return {"pronto":False,"erro":ERRO_CARGA,"mensagem":"Falha ao carregar os modelos."}
    if MOTOR is None: return {"pronto":False,"mensagem":"Carregando os modelos… (o MedGemma-27B leva cerca de 3 min)"}
    return {"pronto":True,"demo":False,**MOTOR.info,"fila":FILA.qsize()}

@app.post("/api/analisar")
async def analisar(imagem:UploadFile=File(...),paciente:str=Form(""),olho:str=Form(""),modo:str=Form("completo"),
                   x_chave:str|None=Header(None)):
    checar_chave(x_chave)
    if not DEMO and MOTOR is None:
        raise HTTPException(503,ERRO_CARGA or "Modelos ainda carregando. Tente em instantes.")
    dados=await imagem.read()
    if not dados: raise HTTPException(400,"Imagem vazia.")
    if len(dados)>MAX_BYTES: raise HTTPException(413,"Imagem maior que 25 MB.")
    olho=olho.strip().upper() or None
    if olho not in (None,"OD","OE"): raise HTTPException(400,"Olho deve ser OD, OE ou vazio.")
    jid=uuid.uuid4().hex
    with LOCK:
        TRABALHOS[jid]={"estado":"na fila","etapa":"Aguardando a GPU","criado":time.time(),"dados":dados,
                        "nome":imagem.filename or "retinografia.jpg","paciente":paciente.strip()[:80] or None,
                        "olho":olho,"completo":modo!="rapido"}
    FILA.put(jid)
    return {"id":jid,"posicao":FILA.qsize()}

@app.get("/api/trabalhos/{jid}")
def trabalho(jid:str,x_chave:str|None=Header(None)):
    checar_chave(x_chave)
    job=TRABALHOS.get(jid)
    if not job: raise HTTPException(404,"Análise não encontrada (expirou ou o servidor reiniciou).")
    out={"estado":job["estado"],"etapa":job.get("etapa")}
    if "inicio" in job: out["decorrido"]=round((job.get("fim") or time.time())-job["inicio"],1)
    if job["estado"]=="concluido": out["resultado"]=job["resultado"]
    if job["estado"]=="erro": out["erro"]=job["erro"]
    return out

# O próprio servidor também entrega o aplicativo web (útil para testar no navegador do celular).
WWW=AQUI.parent/"app"/"www"
if WWW.exists(): app.mount("/",StaticFiles(directory=str(WWW),html=True),name="app")
