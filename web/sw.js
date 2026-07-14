self.addEventListener('push', function(event) {
    if (event.data) {
        try {
            const data = event.data.json();
            const options = {
                body: data.body || 'Nová zpráva',
                icon: '/icon.png', // Můžeme přidat ikonu později
                badge: '/badge.png',
                data: {
                    url: data.url || '/'
                }
            };
            event.waitUntil(
                self.registration.showNotification(data.title || 'Úřední deska', options)
            );
        } catch(e) {
            event.waitUntil(
                self.registration.showNotification('Úřední deska', {body: event.data.text()})
            );
        }
    }
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(
        clients.openWindow(event.notification.data.url)
    );
});
