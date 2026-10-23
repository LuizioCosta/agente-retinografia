# ==========================================================================================
# EyeFlow V800 — pipeline de inferência do "Agente de Retinografia"
# ==========================================================================================
# Código extraído do notebook EyeFlow_V800_Inferencia_Laudo_PTBR_V100 (células 1, 3, 4, 5 e 6),
# com a mesma lógica, os mesmos modelos e o mesmo pré-processamento. A única diferença é a saída:
# em vez de montar a página HTML, `analisar()` devolve um JSON com todos os dados do laudo, e o
# aplicativo monta a página com o mesmo layout, as mesmas cores e os mesmos textos do notebook.
# ==========================================================================================

import os, io, re, json, time, base64, hashlib, datetime, warnings, threading
from pathlib import Path
from zoneinfo import ZoneInfo
warnings.filterwarnings("ignore")

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage
from scipy.special import expit, logit
import matplotlib; matplotlib.use("Agg")
from matplotlib import colormaps

# ---------------- caminhos (iguais aos do notebook V800) ----------------
ROOT=Path(os.environ.get("EYEFLOW_ROOT","/content/drive/MyDrive/EyeFlow"))
PROJECT=ROOT/"glaucoma_cot_v800"
RETFOUND_CKPT=ROOT/"modelos"/"RETFound"/"RETFound_mae_natureCFP.pth"
S1=PROJECT/"stage1"; S2=PROJECT/"stage2"
POSTHOC_JSON=S1/"audits"/"stage1_posthoc_oof.json"
S1_CALIB_JSON=S1/"audits"/"stage1_calibration.json"
S1_METRICS_JSON=S1/"audits"/"stage1_metrics.json"
SELECTION_JSON=S1/"parameter_search"/"selection.json"
BEST_ADAPTER=S2/"best_adapter"
REVISION_JSON=S2/"audits"/"model_revision.json"
TOKEN_AUDIT_JSON=S2/"audits"/"token_length_audit.json"
DECISION_JSON=S2/"evaluation"/"calibrated_decision.json"
S2_CALIB_JSON=S2/"evaluation"/"stage2_calibration.json"
S2_METRICS_JSON=S2/"evaluation"/"stage2_metrics.json"

USAR_STAGE2=os.environ.get("USAR_STAGE2","1")=="1"     # 0 = servidor só com o Stage 1 (qualquer GPU)
MODO_DECISAO=os.environ.get("MODO_DECISAO","calibrada")  # "calibrada" ou "livre"
TRADUZIR_TEXTO_LIVRE=True

IMAGE_SIZE=224; EMBED_DIM=1024; TOKEN_COUNT=197; N_SIGNS=6; DISC_CROP_FRAC=0.38
QUADS=["I","S","N","T"]
RIM_NAMES=["normal","mild thinning","severe thinning"]
SIGN_NAMES=["rnfl_defect","rim_notching","vessel_bayoneting","beta_zone_atrophy","peripapillary_atrophy","disc_hemorrhage"]
SIGN_STATES=["absent","present","uncertain"]
QUAD_PT={"I":"Inferior","S":"Superior","N":"Nasal","T":"Temporal"}
SIGN_PT={"rnfl_defect":"Defeito da camada de fibras nervosas (CFNR)","rim_notching":"Entalhe (notch) da rima",
         "vessel_bayoneting":"Sinal da baioneta vascular","beta_zone_atrophy":"Atrofia peripapilar de zona beta",
         "peripapillary_atrophy":"Atrofia peripapilar","disc_hemorrhage":"Hemorragia de disco"}

readj=lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
def br(x,d=2): return f"{x:.{d}f}".replace(".",",")
def pct(x): return f"{100*x:.0f}%".replace(".",",")

# ==========================================================================================
# Funções de imagem (sem dependência de GPU)
# ==========================================================================================

def open_rgb(data):
    img=Image.open(io.BytesIO(data)); img=ImageOps.exif_transpose(img)
    return img.convert("RGB")

def locate_disc(img):
    small=img.copy(); small.thumbnail((512,512),Image.Resampling.BILINEAR)
    a=np.asarray(small,dtype=np.float32)/255.0
    fov=a.mean(2)>0.08
    fov=ndimage.binary_erosion(fov,iterations=max(2,min(small.size)//50))
    if fov.mean()<0.15: fov=np.ones(fov.shape,bool)
    lum=0.55*a[...,0]+0.45*a[...,1]
    sm=ndimage.gaussian_filter(lum,sigma=max(small.size)/45.0)
    contrast=float(sm[fov].max()-np.median(sm[fov]))
    sm=np.where(fov,sm,-1.0)
    y,x=np.unravel_index(int(np.argmax(sm)),sm.shape)
    s=img.size[0]/small.size[0]
    return float(x*s),float(y*s),contrast

def disc_crop(img,cx,cy):
    W,H=img.size; side=DISC_CROP_FRAC*min(W,H)
    x0=min(max(cx-side/2,0),W-side); y0=min(max(cy-side/2,0),H-side)
    return img.crop((int(x0),int(y0),int(x0+side),int(y0+side))),(int(x0),int(y0),int(side))

def img_b64(img,max_side=900,quality=88):
    im=img.copy(); im.thumbnail((max_side,max_side),Image.Resampling.LANCZOS)
    buf=io.BytesIO(); im.save(buf,format="JPEG",quality=quality)
    return "data:image/jpeg;base64,"+base64.b64encode(buf.getvalue()).decode()

def attention_overlay(img,att):
    """Atenção do pooling tier2a sobre os 196 patches (o token 0 é o CLS)."""
    a=np.asarray(att[1:197],float).reshape(14,14); a=(a-a.min())/max(a.max()-a.min(),1e-12)
    base=img.copy(); base.thumbnail((900,900),Image.Resampling.LANCZOS)
    heat=Image.fromarray((a*255).astype(np.uint8)).resize(base.size,Image.Resampling.BICUBIC)
    rgba=(colormaps["inferno"](np.asarray(heat)/255.0)[...,:3]*255).astype(np.uint8)
    return Image.blend(base,Image.fromarray(rgba),0.45)

def qualidade_automatica(img,ctx):
    W,H=img.size; a=np.asarray(img.resize((256,int(256*H/W))),dtype=np.float32)/255
    fov=a.mean(2)>0.08; frac=float(fov.mean()); bright=float(a[fov].mean()) if fov.any() else 0.0
    return [("Resolução",f"{W}×{H} px", min(W,H)>=512),
            ("Área de campo útil",pct(frac),frac>=0.35),
            ("Luminosidade média do campo",pct(bright),0.15<=bright<=0.75),
            ("Destaque do disco óptico (heurístico)",br(ctx["disc_contrast"],3),ctx["disc_contrast"]>=0.04)]

# ==========================================================================================
# Prompt e parser do Stage 2 (idênticos ao Módulo 29 / Módulo 40 da V800)
# ==========================================================================================

SYSTEM_PROMPT="""You are a multimodal ophthalmic reasoning model for glaucoma screening from color fundus photographs.

You receive one color fundus photograph and structured clinical evidence predicted by Stage 1. The Stage-1 evidence is predicted evidence, not ground truth and may contain errors. Integrate the image and the complete evidence pattern.

Generate exactly these six sections and no others:

Step 1 - Image Quality Assessment
Step 2 - CDR Evaluation
Step 3 - ISNT Rule Analysis
Step 4 - Glaucomatous Signs Check
Step 5 - Structural Summary
Step 6 - Final Classification

In Step 3, explicitly include one line beginning exactly:
Predicted ISNT order:

The order must contain all four letters I, S, N and T exactly once, separated by >.

In Step 4, explicitly report all six Stage-1 structural signs using only:
absent, present, uncertain.

Step 6 must begin with exactly one of the following sentences, followed by a concise clinical justification:
Glaucoma is likely.
Glaucoma is not likely.
"""
EXPECTED_PROMPT_SHA="12946b1be626ea882155f4e4cf3b6d621316280be37b5988edb9a7130b7909ac"
assert hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()==EXPECTED_PROMPT_SHA,"Prompt difere do usado no treino V800."

def fmt4(x): return f"{float(x):.4f}"
def build_user_prompt(e):
    rim=e["rim_abnormality"]; signs=e["structural_signs"]; dx=e["initial_diagnosis"]
    return f"""Analyze the attached color fundus photograph using the Stage-1 predicted evidence.

[HEAD 1 - CDR]
vertical_CDR: {fmt4(e['cdr']['vertical'])}
horizontal_CDR: {fmt4(e['cdr']['horizontal'])}

[HEAD 2 - ISNT / RIM ORDER]
predicted_order: {e['isnt_rank']['order']}
ranking_scores:
I: {fmt4(e['isnt_rank']['scores']['I'])}
S: {fmt4(e['isnt_rank']['scores']['S'])}
N: {fmt4(e['isnt_rank']['scores']['N'])}
T: {fmt4(e['isnt_rank']['scores']['T'])}

[HEAD 3 - PER-QUADRANT RIM ABNORMALITY]
Inferior: {rim['I']['class']} (confidence={fmt4(rim['I']['confidence'])})
Superior: {rim['S']['class']} (confidence={fmt4(rim['S']['confidence'])})
Nasal: {rim['N']['class']} (confidence={fmt4(rim['N']['confidence'])})
Temporal: {rim['T']['class']} (confidence={fmt4(rim['T']['confidence'])})

[HEAD 4 - GLAUCOMATOUS STRUCTURAL SIGNS]
RNFL defect: {signs['rnfl_defect']['class']} (confidence={fmt4(signs['rnfl_defect']['confidence'])})
Rim notching: {signs['rim_notching']['class']} (confidence={fmt4(signs['rim_notching']['confidence'])})
Vessel bayoneting: {signs['vessel_bayoneting']['class']} (confidence={fmt4(signs['vessel_bayoneting']['confidence'])})
Beta-zone atrophy: {signs['beta_zone_atrophy']['class']} (confidence={fmt4(signs['beta_zone_atrophy']['confidence'])})
Peripapillary atrophy: {signs['peripapillary_atrophy']['class']} (confidence={fmt4(signs['peripapillary_atrophy']['confidence'])})
Disc hemorrhage: {signs['disc_hemorrhage']['class']} (confidence={fmt4(signs['disc_hemorrhage']['confidence'])})

[HEAD 5 - INITIAL GLAUCOMA ASSESSMENT]
glaucoma_probability: {fmt4(dx['glaucoma_probability'])}
predicted_class: {dx['predicted_class']}
confidence: {fmt4(dx['confidence'])}

Generate the six-step ophthalmic reasoning report."""

FINAL_SENTENCES={1:"Glaucoma is likely.",0:"Glaucoma is not likely."}
STEP6_HEADER="Step 6 - Final Classification"

def generated_step(text,n):
    m=re.search(rf"(?is)Step\s*{n}\s*-\s*[^\n]+\n(.*?)(?=\n\s*Step\s*{n+1}\s*-|\Z)",text)
    return m.group(1).strip() if m else ""
def parse_cdr(text):
    s=generated_step(text,2) or text
    def one(prefix):
        m=re.search(prefix+r"[^0-9]{0,80}([01](?:\.\d+)?)",s,re.I)
        if m:
            v=float(m.group(1))
            if 0<=v<=1: return v
        return None
    return one(r"vertical(?:\s+cup[- ]to[- ]disc ratio|\s+CDR)?"),one(r"(?:horizontal|transverse)(?:\s+cup[- ]to[- ]disc ratio|\s+CDR)?")
WORD2Q={"inferior":"I","superior":"S","nasal":"N","temporal":"T"}
def parse_order(text):
    s=generated_step(text,3) or text
    m=re.search(r"\b([ISNT])\s*>\s*([ISNT])\s*>\s*([ISNT])\s*>\s*([ISNT])\b",s,re.I)
    if m:
        q=[x.upper() for x in m.groups()]
        if len(set(q))==4: return ">".join(q)
    m=re.search(r"(?im)^\s*Predicted ISNT order\s*:\s*([^\n.]+)",s)
    if m:
        q=re.findall(r"\b[ISNT]\b",m.group(1).upper())[:4]
        if len(set(q))==4: return ">".join(q)
    return None
def norm_rim(x):
    x=str(x).lower()
    if "severe" in x: return "severe thinning"
    if "mild" in x or "moderate" in x: return "mild thinning"
    if "normal" in x or "preserved" in x: return "normal"
    return None
def parse_rim(text):
    s=generated_step(text,3) or text; out={q:None for q in QUADS}
    for w,q in WORD2Q.items():
        m=re.search(rf"(?i)\b{w}\b\s*[-—:]\s*([^;\n.]+)",s)
        if m: out[q]=norm_rim(m.group(1))
    return out
SIGN_ALIASES={"rnfl_defect":["rnfl defect"],"rim_notching":["rim notching","notching"],
 "vessel_bayoneting":["vessel bayoneting","bayoneting"],"beta_zone_atrophy":["beta-zone atrophy","beta zone atrophy"],
 "peripapillary_atrophy":["peripapillary atrophy"],"disc_hemorrhage":["disc hemorrhage","disc haemorrhage"]}
def parse_signs(text):
    s=(generated_step(text,4) or text).lower(); out={}
    for k,al in SIGN_ALIASES.items():
        out[k]=None
        for a in al:
            m=re.search(re.escape(a)+r"\s*[-—:]\s*(absent|present|uncertain)\b",s)
            if m: out[k]=m.group(1); break
    return out
def first_decision(text):
    s=(generated_step(text,6) or text[-1500:]).lower()
    pos={1:s.find("glaucoma is likely."),0:s.find("glaucoma is not likely.")}
    found={k:v for k,v in pos.items() if v>=0}
    return min(found,key=found.get) if found else None

GLOSSARIO=("cup-to-disc ratio (CDR) = relação escavação/disco (E/D); optic disc = disco óptico; optic cup = escavação; "
           "neuroretinal rim = rima neurorretiniana; rim thinning = afinamento da rima; ISNT rule = regra ISNT; "
           "retinal nerve fiber layer (RNFL) = camada de fibras nervosas da retina (CFNR); rim notching = entalhe (notch) da rima; "
           "vessel bayoneting = sinal da baioneta vascular; peripapillary atrophy = atrofia peripapilar; "
           "beta-zone atrophy = atrofia peripapilar de zona beta; disc hemorrhage = hemorragia de disco; "
           "fundus photograph = retinografia; cupping = escavação; glaucomatous = glaucomatoso")

# ==========================================================================================
# Carregamento dos modelos (uma vez, na partida do servidor)
# ==========================================================================================

class Motor:
    """Guarda os modelos carregados. Um único lock serializa o uso da GPU."""
    def __init__(self):
        self.lock=threading.Lock(); self.stage2=False; self.info={}

    # ---------------- configuração e métricas (célula 1) ----------------
    def carregar_config(self):
        required=[RETFOUND_CKPT,POSTHOC_JSON,S1_CALIB_JSON,SELECTION_JSON]
        missing=[str(p) for p in required if not p.exists()]
        if missing: raise FileNotFoundError("Artefatos V800 ausentes:\n"+"\n".join(missing))
        self.POSTHOC=readj(POSTHOC_JSON); self.S1_CALIB=readj(S1_CALIB_JSON)
        self.VIEW_MODE=readj(SELECTION_JSON)["winner"]["view_mode"]
        self.ENSEMBLE_PATHS=[Path(p) for p in self.POSTHOC["ensemble_paths"]]
        for p in self.ENSEMBLE_PATHS:
            if not p.exists(): raise FileNotFoundError(f"Modelo Stage 1 ausente: {p}")
        self.PERF_S1={}; self.PERF_S2={}
        if S1_METRICS_JSON.exists():
            t=readj(S1_METRICS_JSON)["test"]
            self.PERF_S1={"fonte":"Stage 1 (ensemble), TEST público","n":159,"acuracia_balanceada":t["dx_balanced_accuracy"],
                  "sensibilidade":t["dx_sensitivity"],"especificidade":t["dx_specificity"],"auc":t["dx_auc"],"cdr_mae":t["cdr_mae"]}
        if S2_METRICS_JSON.exists():
            m2=readj(S2_METRICS_JSON)
            key="structured_clinical_metrics" if MODO_DECISAO=="calibrada" else "free_generation_metrics"
            c=m2.get(key,{})
            self.PERF_S2={"fonte":f"Stage 2 ({MODO_DECISAO}), TEST público","n":159,"acuracia_balanceada":c.get("balanced_accuracy"),
                  "sensibilidade":c.get("sensitivity"),"especificidade":c.get("specificity"),
                  "auc":m2.get("continuous_auc_and_calibration",{}).get("test_auc_continuous_raw"),"cdr_mae":c.get("cdr_mae")}

    # ---------------- Stage 1 (célula 3) ----------------
    def carregar_stage1(self):
        import torch, torch.nn as nn, timm
        self.torch=torch
        self.DEVICE=torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if self.DEVICE.type=="cuda":
            torch.backends.cuda.matmul.allow_tf32=True; torch.backends.cudnn.allow_tf32=True
        self.IMNET_MEAN=torch.tensor([0.485,0.456,0.406]).view(3,1,1); self.IMNET_STD=torch.tensor([0.229,0.224,0.225]).view(3,1,1)

        class Tier2aPool(nn.Module):
            def __init__(self,dim=1024,hidden=256):
                super().__init__(); self.V=nn.Linear(dim,hidden); self.w=nn.Linear(hidden,1)
            def forward(self,tokens):
                a=torch.softmax(self.w(torch.tanh(self.V(tokens))).squeeze(-1),dim=1)
                return (a.unsqueeze(-1)*tokens).sum(dim=1),a
        def linear_head(i,o): return nn.Sequential(nn.LayerNorm(i),nn.Linear(i,o))
        class GlaucomaCoTStage1(nn.Module):
            def __init__(self,dim=1024,max_blocks=2):
                super().__init__()
                self.view_emb=nn.Parameter(torch.zeros(max_blocks,dim)); self.pool=Tier2aPool(dim,256)
                self.rank_head=linear_head(dim,4); self.rim_head=linear_head(dim,12); self.cdr_head=linear_head(dim,2)
                self.sign_head=linear_head(dim,N_SIGNS*3); self.dx_head=linear_head(dim,2)
                self.log_vars=nn.Parameter(torch.zeros(5)); self.feature_dropout=nn.Dropout(0.0)
            def forward(self,tokens):
                nb=tokens.shape[1]//TOKEN_COUNT
                tokens=tokens+self.view_emb[:nb].repeat_interleave(TOKEN_COUNT,0).unsqueeze(0)
                z,a=self.pool(tokens); z=self.feature_dropout(z)
                return {"rank":self.rank_head(z),"rim":self.rim_head(z).view(-1,4,3),"cdr":torch.sigmoid(self.cdr_head(z)),
                        "signs":self.sign_head(z).view(-1,N_SIGNS,3),"dx":self.dx_head(z),"attention":a}

        enc=timm.create_model("vit_large_patch16_224",pretrained=False,num_classes=0,img_size=IMAGE_SIZE)
        ck=torch.load(RETFOUND_CKPT,map_location="cpu",weights_only=False)
        state=ck.get("model",ck.get("state_dict",ck)); out={}
        for k,v in state.items():
            nk=k
            for prefix in ("module.","model.","encoder."):
                if nk.startswith(prefix): nk=nk[len(prefix):]
            out[nk]=v
        target=enc.state_dict()
        comp={k:v for k,v in out.items() if k in target and tuple(v.shape)==tuple(target[k].shape)}
        cov=sum(v.numel() for v in comp.values())/max(sum(v.numel() for k,v in target.items() if "head" not in k),1)
        if cov<0.95: raise RuntimeError(f"Checkpoint RETFound incompatível ({cov:.1%}).")
        enc.load_state_dict(comp,strict=False)
        for p in enc.parameters(): p.requires_grad_(False)
        self.ENCODER=enc.eval().to(self.DEVICE)
        self.STAGE1_MODELS=[]
        for p in self.ENSEMBLE_PATHS:
            m=GlaucomaCoTStage1().to(self.DEVICE)
            m.load_state_dict(torch.load(p,map_location=self.DEVICE,weights_only=False)["model_state"]); self.STAGE1_MODELS.append(m.eval())
        self.RIM_BIAS=np.asarray(self.POSTHOC["rim_bias"],float); self.SIGN_BIAS=np.asarray(self.POSTHOC["sign_bias"],float)
        self.APPLIED=self.POSTHOC["applied"]; self.DX_THR=float(self.POSTHOC["dx_threshold_oof"]) if self.APPLIED.get("use_dx") else 0.5
        self.T1=float(self.S1_CALIB["temperature"])

    def pil_to_norm(self,img):
        torch=self.torch
        if img.size!=(IMAGE_SIZE,IMAGE_SIZE): img=img.resize((IMAGE_SIZE,IMAGE_SIZE),Image.Resampling.BICUBIC)
        x=torch.from_numpy(np.asarray(img,dtype=np.float32)/255.0).permute(2,0,1).contiguous()
        return (x-self.IMNET_MEAN)/self.IMNET_STD

    def retfound_tokens(self,img):
        torch=self.torch
        x=self.pil_to_norm(img).unsqueeze(0).to(self.DEVICE)
        with torch.no_grad(), torch.autocast(self.DEVICE.type,dtype=torch.bfloat16):
            f=self.ENCODER.forward_features(x)
        return f.to(torch.float16).float()     # mesmo arredondamento do cache fp16 usado no treino

    def stage1_predict(self,img):
        """Evidência canônica (mesmo schema do treino) + mapa de atenção + recorte do disco."""
        torch=self.torch
        cx,cy,contrast=locate_disc(img); crop,box=disc_crop(img,cx,cy)
        with torch.no_grad():
            x=self.retfound_tokens(img)
            if self.VIEW_MODE=="full+disc": x=torch.cat([x,self.retfound_tokens(crop)],1)
            acc={k:[] for k in ["cdr","rank","rim","sign","dx","att"]}
            for m in self.STAGE1_MODELS:
                o=m(x)
                acc["cdr"].append(o["cdr"][0].float().cpu().numpy()); acc["rank"].append(o["rank"][0].float().cpu().numpy())
                acc["rim"].append(torch.softmax(o["rim"][0].float(),-1).cpu().numpy())
                acc["sign"].append(torch.softmax(o["signs"][0].float(),-1).cpu().numpy())
                acc["dx"].append(torch.softmax(o["dx"][0].float(),-1).cpu().numpy())
                acc["att"].append(o["attention"][0,:TOKEN_COUNT].float().cpu().numpy())
        cdr,rank,rim_p,sign_p,dx_p,att=[np.mean(acc[k],0) for k in ["cdr","rank","rim","sign","dx","att"]]
        rim_c=(np.log(np.clip(rim_p,1e-8,1))+(self.RIM_BIAS if self.APPLIED.get("use_rim") else 0)).argmax(-1)
        sign_c=(np.log(np.clip(sign_p,1e-8,1))+(self.SIGN_BIAS if self.APPLIED.get("use_sign") else 0)).argmax(-1)
        dx_hat=int(dx_p[1]>=self.DX_THR)
        order=">".join(QUADS[j] for j in np.argsort(-rank))
        ev={"cdr":{"vertical":float(cdr[0]),"horizontal":float(cdr[1])},
            "isnt_rank":{"scores":{q:float(rank[j]) for j,q in enumerate(QUADS)},"order":order},
            "rim_abnormality":{q:{"class_index":int(rim_c[i]),"class":RIM_NAMES[int(rim_c[i])],
                "probabilities":{RIM_NAMES[k]:float(rim_p[i,k]) for k in range(3)},"confidence":float(rim_p[i,int(rim_c[i])])}
                for i,q in enumerate(QUADS)},
            "structural_signs":{n:{"class_index":int(sign_c[j]),"class":SIGN_STATES[int(sign_c[j])],
                "probabilities":{SIGN_STATES[k]:float(sign_p[j,k]) for k in range(3)},"confidence":float(sign_p[j,int(sign_c[j])])}
                for j,n in enumerate(SIGN_NAMES)},
            "initial_diagnosis":{"probabilities":{"not likely":float(dx_p[0]),"likely":float(dx_p[1])},
                "glaucoma_probability":float(dx_p[1]),"predicted_class":"likely" if dx_hat else "not likely",
                "confidence":float(dx_p[dx_hat]),"decision_threshold":self.DX_THR}}
        p_cal=float(expit(logit(np.clip(dx_p[1],1e-6,1-1e-6))/self.T1))
        return ev,{"attention":att,"disc_center":(cx,cy),"disc_contrast":contrast,"disc_crop":crop,"disc_box":box,
                   "glaucoma_probability_calibrated":p_cal}

    # ---------------- Stage 2 (célula 4) ----------------
    def carregar_stage2(self):
        torch=self.torch
        for p in [BEST_ADAPTER/"adapter_config.json",REVISION_JSON,DECISION_JSON,S2_CALIB_JSON]:
            if not p.exists(): raise FileNotFoundError(f"Artefato do Stage 2 ausente: {p}")
        if self.DEVICE.type!="cuda": raise RuntimeError("O Stage 2 (MedGemma-27B) exige GPU.")
        vram=torch.cuda.get_device_properties(0).total_memory/2**30
        if vram<21.5: raise RuntimeError("Menos de 22 GiB de VRAM: insuficiente para o MedGemma-27B.")
        from transformers import AutoProcessor,AutoModelForImageTextToText,BitsAndBytesConfig
        from peft import PeftModel
        HF_TOKEN=os.environ.get("HF_TOKEN")
        if not HF_TOKEN: raise RuntimeError("Defina HF_TOKEN (acesso ao google/medgemma-27b-it).")
        self.MODEL_ID="google/medgemma-27b-it"; rev=readj(REVISION_JSON)["sha"]
        self.DECISION_THRESHOLD=float(readj(DECISION_JSON)["threshold"])
        self.T2=float(readj(S2_CALIB_JSON)["temperature_selected_on_val"])
        self.MAX_NEW_TOKENS=int(readj(TOKEN_AUDIT_JSON)["summary"]["assistant_target_tokens"]["max_new_tokens"]) if TOKEN_AUDIT_JSON.exists() else 800
        self.PRECISAO="bf16" if vram>=70 else "nf4"
        self.processor=AutoProcessor.from_pretrained(self.MODEL_ID,revision=rev,token=HF_TOKEN)
        self.tok=self.processor.tokenizer
        kw=dict(revision=rev,token=HF_TOKEN,dtype=torch.bfloat16,device_map={"":0},low_cpu_mem_usage=True,attn_implementation="sdpa")
        if self.PRECISAO=="nf4":
            kw["quantization_config"]=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
        base=AutoModelForImageTextToText.from_pretrained(self.MODEL_ID,**kw)
        self.MODEL=PeftModel.from_pretrained(base,str(BEST_ADAPTER),is_trainable=False).eval()
        self.MODEL.config.use_cache=True
        if hasattr(self.MODEL.config,"text_config"): self.MODEL.config.text_config.use_cache=True
        self.INF_DEVICE=next(self.MODEL.parameters()).device
        self.stage2=True

    def generation_text(self,ev):
        msgs=[{"role":"system","content":[{"type":"text","text":SYSTEM_PROMPT}]},
              {"role":"user","content":[{"type":"image"},{"type":"text","text":build_user_prompt(ev)}]}]
        return self.processor.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)

    def prep(self,texts,img,side):
        torch=self.torch
        self.tok.padding_side=side
        b=self.processor(text=texts,images=[[img] for _ in texts],return_tensors="pt",padding=True)
        out={}
        for k,v in b.items():
            if torch.is_tensor(v):
                v=v.to(self.INF_DEVICE)
                if k=="pixel_values": v=v.to(torch.bfloat16)
            out[k]=v
        return out

    def generate_from(self,prompt_text,img,max_new):
        with self.torch.inference_mode():
            b=self.prep([prompt_text],img,"left"); L=b["input_ids"].shape[1]
            out=self.MODEL.generate(**b,max_new_tokens=max_new,do_sample=False,use_cache=True,pad_token_id=self.tok.pad_token_id)
        return self.tok.decode(out[0][L:],skip_special_tokens=True).strip()

    @staticmethod
    def prefix_before_final(report):
        m=re.search(r"(?im)^\s*Step\s*6\s*-\s*Final Classification\s*$",report)
        return (report[:m.start()] if m else report).rstrip()+"\n\n"+STEP6_HEADER+"\n"

    def stage2_margin(self,ev,img,report):
        """mean logP('Glaucoma is likely.') − mean logP('Glaucoma is not likely.') após os Passos 1–5 gerados."""
        torch=self.torch
        with torch.inference_mode():
            pre=self.generation_text(ev)+self.prefix_before_final(report)
            self.tok.padding_side="right"
            P=int(self.processor(text=pre,images=img,return_tensors="pt",padding=False)["input_ids"].shape[1])
            b=self.prep([pre+FINAL_SENTENCES[1],pre+FINAL_SENTENCES[0]],img,"right")
            lens=b["attention_mask"].sum(1).tolist(); Lmax=b["input_ids"].shape[1]
            logits=self.MODEL(**b,use_cache=False,logits_to_keep=Lmax-P+1).logits; off=Lmax-logits.shape[1]
            lp=[]
            for i in range(2):
                Li=int(lens[i]); ids=b["input_ids"][i,P:Li]
                l=torch.log_softmax(logits[i,P-1-off:Li-1-off].float(),-1)
                lp.append(float(l.gather(-1,ids.unsqueeze(-1)).mean()))
        return lp[0]-lp[1]

    def stage2_report(self,ev,img,etapa):
        t=time.perf_counter()
        etapa("Stage 2 · gerando o raciocínio em 6 passos (MedGemma-27B)")
        free=self.generate_from(self.generation_text(ev),img,self.MAX_NEW_TOKENS)
        etapa("Stage 2 · calculando a decisão calibrada")
        margin=self.stage2_margin(ev,img,free)
        dx_free=first_decision(free); dx_cal=int(margin>=self.DECISION_THRESHOLD)
        report=free; regenerated=False
        if MODO_DECISAO=="calibrada" and dx_cal!=dx_free:
            etapa("Stage 2 · ajustando a conclusão do Passo 6")
            pre=self.prefix_before_final(free)+FINAL_SENTENCES[dx_cal]
            cont=self.generate_from(self.generation_text(ev)+pre,img,256)
            report=(pre+(" " if cont and not cont.startswith((" ","\n")) else "")+cont).strip(); regenerated=True
        dx=dx_cal if MODO_DECISAO=="calibrada" else dx_free
        return {"report_en":report,"report_free_en":free,"margin":margin,"dx_free":dx_free,"dx_calibrated":dx_cal,
                "dx":dx,"step6_regenerated":regenerated,"probability":float(expit((margin-self.DECISION_THRESHOLD)/self.T2)),
                "seconds":time.perf_counter()-t}

    def traduzir_ptbr(self,texto):
        if not texto.strip(): return ""
        msgs=[{"role":"system","content":[{"type":"text","text":"Você é um tradutor médico especializado em oftalmologia, com português do Brasil nativo."}]},
              {"role":"user","content":[{"type":"text","text":
                "Traduza para o português do Brasil o trecho abaixo de um relatório de retinografia.\n"
                "Regras: preserve todos os valores numéricos, usando vírgula como separador decimal; use a terminologia "
                f"oftalmológica brasileira deste glossário: {GLOSSARIO}. Não acrescente nem remova informações. "
                "Responda somente com a tradução.\n\nTrecho:\n"+texto}]}]
        with self.torch.inference_mode():
            self.tok.padding_side="left"
            b=self.processor.apply_chat_template(msgs,tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt")
            b={k:v.to(self.INF_DEVICE) for k,v in b.items() if self.torch.is_tensor(v)}; L=b["input_ids"].shape[1]
            with self.MODEL.disable_adapter():
                out=self.MODEL.generate(**b,max_new_tokens=min(700,int(len(texto)/2.5)+64),do_sample=False,use_cache=True,
                                        pad_token_id=self.tok.pad_token_id)
        return self.tok.decode(out[0][L:],skip_special_tokens=True).strip()

    # ---------------- partida ----------------
    def carregar(self):
        t0=time.perf_counter()
        self.carregar_config(); self.carregar_stage1()
        print(f"[OK] Stage 1 pronto: RETFound + {len(self.STAGE1_MODELS)} heads ({self.DEVICE.type})")
        if USAR_STAGE2:
            self.carregar_stage2()
            print(f"[OK] MedGemma-27B ({self.PRECISAO}) + adapter V800 carregados")
        self.info={"stage2":self.stage2,"modo_decisao":MODO_DECISAO,"perf_stage1":self.PERF_S1,"perf_stage2":self.PERF_S2,
                   "dispositivo":self.DEVICE.type,"carregado_em_s":round(time.perf_counter()-t0,1)}
        return self

    # ==========================================================================================
    # Pipeline completo (célula 6): imagem → Stage 1 → Stage 2 → tradução → dados do laudo
    # ==========================================================================================
    def analisar(self,dados,nome="retinografia.jpg",paciente=None,olho=None,completo=True,etapa=lambda s:None):
        t0=time.perf_counter()
        usar_s2=bool(completo and self.stage2)
        img=open_rgb(dados)
        with self.lock:
            etapa("Stage 1 · RETFound: evidências estruturais")
            ev,ctx=self.stage1_predict(img)
            s1_dx=1 if ev["initial_diagnosis"]["predicted_class"]=="likely" else 0
            R={"ev":ev,"paciente":paciente,"arquivo":Path(nome).name,
               "s1_prob_cal":ctx["glaucoma_probability_calibrated"],"parse_falhas":[]}
            # Valores apresentados = os que o relatório afirma; o Stage 1 só completa itens ausentes (sinalizado).
            R["cdr_v"],R["cdr_h"]=ev["cdr"]["vertical"],ev["cdr"]["horizontal"]
            R["ordem"]=ev["isnt_rank"]["order"]
            R["rim"]={q:ev["rim_abnormality"][q]["class"] for q in QUADS}
            R["signs"]={k:ev["structural_signs"][k]["class"] for k in SIGN_NAMES}
            if usar_s2:
                s2=self.stage2_report(ev,img,etapa); rep=s2["report_en"]; R["s2"]=s2
                v,h=parse_cdr(rep); o=parse_order(rep); rm=parse_rim(rep); sg=parse_signs(rep)
                if v is not None: R["cdr_v"]=v
                else: R["parse_falhas"].append("CDR vertical")
                if h is not None: R["cdr_h"]=h
                else: R["parse_falhas"].append("CDR horizontal")
                if o: R["ordem"]=o
                else: R["parse_falhas"].append("ordem ISNT")
                for q in QUADS:
                    if rm[q]: R["rim"][q]=rm[q]
                    else: R["parse_falhas"].append(f"rima {QUAD_PT[q].lower()}")
                for k in SIGN_NAMES:
                    if sg[k]: R["signs"][k]=sg[k]
                    else: R["parse_falhas"].append(SIGN_PT[k].lower())
                R["dx"]=s2["dx"] if s2["dx"] is not None else s1_dx
                R["prob"]=s2["probability"] if MODO_DECISAO=="calibrada" else float(expit(s2["margin"]/self.T2))
                R["discordante"]=R["dx"]!=s1_dx
                R["modo"]=(f"Stage 2 com limiar calibrado em VAL (margem {br(s2['margin'],3)}; limiar {br(self.DECISION_THRESHOLD,3)})"
                           +("; conclusão do Passo 6 regenerada a partir da decisão calibrada" if s2["step6_regenerated"] else "")
                           if MODO_DECISAO=="calibrada" else "conclusão gerada livremente pelo Stage 2")
                p1=generated_step(rep,1)
                p6=re.sub(r"(?i)^\s*glaucoma is (not )?likely\.\s*","",generated_step(rep,6))
                if TRADUZIR_TEXTO_LIVRE:
                    etapa("Tradução para o português do Brasil")
                    R["passo1_pt"]=self.traduzir_ptbr(p1); R["passo6_pt"]=self.traduzir_ptbr(p6)
                else:
                    R["passo1_pt"]=p1; R["passo6_pt"]=p6
            else:
                R["s2"]=None; R["dx"]=s1_dx; R["prob"]=ctx["glaucoma_probability_calibrated"]; R["discordante"]=False
                R["modo"]="somente Stage 1 (ensemble RETFound)"; R["passo6_pt"]="Conclusão baseada apenas no classificador estrutural do Stage 1."
            etapa("Montando o laudo")
            W=img.size[0]; nasal_dir=ctx["disc_center"][0]>W/2
            if olho: R["olho"]=olho; R["nasal_direita"]=(olho.upper().startswith("OD"))
            else: R["olho"]=("OD" if nasal_dir else "OE")+" (estimado pela posição do disco)"; R["nasal_direita"]=nasal_dir
            R["exam_id"]=hashlib.sha256(dados).hexdigest()[:10].upper()
            R["data"]=datetime.datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")
            R["qualidade"]=[list(q) for q in qualidade_automatica(img,ctx)]
            R["imagens"]={"original":img_b64(img),"atencao":img_b64(attention_overlay(img,ctx["attention"])),
                          "disco":img_b64(ctx["disc_crop"],600)}
        R["metodo"]="RETFound + MedGemma-27B (V800)" if R["s2"] else "RETFound (V800, Stage 1)"
        R["perf"]=(self.PERF_S2 or self.PERF_S1) if R["s2"] else self.PERF_S1
        if R["s2"]:
            R["report_en"]=R["s2"]["report_en"]
            R["s2"]={k:v for k,v in R["s2"].items() if k not in ("report_en","report_free_en")}
        R["segundos"]=time.perf_counter()-t0
        return R
