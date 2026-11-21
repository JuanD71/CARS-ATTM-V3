// Prueba de escritorio del almacenamiento independiente y pestañas duplicadas.
// No sustituye una prueba real con Blazor dentro de Docker.
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../frontend/wwwroot/js/cars-auth-tabs.js', import.meta.url), 'utf8');
const script = source.replace(/^export /gm, '') + '\nglobalThis.api={initializeTab,readToken,saveToken,clearToken,unsubscribe};';
let count = 0;

class Store {
  constructor(from) { this.data = new Map(from?.data || []); }
  getItem(key) { return this.data.has(key) ? this.data.get(key) : null; }
  setItem(key, value) { this.data.set(key, String(value)); }
  removeItem(key) { this.data.delete(key); }
}

const liveChannels = new Map();
class Channel {
  constructor(name) {
    this.name = name;
    this.listeners = new Set();
    if (!liveChannels.has(name)) liveChannels.set(name, new Set());
    liveChannels.get(name).add(this);
  }
  addEventListener(type, fn) { if (type === 'message') this.listeners.add(fn); }
  removeEventListener(type, fn) { if (type === 'message') this.listeners.delete(fn); }
  postMessage(message) {
    for (const listener of liveChannels.get(this.name) || []) {
      if (listener !== this) {
        for (const fn of [...listener.listeners]) fn({ data: message });
      }
    }
  }
  close() { liveChannels.get(this.name)?.delete(this); }
}

const sharedLocalStorage = new Store();
sharedLocalStorage.setItem('cars-attm.auth.jwt.v1', 'token-de-version-antigua');
function tab(sessionStorage = new Store()) {
  const window = {
    sessionStorage, localStorage: sharedLocalStorage, BroadcastChannel: Channel,
    crypto: { randomUUID: () => 'tab-' + ++count },
    setTimeout, clearTimeout,
  };
  const sandbox = { window, console, Promise, Date, Math };
  runInNewContext(script, sandbox, { filename: 'cars-auth-tabs.js' });
  return { ...sandbox.api, sessionStorage };
}

// Abrir dos pestañas nuevas permite iniciar dos cuentas distintas.
const first = tab();
assert.deepEqual(JSON.parse(JSON.stringify(await first.initializeTab())), { token: null, startAtHome: true });
first.saveToken('jwt-usuario-A');
const second = tab();
assert.deepEqual(JSON.parse(JSON.stringify(await second.initializeTab())), { token: null, startAtHome: true });
second.saveToken('jwt-usuario-B');
assert.equal(first.readToken(), 'jwt-usuario-A');
assert.equal(second.readToken(), 'jwt-usuario-B');
assert.equal(sharedLocalStorage.getItem('cars-attm.auth.jwt.v1'), null);

// Recargar una pestaña CONSERVA su usuario y su ruta actual.
first.unsubscribe(); // Se desmontó el documento anterior de la primera pestaña.
const reloadedFirst = tab(first.sessionStorage);
assert.deepEqual(JSON.parse(JSON.stringify(await reloadedFirst.initializeTab())),
  { token: 'jwt-usuario-A', startAtHome: false });

// Duplicar una pestaña CLONA sessionStorage en los navegadores principales.
// La copia detecta a la original, empieza como visitante y abre Inicio.
const duplicated = tab(new Store(reloadedFirst.sessionStorage));
assert.deepEqual(JSON.parse(JSON.stringify(await duplicated.initializeTab())),
  { token: null, startAtHome: true });
assert.equal(reloadedFirst.readToken(), 'jwt-usuario-A');
assert.equal(second.readToken(), 'jwt-usuario-B');

// La copia puede iniciar una TERCERA cuenta sin afectar ninguna de las anteriores.
duplicated.saveToken('jwt-usuario-C');
assert.equal(reloadedFirst.readToken(), 'jwt-usuario-A');
assert.equal(second.readToken(), 'jwt-usuario-B');
assert.equal(duplicated.readToken(), 'jwt-usuario-C');

// Cerrar sesión en una pestaña NO desconecta las otras.
second.clearToken();
assert.equal(second.readToken(), null);
assert.equal(reloadedFirst.readToken(), 'jwt-usuario-A');
assert.equal(duplicated.readToken(), 'jwt-usuario-C');

reloadedFirst.unsubscribe();
second.unsubscribe();
duplicated.unsubscribe();
console.log('OK: usuarios A/B/C aislados, pestaña duplicada independiente, apertura en Inicio, recarga y logout.');
