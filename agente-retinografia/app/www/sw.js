// Service worker: guarda a interface para abrir rápido e sem rede. As chamadas /api nunca são guardadas.
const VERSAO = "agente-retino-v1";
const ARQUIVOS = ["./", "index.html", "css/app.css", "js/laudo.js", "js/app.js", "manifest.webmanifest",
  "icons/icon-192.png", "icons/icon-512.png", "demo/exemplo.json"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(VERSAO).then((c) => c.addAll(ARQUIVOS)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) =>
  Promise.all(ks.filter((k) => k !== VERSAO).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.includes("/api/")) return;
  e.respondWith(caches.match(e.request).then((hit) => {
    const rede = fetch(e.request).then((r) => { if (r.ok) caches.open(VERSAO).then((c) => c.put(e.request, r.clone())); return r; }).catch(() => hit);
    return hit || rede;
  }));
});
