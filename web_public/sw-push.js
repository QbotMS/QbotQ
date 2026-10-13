/* sw-push.js - QBot: powiadomienia systemowe z dzwonka (Web Push), 2026-10-13.
   Rejestrowany z SETUP > Powiadomienia ("Powiadomienia na tym komputerze"). Serwer: qbot_webpush.py.
   Payload: {title, body, url, tag}. Klik otwiera url (albo przelacza na otwarta karte QBota). */
self.addEventListener("install", function(){ self.skipWaiting(); });
self.addEventListener("activate", function(e){ e.waitUntil(self.clients.claim()); });
self.addEventListener("push", function(e){
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = {title: "QBot", body: e.data ? e.data.text() : ""}; }
  e.waitUntil(self.registration.showNotification(d.title || "QBot", {
    body: d.body || "", tag: d.tag || undefined, renotify: !!d.tag,
    icon: "/favicon.svg", data: {url: d.url || "/"}
  }));
});
self.addEventListener("notificationclick", function(e){
  e.notification.close();
  var url = new URL((e.notification.data && e.notification.data.url) || "/", self.location.origin).href;
  e.waitUntil(self.clients.matchAll({type: "window", includeUncontrolled: true}).then(function(cs){
    for (var i = 0; i < cs.length; i++) {
      if (cs[i].url === url && "focus" in cs[i]) return cs[i].focus();
    }
    return self.clients.openWindow(url);
  }));
});
