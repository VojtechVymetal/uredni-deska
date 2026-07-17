document.addEventListener('DOMContentLoaded', () => {
    // Check if we have a password saved
    const savedPassword = sessionStorage.getItem('admin_password');
    if (savedPassword) {
        document.getElementById('passwordInput').value = savedPassword;
        loadSubscribers(savedPassword);
    }

    document.getElementById('loginForm').addEventListener('submit', (e) => {
        e.preventDefault();
        const pwd = document.getElementById('passwordInput').value;
        loadSubscribers(pwd);
    });
});

function logout() {
    sessionStorage.removeItem('admin_password');
    document.getElementById('mainContent').classList.add('hidden');
    document.getElementById('loginModal').classList.remove('hidden');
    document.getElementById('passwordInput').value = '';
    document.getElementById('subscribersTable').innerHTML = '';
}

function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe.toString()
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
}

function formatDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return d.toLocaleDateString('cs-CZ') + ' ' + d.toLocaleTimeString('cs-CZ', {hour: '2-digit', minute:'2-digit'});
}

async function loadSubscribers(password) {
    document.getElementById('loginError').classList.add('hidden');
    
    try {
        const response = await fetch('/api/admin/subscribers', {
            headers: {
                'Authorization': 'Bearer ' + password
            }
        });

        if (response.status === 401) {
            document.getElementById('loginError').classList.remove('hidden');
            sessionStorage.removeItem('admin_password');
            return;
        }

        if (!response.ok) {
            throw new Error('Chyba serveru: ' + response.statusText);
        }

        const data = await response.json();
        
        // Success
        sessionStorage.setItem('admin_password', password);
        document.getElementById('loginModal').classList.add('hidden');
        document.getElementById('mainContent').classList.remove('hidden');
        
        renderTable(data.subscribers || []);

    } catch (e) {
        alert('Nepoda≈ôilo se naƒç√≠st data: ' + e.message);
    }
}

function renderTable(subscribers) {
    const tbody = document.getElementById('subscribersTable');
    
    if (subscribers.length === 0) {
        tbody.innerHTML = '';
        document.getElementById('emptyState').classList.remove('hidden');
        document.getElementById('subscribersTable').parentElement.classList.add('hidden');
        return;
    }

    document.getElementById('emptyState').classList.add('hidden');
    document.getElementById('subscribersTable').parentElement.classList.remove('hidden');

    tbody.innerHTML = subscribers.map(sub => {
        const categories = sub.categories ? sub.categories.join(', ') : 'V≈°echny';
        const isActive = sub.is_active !== false;
        
        const severities = (sub.severities && sub.severities.length > 0)
            ? (sub.severities.includes('all') ? 'V≈°e' : sub.severities.join(', '))
            : 'V≈°e';

        return `
            <tr class="hover:bg-surface-container-low transition-colors">
                <td class="py-4 px-6">
                    <span class="font-bold text-on-surface">${escapeHtml(sub.email)}</span>
                </td>
                <td class="py-4 px-6 text-body-sm text-on-surface-variant max-w-[200px] truncate" title="${escapeHtml(categories)}">
                    ${escapeHtml(categories)}
                </td>
                <td class="py-4 px-6 text-body-sm text-on-surface-variant">
                    ${escapeHtml(severities)}
                </td>
                <td class="py-4 px-6">
                    ${isActive 
                        ? '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold tracking-widest bg-secondary/10 text-secondary"><span class="w-1.5 h-1.5 rounded-full bg-secondary"></span> AKTIVN√ç</span>'
                        : '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold tracking-widest bg-outline/10 text-on-surface-variant"><span class="w-1.5 h-1.5 rounded-full bg-outline"></span> NEAKTIVN√ç</span>'
                    }
                </td>
                <td class="py-4 px-6 text-data-mono font-data-mono text-on-surface-variant text-[13px]">
                    ${formatDate(sub.created_at)}
                </td>
                <td class="py-4 px-6 text-right">
                    <button onclick="deleteSubscriber(${sub.id}, '${escapeHtml(sub.email)}')" class="p-2 text-error hover:bg-error/10 rounded-full transition-colors tooltip-trigger" title="Smazat odbƒõratele">
                        <span class="material-symbols-outlined text-[20px]">delete</span>
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

async function deleteSubscriber(id, email) {
    if (!confirm(`Opravdu chcete nen√°vratnƒõ smazat odbƒõratele ${email}?`)) {
        return;
    }

    const pwd = sessionStorage.getItem('admin_password');
    
    try {
        const response = await fetch('/api/admin/subscribers/' + id, {
            method: 'DELETE',
            headers: {
                'Authorization': 'Bearer ' + pwd
            }
        });

        if (response.ok) {
            // Reload table
            loadSubscribers(pwd);
        } else {
            alert('Chyba p≈ôi maz√°n√≠: ' + response.statusText);
        }
    } catch (e) {
        alert('Nepoda≈ôilo se smazat z√°znam: ' + e.message);
    }
}

async function triggerEmails() {
    const btn = document.getElementById('btnTriggerEmails');
    if (!confirm('Opravdu chcete hned teÔ ruËnÏ rozeslat maily za poslednÌch 24 hodin vöem odbÏratel˘m?')) {
        return;
    }
    
    const pwd = sessionStorage.getItem('admin_password');
    const originalHtml = btn.innerHTML;
    btn.innerHTML = '<div class="w-4 h-4 border-2 border-on-primary border-t-transparent rounded-full animate-spin"></div> OdesÌl·m...';
    btn.disabled = true;
    
    try {
        const response = await fetch('/api/admin/trigger-emails', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + pwd
            }
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert('⁄spÏönÏ odesl·no! Server vr·til: ' + JSON.stringify(data.response));
        } else {
            alert('Chyba p¯i odesÌl·nÌ: ' + JSON.stringify(data));
        }
    } catch (e) {
        alert('Nepoda¯ilo se spustit odesÌl·nÌ: ' + e.message);
    } finally {
        btn.innerHTML = originalHtml;
        btn.disabled = false;
    }
}
