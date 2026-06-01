// OTT Bot PWA Service Worker
// Offline cache + bildirim altyapısı

const CACHE_NAME = "ott-bot-v1";

self.addEventListener("install", (event) => {
    console.log("[SW] Install");
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    console.log("[SW] Activate");
    event.waitUntil(clients.claim());
});

// Push event — backend push gönderirse Android telefonda bildirim
self.addEventListener("push", (event) => {
    let data = {};
    try {
        data = event.data ? event.data.json() : {};
    } catch (e) {
        data = { title: "OTT Bot", body: event.data ? event.data.text() : "Yeni sinyal" };
    }
    const title = data.title || "OTT Bot";
    const options = {
        body: data.body || "Yeni sinyal geldi",
        icon: "/app/static/icon-192.png",
        badge: "/app/static/icon-192.png",
        tag: data.tag || "ott-signal",
        data: data,
        vibrate: [200, 100, 200],
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

// Bildirime tıklayınca dashboard'ı aç
self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: "window" }).then((clientList) => {
            for (const client of clientList) {
                if (client.url && "focus" in client) return client.focus();
            }
            if (clients.openWindow) return clients.openWindow("/");
        })
    );
});
