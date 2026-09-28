const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function fixture() {
  const ids = ['review-playback-bar', 'review-playback-label', 'review-before', 'review-after', 'review-exit'];
  const nodes = Object.fromEntries(ids.map(id => [id, {
    hidden: true, events: {}, attrs: {},
    addEventListener(event, cb) { this.events[event] = cb; },
    setAttribute(key, value) { this.attrs[key] = value; },
    focus() {},
  }]));
  const controls = [{ disabled: false }, { disabled: true }];
  const context = { window: {}, document: {
    getElementById: id => nodes[id],
    querySelectorAll: () => controls,
    querySelector: () => ({ scrollIntoView() {} }),
  }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../frontend/shared/review-playback.js'), 'utf8'), context);
  const events = [];
  let busy = false;
  const player = context.window.ChessCouncilReview.create({
    canOpen: () => !busy, onStart: () => events.push('start'),
    render: state => events.push(state.phase), onExit: () => events.push('exit'),
    controls: 'button', notify: msg => events.push(msg),
  });
  return { nodes, controls, events, player, setBusy(value) { busy = value; } };
}
const move = { number: 3, san: 'Nxe5', fen_before: 'before', fen_after: 'after' };
test('key move opens after-position, allows comparison and restores controls on exit', () => {
  const f = fixture();
  assert.equal(f.player.open(move), true);
  assert.equal(f.player.active, true);
  assert.equal(f.nodes['review-playback-bar'].hidden, false);
  assert.deepEqual(f.controls.map(el => el.disabled), [true, true]);
  f.nodes['review-before'].events.click();
  f.nodes['review-after'].events.click();
  f.nodes['review-exit'].events.click();
  assert.deepEqual(f.events, ['start', 'after', 'before', 'after', 'exit']);
  assert.deepEqual(f.controls.map(el => el.disabled), [false, true]);
  assert.equal(f.player.active, false);
  assert.equal(f.nodes['review-playback-bar'].hidden, true);
});
test('switching key moves does not overwrite the original disabled states', () => {
  const f = fixture();
  f.player.open(move);
  f.player.open({ ...move, number: 5 });
  f.player.close();
  assert.deepEqual(f.events, ['start', 'after', 'after', 'exit']);
  assert.deepEqual(f.controls.map(el => el.disabled), [false, true]);
  f.player.close();
  assert.equal(f.events.length, 4);
});
test('missing snapshot and an in-flight move cannot open replay', () => {
  const f = fixture();
  assert.equal(f.player.open({ number: 1 }), false);
  f.setBusy(true);
  assert.equal(f.player.open(move), false);
  assert.equal(f.player.active, false);
  assert.deepEqual(f.controls.map(el => el.disabled), [false, true]);
});
