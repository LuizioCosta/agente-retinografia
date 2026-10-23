// ==========================================================================================
// Laudo em português — porte fiel da CÉLULA 5 do notebook EyeFlow V800 (render_laudo)
// Mesmo CSS, mesmas cores, mesmos gráficos SVG e mesmos textos. Recebe o JSON do servidor.
// ==========================================================================================
(function (g) {
  const QUADS = ["I", "S", "N", "T"];
  const SIGN_NAMES = ["rnfl_defect", "rim_notching", "vessel_bayoneting", "beta_zone_atrophy", "peripapillary_atrophy", "disc_hemorrhage"];
  const QUAD_PT = { I: "Inferior", S: "Superior", N: "Nasal", T: "Temporal" };
  const RIM_PT = { "normal": "Preservada", "mild thinning": "Afinamento leve", "severe thinning": "Afinamento acentuado", "null": "Não informado" };
  const SIGN_PT = {
    rnfl_defect: "Defeito da camada de fibras nervosas (CFNR)", rim_notching: "Entalhe (notch) da rima",
    vessel_bayoneting: "Sinal da baioneta vascular", beta_zone_atrophy: "Atrofia peripapilar de zona beta",
    peripapillary_atrophy: "Atrofia peripapilar", disc_hemorrhage: "Hemorragia de disco"
  };
  const STATE_PT = { absent: "Ausente", present: "Presente", uncertain: "Indeterminado", "null": "Não informado" };
  const RIM_COLOR = { "normal": "#2e9d6b", "mild thinning": "#e0a12b", "severe thinning": "#d1495b", "null": "#9aa5ad" };
  const STATE_COLOR = { absent: "#2e9d6b", present: "#d1495b", uncertain: "#e0a12b", "null": "#9aa5ad" };
  const k = (x) => (x == null ? "null" : x);

  const br = (x, d = 2) => Number(x).toFixed(d).replace(".", ",");
  const pct = (x) => (100 * x).toFixed(0) + "%";
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;" }[c]));

  function cdrFaixa(x) {
    if (x > 0.6) return ["Aumentada", "#d1495b"];
    if (x >= 0.5) return ["Limítrofe", "#e0a12b"];
    return ["Dentro da normalidade", "#2e9d6b"];
  }

  // ---------------- componentes SVG ----------------
  function svgCdrBar(label, v) {
    const w = 420, h = 56, x = (t) => 20 + t * (w - 40);
    const [, cor] = cdrFaixa(v);
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="${esc(label)}: ${br(v)}">
<rect x="${x(0)}" y="22" width="${x(.5) - x(0)}" height="12" fill="#cfeadb"/><rect x="${x(.5)}" y="22" width="${x(.6) - x(.5)}" height="12" fill="#f6e2b5"/>
<rect x="${x(.6)}" y="22" width="${x(1) - x(.6)}" height="12" fill="#f3c8ce"/>
<text x="${x(0)}" y="50" font-size="10" fill="#5b6b75">0</text><text x="${x(.5) - 7}" y="50" font-size="10" fill="#5b6b75">0,5</text>
<text x="${x(.6) - 7}" y="50" font-size="10" fill="#5b6b75">0,6</text><text x="${x(1) - 6}" y="50" font-size="10" fill="#5b6b75">1</text>
<polygon points="${x(v) - 7},8 ${x(v) + 7},8 ${x(v)},20" fill="${cor}"/><line x1="${x(v)}" y1="20" x2="${x(v)}" y2="36" stroke="#1d2b33" stroke-width="2"/>
</svg>`;
  }

  function svgDisco(rim, cdrV, cdrH, nasalDireita) {
    // Disco esquemático: rima por quadrante (cores) + escavação proporcional ao CDR.
    const cx = 150, cy = 150, R1 = 118, R0 = 78, rad = (a) => (a * Math.PI) / 180;
    const ang = { S: -90, I: 90, N: nasalDireita ? 0 : 180, T: nasalDireita ? 180 : 0 };
    const p = (r, a) => [cx + r * Math.cos(rad(a)), cy + r * Math.sin(rad(a))];
    const f = (n) => n.toFixed(1);
    function arc(a0, a1, r1, r0) {
      const [x1, y1] = p(r1, a0), [x2, y2] = p(r1, a1), [x3, y3] = p(r0, a1), [x4, y4] = p(r0, a0);
      return `M${f(x1)},${f(y1)} A${r1},${r1} 0 0 1 ${f(x2)},${f(y2)} L${f(x3)},${f(y3)} A${r0},${r0} 0 0 0 ${f(x4)},${f(y4)} Z`;
    }
    let segs = "", labels = "";
    for (const q of QUADS) {
      const a = ang[q];
      segs += `<path d="${arc(a - 44, a + 44, R1, R0)}" fill="${RIM_COLOR[k(rim[q])]}" stroke="#fff" stroke-width="3"/>`;
      const lx = cx + (R1 + 18) * Math.cos(rad(a)), ly = cy + (R1 + 18) * Math.sin(rad(a)) + 5;
      labels += `<text x="${lx.toFixed(0)}" y="${ly.toFixed(0)}" text-anchor="middle" font-size="14" font-weight="700" fill="#1d2b33">${q}</text>`;
    }
    const rx = Math.max(8, Math.min(R0 - 4, cdrH * R0 * 1.05)), ry = Math.max(8, Math.min(R0 - 4, cdrV * R0 * 1.05));
    return `<svg viewBox="0 0 300 300" width="100%" style="max-width:300px" role="img" aria-label="Esquema do disco óptico">
<circle cx="${cx}" cy="${cy}" r="${R1 + 2}" fill="#f6d9c4"/>${segs}
<circle cx="${cx}" cy="${cy}" r="${R0}" fill="#f9e8d8"/>
<ellipse cx="${cx}" cy="${cy}" rx="${f(rx)}" ry="${f(ry)}" fill="#fffaf2" stroke="#c9a27e" stroke-dasharray="4 3"/>
<text x="${cx}" y="${cy + 4}" text-anchor="middle" font-size="11" fill="#7b5e44">escavação</text>${labels}</svg>`;
  }

  function svgIsntBars(scores) {
    // Barras e posições vêm dos mesmos escores do Stage 1 (a ordem textual do laudo aparece acima).
    const w = 420, vals = QUADS.map((q) => scores[q]), mn = Math.min(...vals), mx = Math.max(...vals);
    const sorted = [...QUADS].sort((a, b) => scores[b] - scores[a]);
    const rankPos = Object.fromEntries(sorted.map((q, i) => [q, i + 1]));
    let rows = "";
    QUADS.forEach((q, i) => {
      const v = scores[q], frac = 0.08 + 0.92 * (v - mn) / Math.max(mx - mn, 1e-6), y = 10 + i * 30;
      rows += `<text x="0" y="${y + 14}" font-size="12" fill="#1d2b33">${QUAD_PT[q]}</text>` +
        `<rect x="80" y="${y + 2}" width="${w - 150}" height="16" rx="3" fill="#e9eef1"/>` +
        `<rect x="80" y="${y + 2}" width="${Math.max(4, (w - 150) * frac).toFixed(1)}" height="16" rx="3" fill="#2a7f8f"/>` +
        `<text x="${w - 62}" y="${y + 14}" font-size="12" fill="#1d2b33">${rankPos[q]}º</text>`;
    });
    return `<p style="margin:10px 0 2px;font-size:12px;color:#64757f">Espessura relativa da rima estimada pelo Stage 1 (posição 1º = mais espessa)</p><svg viewBox="0 0 ${w} 130" width="100%" role="img" aria-label="Escores relativos de espessura da rima">${rows}</svg>`;
  }

  const barHtml = (p, cor = "#2a7f8f") =>
    `<div class="bar"><i style="width:${Math.max(2, 100 * p).toFixed(0)}%;background:${cor}"></i></div><span class="barv">${pct(p)}</span>`;

  const CSS = `
.ef{font:14px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;color:#1d2b33;background:#eef3f6;padding:18px;margin:0}
.ef *{box-sizing:border-box}.ef .page{max-width:1000px;margin:0 auto;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 4px 22px #0f2b3a1a}
.ef header{background:linear-gradient(120deg,#0d5563,#167a7f);color:#fff;padding:22px 28px;display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap}
.ef header h1{margin:0;font-size:22px;letter-spacing:.2px}.ef header p{margin:4px 0 0;opacity:.85;font-size:13px}
.ef .meta{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border-bottom:1px solid #e3eaee}
.ef .meta div{padding:12px 18px;border-right:1px solid #e3eaee}.ef .meta small{display:block;color:#64757f;font-size:11px;text-transform:uppercase;letter-spacing:.6px}
.ef .meta b{font-size:14px}.ef .body{padding:22px 28px}
.ef .verdict{border-radius:12px;padding:18px 22px;display:flex;gap:22px;align-items:center;flex-wrap:wrap;margin-bottom:22px}
.ef .verdict h2{margin:0 0 4px;font-size:21px}.ef .verdict p{margin:0}.ef .verdict .score{margin-left:auto;min-width:260px}
.ef .pos{background:#fbe9ec;border-left:7px solid #d1495b}.ef .neg{background:#e6f5ee;border-left:7px solid #2e9d6b}
.ef .alert{background:#fff4d9;border-left:5px solid #c58c2e;padding:10px 14px;border-radius:8px;margin:8px 0}
.ef .imgs{display:grid;grid-template-columns:1.35fr 1fr 1fr;gap:12px;margin-bottom:8px}
.ef figure{margin:0;align-self:start;background:#0b1418;border-radius:10px;overflow:hidden}.ef figure img{width:100%;display:block;height:280px;object-fit:contain}
.ef figcaption{background:#f4f7f9;color:#40525c;font-size:12px;padding:6px 10px}
.ef section{margin-top:22px}.ef section h3{font-size:15px;margin:0 0 10px;color:#0d5563;border-bottom:2px solid #d9e6ea;padding-bottom:6px}
.ef .two{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}
.ef table{width:100%;border-collapse:collapse}.ef td,.ef th{padding:7px 8px;border-bottom:1px solid #edf1f3;text-align:left;vertical-align:middle}
.ef th{font-size:11px;text-transform:uppercase;color:#64757f;letter-spacing:.5px}
.ef .chip{display:inline-block;padding:2px 10px;border-radius:20px;color:#fff;font-size:12px;font-weight:600;white-space:nowrap}
.ef .bar{display:inline-block;width:110px;height:9px;background:#e9eef1;border-radius:5px;overflow:hidden;vertical-align:middle}
.ef .bar i{display:block;height:100%}.ef .barv{font-size:12px;color:#40525c;margin-left:6px}
.ef .kv{display:flex;justify-content:space-between;gap:10px}.ef .kv b{font-size:20px}
.ef .text{background:#f7fafb;border-radius:8px;padding:12px 14px;white-space:pre-wrap}
.ef ul{margin:6px 0 0 18px;padding:0}.ef li{margin:3px 0}
.ef .legend span{display:inline-flex;align-items:center;gap:5px;margin-right:12px;font-size:12px}.ef .legend i{width:12px;height:12px;border-radius:3px;display:inline-block}
.ef footer{background:#f4f7f9;padding:16px 28px;font-size:12px;color:#4f616b;border-top:1px solid #e3eaee}
.ef details{margin-top:8px}.ef summary{cursor:pointer;color:#0d5563;font-weight:600}
.ef .sig{margin-top:26px;display:grid;grid-template-columns:1fr 1fr;gap:30px}.ef .sig div{border-top:1px solid #8396a5;padding-top:6px;font-size:12px;color:#4f616b}
@media(max-width:760px){.ef figure img{height:auto;max-height:360px}.ef .meta{grid-template-columns:1fr 1fr}.ef .imgs,.ef .two,.ef .sig{grid-template-columns:1fr}.ef .body,.ef header{padding:16px}}
@media(max-width:420px){.ef{padding:0}.ef .page{border-radius:0}.ef .verdict .score{min-width:0;width:100%;margin-left:0}.ef .meta div{padding:10px 12px}.ef td,.ef th{padding:6px 4px}.ef .bar{width:70px}}
@media print{.ef{background:#fff;padding:0}.ef .page{box-shadow:none}.ef details{display:none}}
`;

  function recomendacoes(dx, findings, qualOk, discordante) {
    const r = [];
    if (!qualOk) r.push("Qualidade da imagem com ressalvas: considerar repetir a retinografia antes de interpretar o resultado.");
    if (dx === 1) {
      r.push("Encaminhar para avaliação oftalmológica completa, preferencialmente com especialista em glaucoma.",
        "Complementar com medida da pressão intraocular, gonioscopia, paquimetria, OCT de disco óptico/CFNR e campimetria computadorizada.",
        "Correlacionar com história clínica e fatores de risco (idade, história familiar, miopia, PIO, etnia).");
    } else {
      r.push("Manter acompanhamento oftalmológico conforme idade e fatores de risco.",
        "Havendo fatores de risco ou queixas visuais, considerar avaliação complementar (PIO, OCT).");
      if (findings.length) r.push("Achados isolados (" + findings.join(", ") + ") justificam correlação clínica no próximo exame.");
    }
    if (discordante) r.push("Stage 1 e Stage 2 discordaram: priorizar revisão humana deste exame.");
    return r;
  }

  function renderLaudo(R, opts = {}) {
    const instituicao = opts.instituicao || "EyeFlow — Pesquisa em oftalmologia assistida por IA";
    const mostrarOriginal = opts.mostrarOriginal !== false;
    const ev = R.ev, s2 = R.s2, dx = R.dx, prob = R.prob;
    const cdrV = R.cdr_v, cdrH = R.cdr_h, rim = R.rim, signs = R.signs, ordem = R.ordem, nasalDir = R.nasal_direita;
    const [titulo, cls] = dx === 1 ? ["Glaucoma provável", "pos"] : ["Glaucoma improvável", "neg"];
    const frase = dx === 1 ? "Achados estruturais sugestivos de neuropatia óptica glaucomatosa."
      : "Sem achados estruturais suficientes para suspeita de neuropatia óptica glaucomatosa.";
    let alerts = "";
    if (R.discordante) alerts += '<div class="alert"><b>Discordância entre etapas:</b> o classificador inicial (Stage 1) e o raciocínio final (Stage 2) chegaram a conclusões diferentes. Revisão prioritária.</div>';
    if (Math.abs(prob - 0.5) < 0.15) alerts += '<div class="alert"><b>Resultado próximo ao limiar de decisão</b>: interpretar com cautela.</div>';
    if (R.parse_falhas && R.parse_falhas.length) alerts += '<div class="alert">Itens não explicitados no texto do modelo foram preenchidos com a evidência do Stage 1: ' + esc(R.parse_falhas.join(", ")) + ".</div>";
    const qual = R.qualidade, qualOk = qual.every((q) => q[2]);
    const qualRows = qual.map(([n, v, ok]) => `<tr><td>${esc(n)}</td><td>${esc(v)}</td><td><span class="chip" style="background:${ok ? "#2e9d6b" : "#e0a12b"}">${ok ? "Adequado" : "Atenção"}</span></td></tr>`).join("");
    const [fv, cv] = cdrFaixa(cdrV), [fh, ch] = cdrFaixa(cdrH);
    const rimRows = QUADS.map((q) => `<tr><td>${QUAD_PT[q]}</td><td><span class="chip" style="background:${RIM_COLOR[k(rim[q])]}">${RIM_PT[k(rim[q])]}</span></td>` +
      `<td>${barHtml(ev.rim_abnormality[q].probabilities[rim[q] || "normal"], RIM_COLOR[k(rim[q])])}</td></tr>`).join("");
    const signRows = SIGN_NAMES.map((s) => `<tr><td>${SIGN_PT[s]}</td><td><span class="chip" style="background:${STATE_COLOR[k(signs[s])]}">${STATE_PT[k(signs[s])]}</span></td>` +
      `<td>${barHtml(ev.structural_signs[s].probabilities.present, "#d1495b")}</td></tr>`).join("");
    const isntOk = ordem === "I>S>N>T";
    const ordemPt = ordem.split(">").map((q) => QUAD_PT[q]).join(" > ");
    const sev = QUADS.filter((q) => rim[q] === "severe thinning").map((q) => QUAD_PT[q].toLowerCase());
    const mild = QUADS.filter((q) => rim[q] === "mild thinning").map((q) => QUAD_PT[q].toLowerCase());
    const pres = SIGN_NAMES.filter((s) => signs[s] === "present").map((s) => SIGN_PT[s]);
    const unc = SIGN_NAMES.filter((s) => signs[s] === "uncertain").map((s) => SIGN_PT[s]);
    const sintese = `Relação escavação/disco vertical de ${br(cdrV)} (${fv.toLowerCase()}) e horizontal de ${br(cdrH)} (${fh.toLowerCase()}). ` +
      `Ordem de espessura da rima ${ordemPt}, ${isntOk ? "compatível com" : "em desacordo com"} a regra ISNT. ` +
      (sev.length ? `Afinamento acentuado da rima nos setores ${sev.join(", ")}. ` : "") +
      (mild.length ? `Afinamento leve nos setores ${mild.join(", ")}. ` : "") +
      (!sev.length && !mild.length ? "Rima neurorretiniana preservada nos quatro setores. " : "") +
      (pres.length ? `Sinais estruturais presentes: ${pres.join("; ")}. ` : "Sem sinais estruturais glaucomatosos identificados. ") +
      (unc.length ? `Achados indeterminados: ${unc.join("; ")}.` : "");
    const qTxt = R.passo1_pt || (!s2 ? "Avaliação de qualidade textual não gerada (modo somente Stage 1)." : "");
    const just = R.passo6_pt || "";
    const findings = QUADS.filter((q) => rim[q] !== "normal").map((q) => QUAD_PT[q].toLowerCase() + " (" + RIM_PT[k(rim[q])].toLowerCase() + ")")
      .concat(pres.map((p) => p.toLowerCase()));
    const recs = recomendacoes(dx, dx === 0 ? findings : [], qualOk, R.discordante).map((x) => `<li>${esc(x)}</li>`).join("");
    const scoreHtml = `<div class="kv"><span>Escore final do modelo</span><b>${pct(prob)}</b></div>${barHtml(prob, dx ? "#d1495b" : "#2e9d6b")}` +
      `<div class="kv" style="margin-top:6px"><span>Classificador inicial (Stage 1)</span><span>${pct(R.s1_prob_cal)}</span></div>`;
    const perf = R.perf || {};
    let perfTxt = "";
    if (perf.fonte) {
      const f = (key) => (perf[key] == null ? "—" : key !== "cdr_mae" ? pct(perf[key]) : br(perf[key], 3));
      perfTxt = `Desempenho medido em ${perf.fonte} (${perf.n} imagens, uma execução): acurácia balanceada ${f("acuracia_balanceada")}, ` +
        `sensibilidade ${f("sensibilidade")}, especificidade ${f("especificidade")}, AUC ${f("auc")}, erro médio do CDR ${f("cdr_mae")}. `;
    }
    const original = mostrarOriginal && s2 && R.report_en
      ? `<details><summary>Relatório original do modelo (inglês)</summary><div class="text">${esc(R.report_en)}</div></details>` : "";
    const olho = R.olho, im = R.imagens;
    return `<div class="ef"><style>${CSS}</style><div class="page">
<header><div><h1>Laudo preliminar de retinografia</h1><p>Triagem assistida por IA para glaucoma · ${esc(instituicao)}</p></div>
<div style="text-align:right"><p>Exame <b>${esc(R.exam_id)}</b></p><p>${esc(R.data)}</p></div></header>
<div class="meta"><div><small>Paciente</small><b>${esc(R.paciente || "Não informado")}</b></div><div><small>Olho</small><b>${esc(olho)}</b></div>
<div><small>Arquivo</small><b>${esc(R.arquivo)}</b></div><div><small>Método</small><b>${s2 ? "RETFound + MedGemma-27B (V800)" : "RETFound (V800, Stage 1)"}</b></div></div>
<div class="body">
<div class="verdict ${cls}"><div><small>IMPRESSÃO DIAGNÓSTICA PRELIMINAR</small><h2>${titulo}</h2><p>${frase}</p></div><div class="score">${scoreHtml}</div></div>
${alerts}
<div class="imgs">
<figure><img src="${im.original}" alt="Retinografia original"><figcaption>Retinografia original</figcaption></figure>
<figure><img src="${im.atencao}" alt="Mapa de atenção"><figcaption>Regiões mais ponderadas pelo modelo (indicativo)</figcaption></figure>
<figure><img src="${im.disco}" alt="Disco óptico ampliado"><figcaption>Disco óptico (recorte automático)</figcaption></figure></div>
<section><h3>1. Qualidade da imagem</h3><div class="two"><div class="text">${esc(qTxt)}</div><table><tr><th>Verificação automática</th><th>Valor</th><th></th></tr>${qualRows}</table></div></section>
<section><h3>2. Relação escavação/disco (E/D)</h3><div class="two">
<div><div class="kv"><span>Vertical</span><b style="color:${cv}">${br(cdrV)}</b></div><small>${fv}</small>${svgCdrBar("CDR vertical", cdrV)}</div>
<div><div class="kv"><span>Horizontal</span><b style="color:${ch}">${br(cdrH)}</b></div><small>${fh}</small>${svgCdrBar("CDR horizontal", cdrH)}</div></div>
<p class="legend"><span><i style="background:#cfeadb"></i>≤ 0,5 normal</span><span><i style="background:#f6e2b5"></i>0,5–0,6 limítrofe</span><span><i style="background:#f3c8ce"></i>&gt; 0,6 aumentada</span></p></section>
<section><h3>3. Rima neurorretiniana e regra ISNT</h3><div class="two">
<div style="text-align:center">${svgDisco(rim, cdrV, cdrH, nasalDir)}<p class="legend"><span><i style="background:#2e9d6b"></i>Preservada</span><span><i style="background:#e0a12b"></i>Afinamento leve</span><span><i style="background:#d1495b"></i>Afinamento acentuado</span></p>
<small>Esquema ilustrativo; posição nasal/temporal conforme o olho ${esc(olho)}.</small></div>
<div><p><b>Ordem observada:</b> ${ordemPt}<br><b>Esperada (ISNT):</b> Inferior &gt; Superior &gt; Nasal &gt; Temporal<br>
<span class="chip" style="background:${isntOk ? "#2e9d6b" : "#d1495b"}">${isntOk ? "Regra ISNT respeitada" : "Regra ISNT violada"}</span></p>
${svgIsntBars(ev.isnt_rank.scores)}
<table><tr><th>Setor</th><th>Rima</th><th>Confiança</th></tr>${rimRows}</table></div></div></section>
<section><h3>4. Sinais estruturais glaucomatosos</h3><table><tr><th>Sinal</th><th>Achado</th><th>Probabilidade de presença</th></tr>${signRows}</table></section>
<section><h3>5. Síntese estrutural</h3><div class="text">${esc(sintese)}</div></section>
<section><h3>6. Conclusão</h3><div class="text"><b>${titulo}.</b> ${esc(just)}</div></section>
<section><h3>7. Sugestão de conduta</h3><ul>${recs}</ul></section>
${original}
<div class="sig"><div>Gerado automaticamente por EyeFlow V800 (Agente de Retinografia) em ${esc(R.data)}</div><div>Revisão e assinatura do médico oftalmologista (nome / CRM)</div></div>
</div>
<footer><b>Documento preliminar, sem valor diagnóstico isolado.</b> Gerado por modelo de pesquisa (Glaucoma-CoT, RETFound + MedGemma-27B, versão EyeFlow V800), sem validação clínica prospectiva e sem registro na ANVISA.
Deve ser interpretado por médico oftalmologista junto com exame clínico e exames complementares. ${perfTxt}
O mapa de atenção mostra onde o modelo concentrou o peso das evidências e não é uma explicação causal. Decisão: ${esc(R.modo)}. Tempo de processamento: ${br(R.segundos, 1)} s.</footer>
</div></div>`;
  }

  function documentoCompleto(R, opts) {
    return '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Laudo ' +
      esc(R.exam_id) + ' — Agente de Retinografia</title></head><body style="margin:0">' + renderLaudo(R, opts) + "</body></html>";
  }

  g.Laudo = { renderLaudo, documentoCompleto, esc };
})(window);
