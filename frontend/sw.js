"use strict";
const CACHE_NAME = "ace-canteen-shell-v4";
const APP_SHELL = ["/", "/manifest.webmanifest", "/css/style.css", "/js/app.js", "/assets/ace-logo.png", "/assets/canteen-hero.png"];
const PRIVATE_OR_API_PATH = url => url.pathname === "/api" || url.pathname.startsWith("/api/") || url.pathname === "/docs" || url.pathname.startsWith("/docs/") || url.pathname === "/openapi.json" || url.pathname.startsWith("/auth/");

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(APP_SHELL);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith("ace-canteen-shell-") && key !== CACHE_NAME).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || PRIVATE_OR_API_PATH(url)) return;
  // Never cache API responses. Only cache the known app shell, not arbitrary pages, auth data, or dynamic assets.
  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok) {
          const cache = await caches.open(CACHE_NAME);
          await cache.put("/", response.clone());
        }
        return response;
      } catch {
        return (await caches.match("/")) || new Response(
          "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>ACE Canteen offline</title><main><h1>ACE Canteen is offline</h1><p>Reconnect to load live catalogue, account, order and payment information. Ordering is unavailable offline.</p></main></html>",
          { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" }, status: 503 }
        );
      }
    })());
    return;
  }
  if (!APP_SHELL.includes(url.pathname) || url.search) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);
    if (cached) return cached;
    const response = await fetch(request);
    if (response.ok && response.type === "basic") await cache.put(request, response.clone());
    return response;
  })());
});
