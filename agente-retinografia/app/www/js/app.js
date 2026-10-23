// ==========================================================================================
// Agente de Retinografia — lógica do aplicativo
// Fluxo: imagem → POST /api/analisar → consulta /api/trabalhos/{id} → laudo (laudo.js) → histórico
// ==========================================================================================
(function () {
  const $ = (s) => document.querySelector(s);
  const NATIVO = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
  const PADRAO = { url: "", chave: "", inst: "EyeFlow — Pesquisa em oftalmologia assistida por IA", orig: true };

  // ---------------- preferências (localStorage pode falhar: modo privado etc.) ----------------
  function lerCfg() {
    let c = {};
    try { c = JSON.parse(localStorage.getItem("ag-cfg") || "{}"); } catch (e) {}
    // Quando o app é aberto pelo próprio servidor (http(s)://…/), usa esse endereço por padrão.
    if (!c.url && /^https?:$/.test(location.protocol) && !/github\.io$/.test(location.hostname) && !NATIVO) c.url = location.origin;
    return Object.assign({}, PADRAO, c);
  }
  function salvarCfg(c) { try { localStorage.setItem("ag-cfg", JSON.stringify(c)); } catch (e) {} }
  let cfg = lerCfg();
  // Link de configuração gerado pelo notebook do servidor: …/?servidor=https://…&chave=…
  const qs = new URLSearchParams(location.search);
  if (qs.get("servidor")) {
    cfg.url = qs.get("servidor"); if (qs.get("chave")) cfg.chave = qs.get("chave");
    salvarCfg(cfg); history.replaceState(null, "", location.pathname);
  }
  const base = () => cfg.url.replace(/\/+$/, "");
  const cab = () => (cfg.chave ? { "X-Chave": cfg.chave } : {});

  // ---------------- histórico (IndexedDB, só no aparelho) ----------------
  const DB = {
    abrir() {
      return new Promise((ok, erro) => {
        try {
          const r = indexedDB.open("agente-retinografia", 1);
          r.onupgradeneeded = () => r.result.createObjectStore("laudos", { keyPath: "chave" });
          r.onsuccess = () => ok(r.result); r.onerror = () => erro(r.error);
        } catch (e) { erro(e); }
      });
    },
    async op(modo, fn) {
      const db = await this.abrir();
      return new Promise((ok, erro) => {
        const tx = db.transaction("laudos", modo), st = tx.objectStore("laudos"), r = fn(st);
        tx.oncomplete = () => ok(r && r.result); tx.onerror = () => erro(tx.error);
      });
    },
    todos() { return this.op("readonly", (s) => s.getAll()).catch(() => []); },
    salvar(item) { return this.op("readwrite", (s) => s.put(item)).catch(() => null); },
    apagar(chave) { return this.op("readwrite", (s) => s.delete(chave)).catch(() => null); },
    limpar() { return this.op("readwrite", (s) => s.clear()).catch(() => null); },
  };

  // ---------------- utilidades de interface ----------------
  let toastT;
  function toast(msg, ms = 3200) {
    const t = $("#toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(() => (t.hidden = true), ms);
  }
  function mostrar(id) {
    document.querySelectorAll(".ag-view").forEach((v) => (v.hidden = v.id !== id));
    const aba = id === "v-prog" || id === "v-laudo" ? (vindoDe || "v-nova") : id;
    document.querySelectorAll(".ag-nav button").forEach((b) => {
      if (b.dataset.v === aba) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    window.scrollTo(0, 0);
  }
  let vindoDe = "v-nova";
  function segmentado(el, aoMudar) {
    el.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b || b.disabled) return;
      el.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
      aoMudar && aoMudar(b.dataset.v);
    });
    return () => el.querySelector('[aria-pressed="true"]').dataset.v;
  }
  const olhoSel = segmentado($("#olho"));
  const modoSel = segmentado($("#modo"));

  // ---------------- estado do servidor ----------------
  let stage2Disponivel = true;
  async function verificar(silencioso = true) {
    const st = $("#status"), txt = st.querySelector("span");
    st.className = "ag-status";
    if (!cfg.url) { txt.textContent = "configure o servidor"; st.classList.add("off"); return null; }
    txt.textContent = "conectando…"; st.classList.add("load");
    try {
      const r = await fetch(base() + "/api/saude", { headers: cab(), cache: "no-store" });
      if (r.status === 401) throw new Error("chave de acesso inválida");
      const j = await r.json();
      st.className = "ag-status " + (j.pronto ? "ok" : j.erro ? "off" : "load");
      txt.textContent = j.pronto ? (j.demo ? "servidor demo" : j.stage2 ? "pronto · completo" : "pronto · rápido") : j.erro ? "erro nos modelos" : "carregando modelos";
      if (j.pronto) {
        stage2Disponivel = !!j.stage2;
        const bC = $('#modo [data-v="completo"]');
        bC.disabled = !stage2Disponivel;
        if (!stage2Disponivel) $('#modo [data-v="rapido"]').click();
      } else if (!j.erro) setTimeout(verificar, 15000);
      if (!silencioso) toast(j.mensagem || (j.pronto ? "Servidor pronto." : "Servidor indisponível."));
      return j;
    } catch (e) {
      st.className = "ag-status off"; txt.textContent = "servidor offline";
      if (!silencioso) toast("Sem conexão: " + e.message);
      return null;
    }
  }
  $("#status").addEventListener("click", () => verificar(false));

  // ---------------- escolha da imagem ----------------
  let arquivo = null, urlPrev = null;
  function escolher(f) {
    if (!f) return;
    if (f.size > 25 * 1024 * 1024) return toast("Imagem maior que 25 MB.");
    arquivo = f;
    if (urlPrev) URL.revokeObjectURL(urlPrev);
    urlPrev = URL.createObjectURL(f);
    const img = $("#preview");
    img.onload = () => ($("#img-info").textContent = `${f.name || "foto"} · ${img.naturalWidth}×${img.naturalHeight} px · ${(f.size / 1048576).toFixed(1).replace(".", ",")} MB` +
      (Math.min(img.naturalWidth, img.naturalHeight) < 512 ? " · resolução abaixo de 512 px" : ""));
    img.onerror = () => ($("#img-info").textContent = `${f.name} · ${(f.size / 1048576).toFixed(1).replace(".", ",")} MB (pré-visualização indisponível para este formato)`);
    img.src = urlPrev; img.hidden = false; $("#drop-empty").hidden = true;
    $("#btn-gerar").disabled = false;
  }
  ["#in-camera", "#in-galeria"].forEach((s) => $(s).addEventListener("change", (e) => { escolher(e.target.files[0]); e.target.value = ""; }));
  const drop = $("#drop");
  drop.addEventListener("dragover", (e) => e.preventDefault());
  drop.addEventListener("drop", (e) => { e.preventDefault(); escolher(e.dataTransfer.files[0]); });

  // ---------------- análise ----------------
  let cancelado = false, relogio = null;
  function progresso(etapa, s2) {
    $("#prog-etapa").textContent = etapa || "";
    const itens = [...document.querySelectorAll("#prog-passos li")];
    itens.forEach((li) => li.classList.toggle("off", li.classList.contains("s2") && !s2));
    const idx = itens.findIndex((li) => etapa && etapa.startsWith(li.dataset.k));
    if (idx < 0) return;
    itens.forEach((li, i) => { li.classList.toggle("ok", i < idx); li.classList.toggle("on", i === idx); });
  }
  async function gerar() {
    if (!arquivo) return;
    if (!cfg.url) { toast("Informe o endereço do servidor em Ajustes."); vindoDe = "v-ajustes"; return mostrar("v-ajustes"); }
    const completo = modoSel() === "completo" && stage2Disponivel;
    cancelado = false; vindoDe = "v-nova"; mostrar("v-prog"); progresso("Envio da imagem", completo);
    $("#prog-titulo").textContent = completo ? "Análise completa em andamento…" : "Análise rápida em andamento…";
    const t0 = Date.now();
    relogio = setInterval(() => {
      const s = Math.round((Date.now() - t0) / 1000);
      $("#prog-tempo").textContent = s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
    }, 500);
    try {
      const fd = new FormData();
      fd.append("imagem", arquivo, arquivo.name || "retinografia.jpg");
      fd.append("paciente", $("#paciente").value.trim());
      fd.append("olho", olhoSel());
      fd.append("modo", completo ? "completo" : "rapido");
      const r = await fetch(base() + "/api/analisar", { method: "POST", body: fd, headers: cab() });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || `erro ${r.status}`);
      let falhas = 0;
      while (!cancelado) {
        await new Promise((ok) => setTimeout(ok, 2000));
        let s;
        try {
          const rr = await fetch(base() + "/api/trabalhos/" + j.id, { headers: cab(), cache: "no-store" });
          s = await rr.json(); if (!rr.ok) throw new Error(s.detail || `erro ${rr.status}`);
          falhas = 0;
        } catch (e) { if (++falhas > 5) throw e; continue; }   // tolera quedas curtas de rede
        if (s.estado === "erro") throw new Error(s.erro);
        if (s.estado === "concluido") { await concluir(s.resultado); return; }
        progresso(s.estado === "na fila" ? "Aguardando a GPU (fila)" : s.etapa, completo);
      }
    } catch (e) {
      if (!cancelado) { mostrar("v-nova"); toast("Não foi possível gerar o laudo: " + e.message, 6000); }
    } finally { clearInterval(relogio); }
  }
  $("#btn-gerar").addEventListener("click", gerar);
  $("#btn-cancelar").addEventListener("click", () => { cancelado = true; clearInterval(relogio); mostrar("v-nova"); });

  async function concluir(R) {
    await DB.salvar({ chave: R.exam_id + "-" + Date.now(), quando: Date.now(), R });
    const todos = (await DB.todos()).sort((a, b) => b.quando - a.quando);
    for (const x of todos.slice(50)) await DB.apagar(x.chave);
    abrirLaudo(R);
  }

  // ---------------- exibição, compartilhamento e PDF ----------------
  let atual = null;
  function abrirLaudo(R) {
    atual = R;
    $("#laudo").innerHTML = Laudo.renderLaudo(R, { instituicao: cfg.inst, mostrarOriginal: cfg.orig });
    $("#faixa-exemplo").hidden = !R.exemplo;
    mostrar("v-laudo");
  }
  $("#btn-voltar").addEventListener("click", () => { mostrar(vindoDe); if (vindoDe === "v-hist") listar(); });
  $("#btn-print").hidden = NATIVO;   // o WebView do Android não imprime; no app nativo use Compartilhar
  $("#btn-print").addEventListener("click", () => window.print());
  $("#btn-share").addEventListener("click", async () => {
    if (!atual) return;
    const html = Laudo.documentoCompleto(atual, { instituicao: cfg.inst, mostrarOriginal: cfg.orig });
    const nome = `laudo_${(atual.arquivo || "exame").replace(/\.[^.]+$/, "")}_${atual.exam_id}.html`;
    try {
      if (NATIVO) {
        const { Filesystem, Share } = window.Capacitor.Plugins;
        const b64 = btoa(unescape(encodeURIComponent(html)));
        const w = await Filesystem.writeFile({ path: nome, data: b64, directory: "CACHE" });
        await Share.share({ title: "Laudo preliminar de retinografia", files: [w.uri], dialogTitle: "Compartilhar laudo" });
        return;
      }
      const file = new File([html], nome, { type: "text/html" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: "Laudo preliminar de retinografia" });
        return;
      }
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([html], { type: "text/html" })); a.download = nome;
      document.body.appendChild(a); a.click(); a.remove();
      toast("Laudo salvo em Downloads (abre em qualquer navegador).");
    } catch (e) { if (e && e.name !== "AbortError") toast("Não foi possível compartilhar: " + (e.message || e)); }
  });

  $("#btn-exemplo").addEventListener("click", async () => {
    try {
      const r = await fetch("demo/exemplo.json"); vindoDe = "v-nova"; abrirLaudo(await r.json());
    } catch (e) { toast("Exemplo indisponível."); }
  });

  // ---------------- histórico ----------------
  async function listar() {
    const ul = $("#lista"), itens = (await DB.todos()).sort((a, b) => b.quando - a.quando);
    if (!itens.length) { ul.innerHTML = '<li class="ag-vazio">Nenhum laudo ainda.</li>'; return; }
    ul.innerHTML = itens.map((x) => {
      const R = x.R, pos = R.dx === 1;
      return `<li data-k="${Laudo.esc(x.chave)}"><img src="${R.imagens.disco}" alt=""><div class="t">` +
        `<b><span class="ag-chip" style="background:${pos ? "#d1495b" : "#2e9d6b"}">${pos ? "Provável" : "Improvável"}</span>${Laudo.esc(R.paciente || "Paciente não informado")}</b>` +
        `<small>${Laudo.esc(R.data)} · ${Laudo.esc(R.olho)} · ${Laudo.esc(R.arquivo)}</small></div>` +
        `<button class="ag-del" type="button" aria-label="Apagar">×</button></li>`;
    }).join("");
    ul.onclick = async (e) => {
      const li = e.target.closest("li[data-k]"); if (!li) return;
      const item = itens.find((x) => x.chave === li.dataset.k);
      if (e.target.closest(".ag-del")) {
        if (confirm("Apagar este laudo do aparelho?")) { await DB.apagar(item.chave); listar(); }
      } else { vindoDe = "v-hist"; abrirLaudo(item.R); }
    };
  }

  // ---------------- ajustes ----------------
  function preencherAjustes() {
    $("#cfg-url").value = cfg.url; $("#cfg-chave").value = cfg.chave; $("#cfg-inst").value = cfg.inst; $("#cfg-orig").checked = cfg.orig;
  }
  function lerAjustes() {
    let url = $("#cfg-url").value.trim();
    if (url && !/^https?:\/\//i.test(url)) url = "https://" + url;
    cfg = { url, chave: $("#cfg-chave").value.trim(), inst: $("#cfg-inst").value.trim() || PADRAO.inst, orig: $("#cfg-orig").checked };
    salvarCfg(cfg);
  }
  $("#btn-salvar").addEventListener("click", async () => { lerAjustes(); toast("Ajustes salvos."); await verificar(); });
  $("#btn-testar").addEventListener("click", async () => {
    lerAjustes(); $("#cfg-msg").textContent = "Testando…";
    const j = await verificar();
    $("#cfg-msg").textContent = !j ? "Sem resposta do servidor. Confira o endereço, a chave e se o notebook do servidor está rodando."
      : j.pronto ? (j.demo ? "Conectado ao servidor de demonstração." : `Conectado. Stage 2 ${j.stage2 ? "disponível" : "indisponível (só análise rápida)"} · ${j.dispositivo || ""}.`)
      : (j.erro ? "Servidor respondeu com erro: " + j.erro : j.mensagem);
  });
  $("#btn-limpar").addEventListener("click", async () => { if (confirm("Apagar todos os laudos salvos neste aparelho?")) { await DB.limpar(); toast("Histórico apagado."); } });

  // ---------------- navegação ----------------
  document.querySelectorAll(".ag-nav button").forEach((b) => b.addEventListener("click", () => {
    vindoDe = b.dataset.v; mostrar(b.dataset.v);
    if (b.dataset.v === "v-hist") listar();
    if (b.dataset.v === "v-ajustes") preencherAjustes();
  }));

  // Botão "voltar" do Android no app nativo
  if (NATIVO && window.Capacitor.Plugins.App) {
    window.Capacitor.Plugins.App.addListener("backButton", () => {
      if (!$("#v-laudo").hidden) $("#btn-voltar").click();
      else if ($("#v-nova").hidden) document.querySelector('.ag-nav [data-v="v-nova"]').click();
      else window.Capacitor.Plugins.App.exitApp();
    });
  }

  if ("serviceWorker" in navigator && !NATIVO && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(() => {});
  verificar();
})();
