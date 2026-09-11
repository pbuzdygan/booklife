{% load static %}
const CACHE_NAME = "booklife-app-shell-v1";
const APP_SHELL = [
  "{% static 'catalog/app.css' %}",
  "{% static 'catalog/app.js' %}",
  "{% static 'catalog/tabler-icons.svg' %}",
  "{% static 'catalog/manifest.webmanifest' %}",
  "{% static 'catalog/icons/booklife-icon.svg' %}",
  "{% static 'catalog/icons/booklife-icon-192.png' %}",
  "{% static 'catalog/icons/booklife-icon-512.png' %}",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
    )),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // Authenticated HTML is never stored offline: it can contain private library data.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => new Response(
        "<!doctype html><title>Booklife is offline</title><meta name=viewport content='width=device-width,initial-scale=1'><main><h1>You're offline</h1><p>Reconnect to open your private library.</p></main>",
        { headers: { "Content-Type": "text/html; charset=utf-8" } },
      )),
    );
    return;
  }

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      })),
    );
  }
});
