// Verifica la recuperación cuando la interfaz de Blazor ha perdido su circuito.
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const src = readFileSync(new URL('../frontend/wwwroot/js/cars-login-prompt-fallback.js', import.meta.url), 'utf8');
let clickListener;
let scheduled;
let reloads = 0;
class Element {
  constructor(name = '') { this.name = name; this.attributes = {}; this.isConnected = true; this.parent = null; }
  closest(query) {
    if (query === '[data-login-prompt-dismiss]') return this.name === 'button' ? this : null;
    if (query === '.login-required-backdrop') return this.parent;
    return null;
  }
  matches(query) { return query === '.login-required-backdrop' && this.name === 'overlay'; }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key] ?? null; }
}
const win = {setTimeout: cb => {scheduled = cb;}, location: {reload: () => {reloads += 1;}}};
const document = {addEventListener: (name, callback) => {assert.equal(name, 'click');clickListener=callback;}};
const sandbox = {window:win, document, Element};
runInNewContext(src, sandbox);
assert.equal(typeof clickListener,'function');
const overlay = new Element('overlay');
const button = new Element('button');
button.parent = overlay;
clickListener({target:button});
assert.equal(overlay.getAttribute('data-login-prompt-hidden'), 'true');
assert.equal(typeof scheduled,'function');
// Circulación normal: Blazor desmonta el componente; no recargar.
overlay.isConnected = false;
scheduled();
assert.equal(reloads, 0);
// Desconexión: la capa sigue montada, la recarga recupera la interfaz.
overlay.isConnected = true;
clickListener({target:button});
scheduled();
assert.equal(reloads, 1);
// Enlaces de acceso nativos no son interceptados por el respaldo.
const anchor = new Element('anchor');
clickListener({target:anchor});
assert.equal(reloads, 1);
console.log('OK: cierre de aviso, recuperación sin circuito Blazor y enlaces sin intercepción.');
