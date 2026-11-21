// La autenticación se almacena por PESTAÑA, no por navegador.
// sessionStorage evita mezclar usuarios en pestañas independientes.
// Algunos navegadores clonan sessionStorage al duplicar una pestaña:
// BroadcastChannel identifica esa copia y la convierte en una sesión nueva.
const TOKEN_KEY = "cars-attm.auth.jwt.tab.v2";
const TAB_ID_KEY = "cars-attm.auth.tab-id.v2";
const CHANNEL_NAME = "cars-attm.tab-presence.v2";
const LEGACY_SHARED_KEY = "cars-attm.auth.jwt.v1";
const PROBE_TIMEOUT_MS = 300;

let channel = null;
let tabId = null;
let initialized = false;
const instanceId = newId();

function newId() {
    // El identificador se utiliza solo para reconocer pestañas; no es un secreto.
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function store() { return window.sessionStorage; }

export function readToken() {
    try { return store().getItem(TOKEN_KEY); }
    catch { return null; }
}

export function saveToken(jwt) {
    store().setItem(TOKEN_KEY, jwt);
}

export function clearToken() {
    try { store().removeItem(TOKEN_KEY); }
    catch { /* El cierre de sesión del circuito Blazor se aplica igualmente. */ }
}

function openPresenceChannel() {
    if (channel || !window.BroadcastChannel) return;
    channel = new window.BroadcastChannel(CHANNEL_NAME);
    channel.addEventListener("message", (event) => {
        const message = event.data;
        if (message?.type === "probe" && message.tabId === tabId && message.from !== instanceId) {
            channel?.postMessage({ type: "present", tabId, from: instanceId, to: message.from });
        }
    });
}

function findActiveCopy() {
    if (!channel || !tabId) return Promise.resolve(false);
    return new Promise((resolve) => {
        let finished = false;
        let timeout;
        const onMessage = (event) => {
            const message = event.data;
            if (message?.type === "present" && message.tabId === tabId &&
                message.to === instanceId && message.from !== instanceId) {
                done(true);
            }
        };
        const done = (found) => {
            if (finished) return;
            finished = true;
            window.clearTimeout(timeout);
            channel?.removeEventListener("message", onMessage);
            resolve(found);
        };
        channel.addEventListener("message", onMessage);
        timeout = window.setTimeout(() => done(false), PROBE_TIMEOUT_MS);
        channel.postMessage({ type: "probe", tabId, from: instanceId });
    });
}

export async function initializeTab() {
    if (initialized) return { token: readToken(), startAtHome: false };
    initialized = true;
    let previousId = null;
    try { previousId = store().getItem(TAB_ID_KEY); }
    catch { /* El navegador puede bloquear sessionStorage. */ }

    tabId = previousId || newId();
    try { store().setItem(TAB_ID_KEY, tabId); }
    catch { /* Se conserva el estado en memoria durante la visita. */ }

    openPresenceChannel();
    const cloned = Boolean(previousId) && await findActiveCopy();
    if (cloned) {
        // Duplicar no debe heredar la cuenta de la pestaña original.
        clearToken();
        tabId = newId();
        try { store().setItem(TAB_ID_KEY, tabId); } catch { }
    }

    // Limpiamos la credencial que las versiones antiguas guardaban globalmente.
    try { window.localStorage.removeItem(LEGACY_SHARED_KEY); } catch { }

    return { token: readToken(), startAtHome: !previousId || cloned };
}

export function unsubscribe() {
    if (channel) {
        channel.close();
        channel = null;
    }
}
