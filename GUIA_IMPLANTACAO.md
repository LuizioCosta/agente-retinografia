# Agente de Retinografia: guia de implantação passo a passo

Este guia leva você do zero até o aplicativo **Agente de Retinografia** instalado no seu celular, gerando o mesmo laudo preliminar de glaucoma do notebook *EyeFlow V800*. Não é preciso saber programar: você vai clicar em botões no GitHub e no Google Colab.

---

## 1. Como o aplicativo funciona

```
 ┌─────────────── CELULAR ───────────────┐            ┌──────────── SERVIDOR (GPU) ────────────┐
 │  Agente de Retinografia (≈ 1 MB)       │  imagem →  │  Google Colab A100 + seu Google Drive  │
 │  • câmera / galeria                    │  (https)   │  • Stage 1: RETFound + ensemble de 3    │
 │  • envia a retinografia                │            │  • Stage 2: MedGemma-27B + LoRA V800    │
 │  • monta o laudo com o layout do       │  ← dados   │  • decisão calibrada e tradução PT-BR   │
 │    notebook (cores, gráficos, textos)  │  do laudo  │  • os mesmos modelos do notebook        │
 │  • histórico salvo só no aparelho      │            │                                         │
 └────────────────────────────────────────┘            └─────────────────────────────────────────┘
```

**Por que o celular não roda os modelos sozinho?** O MedGemma-27B ocupa cerca de 52 GB de memória de GPU (veja a célula 4 do seu notebook), e nenhum celular tem isso. Para manter **a mesma qualidade** do notebook, os modelos ficam no servidor. Assim o aplicativo fica **leve** (cerca de 1 MB na versão web e poucos MB no APK) e **rápido**: ele abre na hora e só envia a imagem.

| Modo (escolhido no app) | O que roda | Tempo por exame |
|---|---|---|
| **Completa** (padrão) | Stage 1 + Stage 2 + tradução, idêntico ao notebook com `USAR_STAGE2=True` | 1 a 2 min (o notebook mediu 106 s) |
| **Rápida** | só o Stage 1, idêntico ao notebook com `USAR_STAGE2=False` | poucos segundos |

---

## 2. O que você precisa

- Uma conta Google com o **Google Drive** onde já estão `MyDrive/EyeFlow/glaucoma_cot_v800` e `MyDrive/EyeFlow/modelos/RETFound`, os mesmos arquivos que o notebook V800 usa.
- **Google Colab com A100**, o mesmo ambiente do notebook. Na prática, isso exige Colab Pro ou Pro+.
- O segredo **`HF_TOKEN`** no Colab, o mesmo do notebook V800, com acesso ao `google/medgemma-27b-it`.
- Uma conta gratuita no **GitHub** (github.com). É lá que o aplicativo é construído e publicado.
- Um celular **Android** (para o APK ou o app web) ou um **iPhone** (só o app web).

---

## 3. Passo a passo

### Passo 1: colocar o projeto no GitHub (cerca de 5 min)

1. Entre em **github.com**, clique em **New repository** e use o nome `agente-retinografia`.
   - Escolha **Public**, porque o GitHub Pages gratuito exige repositório público. Os modelos e os dados de pacientes **não** vão para o GitHub, só o código do app.
   - Clique em **Create repository**.
2. Na página do repositório, clique em **uploading an existing file**.
3. Descompacte o `agente-retinografia.zip` no computador e **arraste todo o conteúdo da pasta** para a página, incluindo a pasta `.github`.
   > Se o seu sistema esconder a pasta `.github` por começar com ponto, use a alternativa por terminal: `git init && git add . && git commit -m "Agente de Retinografia" && git branch -M main && git remote add origin https://github.com/SEU-USUARIO/agente-retinografia.git && git push -u origin main`
4. Clique em **Commit changes**.

### Passo 2: publicar o app web (PWA) (cerca de 3 min)

1. No repositório, abra **Settings → Pages**.
2. Em **Source**, escolha **GitHub Actions**.
3. Abra a aba **Actions**, clique em **Publicar app web (PWA)** e depois em **Run workflow**, se ele não tiver começado sozinho.
4. Quando o círculo ficar verde ✅, o app estará em:
   **`https://SEU-USUARIO.github.io/agente-retinografia/`**

### Passo 3: gerar o APK Android (cerca de 8 min, automático)

1. Na aba **Actions**, abra **Gerar APK Android**. Ele roda sozinho depois do Passo 1; se não rodar, clique em **Run workflow**.
2. Quando terminar ✅, abra a página inicial do repositório. À direita aparece **Releases** com o arquivo **`Agente-de-Retinografia.apk`**.

> O GitHub compila o aplicativo nos computadores dele. Você **não** precisa instalar Android Studio.

### Passo 4: ligar o servidor no Colab (cerca de 5 min por sessão)

1. Copie a pasta descompactada `agente-retinografia` para o Drive em **`MyDrive/EyeFlow/agente-retinografia`**.
   Como alternativa, deixe a pasta fora do Drive e preencha `REPO_GIT` na célula 1 com o endereço do seu repositório.
2. No Drive, abra **`agente-retinografia/servidor/Iniciar_Servidor_Colab.ipynb`** com o Google Colab.
3. Vá em **Ambiente de execução → Alterar o tipo de ambiente → A100 GPU**.
4. Confirme que o segredo `HF_TOKEN` existe (ícone 🔑 na barra lateral) e está liberado para este notebook.
5. *(Opcional)* Na célula 4, preencha `APP_WEB = "https://SEU-USUARIO.github.io/agente-retinografia/"`.
6. Clique em **Ambiente de execução → Executar tudo** e autorize o acesso ao Drive.
7. Espere de 3 a 4 minutos. A célula 3 mostra `[OK] Modelos carregados`. A célula 4 mostra:
   - **ENDEREÇO DO SERVIDOR**, por exemplo `https://palavras-aleatorias.trycloudflare.com`
   - **CHAVE DE ACESSO**, que impede que estranhos usem o seu servidor
   - um **QR code**
8. **Deixe a aba do Colab aberta** enquanto usa o app. A célula 5 mostra o registro dos exames.

### Passo 5: instalar o app no celular

**Android, opção A: APK (app "de verdade")**
1. No celular, abra o repositório no navegador, vá em **Releases** e toque em `Agente-de-Retinografia.apk`.
2. Toque no arquivo baixado. O Android pede para **permitir a instalação de fontes desconhecidas** para o navegador: autorize.
3. Abra **Agente de Retinografia**, vá em **Ajustes**, digite o **endereço** e a **chave** do Passo 4 e toque em **Testar conexão**.
   > Se o Play Protect avisar "app não verificado", toque em **Instalar assim mesmo**. Isso é normal em apps instalados fora da Play Store.

**Android ou iPhone, opção B: app web instalável**
1. Aponte a câmera do celular para o **QR code** do Colab. O app abre já configurado com o endereço e a chave.
2. Instale na tela inicial:
   - **Android (Chrome):** menu ⋮ → **Instalar app** ou **Adicionar à tela inicial**.
   - **iPhone (Safari):** botão **Compartilhar** → **Adicionar à Tela de Início**.

### Passo 6: primeiro exame

1. Toque em **Nova análise** e escolha **📷 Câmera** ou **🖼️ Galeria / arquivos**.
2. *(Opcional)* Preencha o paciente (iniciais ou prontuário) e o olho (OD ou OE). Sem o olho, ele é estimado pela posição do disco, como no notebook.
3. Escolha **Completa** ou **Rápida** e toque em **Gerar laudo preliminar**.
4. A tela de progresso mostra cada etapa: Stage 1 → Stage 2 → Tradução → Montagem.
5. O laudo aparece com o mesmo layout do notebook: impressão diagnóstica, escore, as três imagens (original, mapa de atenção e disco), qualidade, relação E/D, esquema do disco, ISNT, sinais, síntese, conclusão, conduta e rodapé com o desempenho medido.
6. Use **Compartilhar** para enviar o laudo (arquivo HTML autônomo) por WhatsApp ou e-mail, ou **PDF / Imprimir** no app web. Os laudos ficam no **Histórico** do aparelho.

**Teste de equivalência:** envie a mesma `paciente001_OD.jpg` que você usou no notebook. Os números (E/D 0,30 e 0,34, escore 3%, Stage 1 1%) devem coincidir. O botão **"Ver um laudo de exemplo"** mostra esse laudo como o notebook o gerou.

---

## 4. Uso no dia a dia

| Situação | O que fazer |
|---|---|
| Começar a usar em um novo dia | Execute o notebook do servidor (Passo 4). O endereço muda a cada sessão: escaneie o novo QR code ou atualize **Ajustes** no APK. |
| Bolinha vermelha "servidor offline" | O Colab desconectou ou foi fechado. Execute o notebook de novo. |
| Bolinha amarela "carregando modelos" | Espere cerca de 3 min (o MedGemma-27B está carregando). |
| "Chave de acesso inválida" | Copie de novo a chave mostrada na célula 4. |
| Só aparece a análise "Rápida" | O servidor foi ligado com `USAR_STAGE2 = False` ou sem A100. |
| Erro de memória (CUDA out of memory) | Use A100 80 GB. Com menos memória, o MedGemma carrega em NF4, como no notebook. |

---

## 5. Servidor permanente (opcional, para uso contínuo)

O Colab é ótimo para começar, mas desliga por inatividade e troca de endereço. Para ter um servidor 24 h com endereço fixo:

1. **Máquina com GPU na nuvem** (Google Cloud, AWS, RunPod, Lambda etc.): A100 80 GB para o modo completo, ou uma L4 / T4 só para o modo rápido.
2. Copie a pasta `EyeFlow` (modelos) para a máquina e rode:
   ```bash
   pip install torch -r servidor/requirements.txt
   export EYEFLOW_ROOT=/caminho/EyeFlow HF_TOKEN=hf_xxx AGENTE_CHAVE=uma-chave-forte
   cd servidor && uvicorn app:app --host 0.0.0.0 --port 8000
   ```
3. Use um **Cloudflare Tunnel com nome** (domínio fixo, ex.: `https://retino.seudominio.com.br`) ou um proxy HTTPS. Configure esse endereço uma única vez no app.

Para testar o app sem GPU: `AGENTE_DEMO=1 uvicorn app:app` responde sempre com o laudo de exemplo.

---

## 6. Segurança, privacidade e aspectos regulatórios

- **Imagens:** o servidor não grava nada em disco. Tudo fica na memória e o resultado é apagado após 1 hora. O histórico fica só no celular (IndexedDB) e pode ser apagado em **Ajustes**.
- **Acesso:** o servidor só aceita pedidos com a **chave de acesso** e só é acessível por **https**.
- **LGPD:** prefira iniciais ou número de prontuário no campo "Paciente", nunca o nome completo.
- O APK gerado é de **depuração** (uso próprio). Para publicar na Google Play, crie uma chave de assinatura e uma conta de desenvolvedor (US$ 25).
- **Aviso clínico:** ferramenta de pesquisa, sem validação clínica nem registro na ANVISA. O laudo é **preliminar**, precisa ser revisado por médico oftalmologista e não substitui exame clínico, tonometria, gonioscopia, OCT nem campimetria.

---

## 7. Estrutura do projeto

```
agente-retinografia/
├── GUIA_IMPLANTACAO.md              ← este guia
├── servidor/
│   ├── Iniciar_Servidor_Colab.ipynb ← liga o servidor no Colab (Passo 4)
│   ├── eyeflow_pipeline.py          ← células 1, 3, 4 e 6 do notebook V800 (mesma lógica)
│   ├── app.py                       ← API: /api/analisar, /api/trabalhos/{id}, /api/saude
│   └── requirements.txt             ← mesmas versões do V800
├── app/
│   ├── www/                         ← o aplicativo (HTML/CSS/JS, sem frameworks)
│   │   ├── js/laudo.js              ← célula 5 do notebook (laudo idêntico)
│   │   ├── js/app.js                ← telas, envio, progresso, histórico, compartilhar
│   │   └── demo/exemplo.json        ← laudo real do notebook (paciente001_OD.jpg)
│   ├── capacitor.config.json        ← empacotamento Android (Capacitor)
│   └── package.json
└── .github/workflows/
    ├── android-apk.yml              ← gera o APK automaticamente
    └── pages.yml                    ← publica o app web
```
