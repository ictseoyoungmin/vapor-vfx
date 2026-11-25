// Tests the real client state machine with a message-transport double, not a fluid solver.
import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { VaporWorkerClient } from '../bindings/web/worker-client.mjs';
const originalWorker = globalThis.Worker;
class Transport {
    static instances = [];
    constructor() { this.sent = []; this.terminated = false; Transport.instances.push(this); }
    postMessage(message) { this.sent.push(message); }
    terminate() { this.terminated = true; }
    reply(method, value) {
        const message = this.sent.find(m => m.method === method);
        assert.ok(message, `No ${method} message`);
        this.sent.splice(this.sent.indexOf(message), 1);
        this.onmessage({ data: { id: message.id, value } });
    }
}
before(() => { globalThis.Worker = Transport; });
after(() => { globalThis.Worker = originalWorker; });
function create(options = {}) {
    const client = new VaporWorkerClient(undefined, { shutdownTimeoutMs: 10, ...options });
    const transport = Transport.instances.at(-1);
    return { client, transport };
}
async function ready(options) {
    const pair = create(options);
    const promise = pair.client.init(undefined, {}, { backend: 'gpu' });
    pair.transport.reply('init', { backendInfo: { active: 'gpu' } });
    await promise;
    return pair;
}
async function stop(client, transport) {
    const promise = client.dispose();
    if (transport.sent.some(m => m.method === 'dispose')) transport.reply('dispose');
    await promise;
}
test('tick before init is rejected without accumulating elapsed time', async () => {
    const { client } = create();
    await assert.rejects(client.tick(.1), /Initialize/);
    assert.equal(client.diagnostics.queuedSeconds, 0);
    await client.dispose();
});
test('single in-flight tick coalesces elapsed, not a stale work queue', async () => {
    const { client, transport } = await ready();
    const tick = client.tick(.1);
    assert.equal(await client.tick(.2), null);
    assert.equal(await client.tick(.3), null);
    assert.equal(transport.sent.filter(m => m.method === 'tick').length, 1);
    transport.reply('tick', { atlas: new Uint8Array(4) }); await tick;
    const next = client.tick(.4);
    assert.ok(Math.abs(transport.sent[0].args[0] - .9) < 1e-10);
    transport.reply('tick', {}); await next;
    await stop(client, transport);
});
test('pending RPCs are bounded, including metrics/slider updates', async () => {
    const { client, transport } = await ready({ maxPendingRequests: 2 });
    const a = client.call('metrics'), b = client.call('metrics');
    await assert.rejects(client.call('metrics'), error => error.code === -10);
    assert.equal(client.diagnostics.pendingRequests, 2);
    transport.reply('metrics', {}); transport.reply('metrics', {});
    await Promise.all([a, b]); await stop(client, transport);
});
test('reset invalidates old atlas and does not carry over pre-reset time', async () => {
    const { client, transport } = await ready();
    const old = client.tick(.1); await client.tick(.25);
    const reset = client.call('reset');
    assert.equal(await client.tick(.2), null);
    transport.reply('tick', { atlas: 'old' }); assert.equal(await old, null);
    transport.reply('reset'); await reset;
    const next = client.tick(.01);
    assert.equal(transport.sent[0].args[0], .01);
    assert.equal(client.diagnostics.clientDiscardedSeconds, .25);
    transport.reply('tick', {}); await next; await stop(client, transport);
});
test('request timeout terminates worker and rejects every outstanding request', async () => {
    const { client, transport } = await ready({ requestTimeoutMs: 15 });
    const results = await Promise.allSettled([client.call('metrics'), client.call('metrics')]);
    assert.ok(results.every(r => r.status === 'rejected' && r.reason.code === -8));
    assert.ok(transport.terminated && client.closed);
    assert.equal(client.diagnostics.pendingRequests, 0); await client.dispose();
});
test('dispose cannot wait forever behind a hung tick', async () => {
    const { client, transport } = await ready();
    const result = client.tick(.1).catch(error => error);
    await client.dispose();
    assert.ok(transport.terminated && client.closed);
    assert.ok((await result) instanceof Error);
    await client.dispose();
});
test('new calls are rejected as soon as disposal starts', async () => {
    const { client, transport } = await ready();
    const disposal = client.dispose();
    await assert.rejects(client.call('metrics'), error => error.code === -2);
    assert.equal(await client.tick(.1), null);
    transport.reply('dispose'); await disposal;
});
test('dispose during init never transitions a terminated client to ready', async () => {
    const { client, transport } = create();
    const init = client.init('cpu.wasm').catch(error => error);
    const disposal = client.dispose(); transport.reply('init', {});
    assert.equal((await init).code, -2);
    transport.reply('dispose'); await disposal;
    assert.equal(client.diagnostics.ready, false);
});
test('message deserialization errors reject pending operations', async () => {
    const { client, transport } = await ready();
    const pending = client.call('metrics').catch(error => error);
    transport.onmessageerror(); assert.equal((await pending).code, -8);
    assert.ok(client.closed); await client.dispose();
});
test('postMessage failure removes request and clears its timer', async () => {
    const { client, transport } = await ready();
    const original = transport.postMessage;
    transport.postMessage = () => { throw new Error('clone failure'); };
    await assert.rejects(client.call('metrics'), /clone failure/);
    assert.equal(client.diagnostics.pendingRequests, 0);
    transport.postMessage = original; await stop(client, transport);
});
test('call cannot bypass init, tick coalescing or bounded dispose', async () => {
    const { client, transport } = await ready();
    for (const method of ['init', 'tick', 'dispose', 'constructor'])
        await assert.rejects(client.call(method), /Unknown worker operation/);
    await stop(client, transport);
});
test('large accumulated elapsed is capped and explicitly accounted for', async () => {
    const { client, transport } = await ready();
    const tick = client.tick(1); await client.tick(3600); await client.tick(3600);
    assert.equal(client.diagnostics.queuedSeconds, 3600);
    assert.equal(client.diagnostics.clientDiscardedSeconds, 3600);
    transport.reply('tick', {}); await tick; await stop(client, transport);
});
test('invalid limits and seconds are rejected before queue mutation', async () => {
    assert.throws(() => create({ maxPendingRequests: 0 }), RangeError);
    assert.throws(() => create({ requestTimeoutMs: NaN }), RangeError);
    assert.throws(() => create({ requestTimeoutMs: 120001 }), RangeError);
    assert.throws(() => create({ shutdownTimeoutMs: 2**32 }), RangeError);
    assert.throws(() => create({ unknown: 1 }), TypeError);
    const { client, transport } = await ready();
    for (const time of [NaN, Infinity, -1, 3601]) await assert.rejects(client.tick(time), RangeError);
    await stop(client, transport);
});

test('full RPC capacity retains tick elapsed instead of dropping time', async () => {
    const { client, transport } = await ready({ maxPendingRequests: 2 });
    const a=client.call('metrics'),b=client.call('diagnostics');
    assert.equal(await client.tick(.1),null);
    assert.equal(client.diagnostics.queuedSeconds,.1);
    assert.equal(transport.sent.filter(m=>m.method==='tick').length,0);
    transport.reply('metrics',{});transport.reply('diagnostics',{});await Promise.all([a,b]);
    const next=client.tick(.02);
    assert.ok(Math.abs(transport.sent[0].args[0]-.12)<1e-12);
    transport.reply('tick',{});await next;await stop(client,transport);
});
