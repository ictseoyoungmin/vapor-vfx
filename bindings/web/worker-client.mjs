import { BackendError } from './gpu-protocol.mjs';

const METHODS = new Set(['step', 'advance', 'setEmitter', 'removeEmitter', 'setSphere',
    'setCapsule', 'setBox', 'removeObstacle', 'setProfile', 'reset', 'metrics', 'diagnostics']);

/** A bounded RPC client. One tick in flight, explicit time accounting, finite shutdown.
 * Timeout stops this worker; it never pretends another backend completed its work.
 */
export class VaporWorkerClient {
    #worker; #pending = new Map(); #next = 1;
    #tick = false; #closed = false; #ready = false; #elapsed = 0;
    #initializing = false; #resetting = false; #closing = false; #disposePromise;
    #epoch = 0; #discarded = 0; #options;

    constructor(url = new URL('./vapor-worker.mjs', import.meta.url), options = {}) {
        this.#options = { maxPendingRequests: 32, requestTimeoutMs: 30000,
            shutdownTimeoutMs: 1000, ...options };
        for (const key of Object.keys(options)) {
            if (!['maxPendingRequests', 'requestTimeoutMs', 'shutdownTimeoutMs'].includes(key))
                throw new TypeError(`Unknown worker option: ${key}`);
        }
        for (const key of ['maxPendingRequests', 'requestTimeoutMs', 'shutdownTimeoutMs']) {
            if (!Number.isInteger(this.#options[key]) || this.#options[key] < 1)
                throw new RangeError(`${key} must be a positive integer`);
        }
        for (const key of ['requestTimeoutMs', 'shutdownTimeoutMs']) {
            if (this.#options[key] > 120000) throw new RangeError(`${key} must be <= 120000`);
        }
        if (this.#options.maxPendingRequests > 1024) throw new RangeError('Too many pending requests');
        this.#worker = new Worker(url, { type: 'module' });
        this.#worker.onmessage = ({ data }) => {
            const pending = this.#pending.get(data?.id);
            if (!pending) return;
            this.#pending.delete(data.id);
            clearTimeout(pending.timer);
            if (data.error) pending.reject(new BackendError(data.error.code ?? -8, data.error.message));
            else pending.resolve(data.value);
        };
        this.#worker.onerror = error => this.#stop(new BackendError(-8, error.message || 'Vapor worker failed'));
        this.#worker.onmessageerror = () => this.#stop(new BackendError(-8, 'Worker response could not be deserialized'));
    }
    get closed() { return this.#closed; }
    get diagnostics() {
        return Object.freeze({ pendingRequests: this.#pending.size, tickPending: this.#tick,
            queuedSeconds: this.#elapsed, clientDiscardedSeconds: this.#discarded,
            ready: this.#ready, closing: this.#closing, closed: this.#closed });
    }
    #stop(error) {
        if (this.#closed) return;
        this.#closed = true; this.#ready = false;
        this.#worker.terminate();
        for (const pending of this.#pending.values()) {
            clearTimeout(pending.timer);
            pending.reject(error);
        }
        this.#pending.clear();
    }
    #send(method, args, timeout = this.#options.requestTimeoutMs, shutdown = false) {
        if (this.#closed || (this.#closing && !shutdown))
            return Promise.reject(new BackendError(-2, 'Worker closed or closing'));
        if (!shutdown && this.#pending.size >= this.#options.maxPendingRequests)
            return Promise.reject(new BackendError(-10, 'Worker request capacity reached'));
        if (!Number.isSafeInteger(this.#next)) return Promise.reject(new BackendError(-4, 'Worker request ID exhausted'));
        const id = this.#next++;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => this.#stop(new BackendError(-8,
                `Worker ${method} timed out after ${timeout} ms`)), timeout);
            this.#pending.set(id, { resolve, reject, timer });
            try { this.#worker.postMessage({ id, method, args }); }
            catch (error) { clearTimeout(timer); this.#pending.delete(id); reject(error); }
        });
    }
    async init(wasmURL, config = {}, execution = { backend: 'cpu' }) {
        if (this.#ready || this.#initializing) throw new Error('Already initialized or initializing');
        this.#initializing = true;
        try {
            const result = await this.#send('init', [wasmURL == null ? undefined : String(wasmURL), config, execution]);
            if (this.#closing || this.#closed) throw new BackendError(-2, 'Worker closed during initialization');
            this.#ready = true;
            return result;
        } finally { this.#initializing = false; }
    }
    call(method, ...args) {
        if (this.#closing || this.#closed) return Promise.reject(new BackendError(-2, 'Worker closed or closing'));
        if (!this.#ready) return Promise.reject(new Error('Initialize the worker first'));
        if (!METHODS.has(method)) return Promise.reject(new Error(`Unknown worker operation: ${method}`));
        if (method !== 'reset') return this.#send(method, args);
        if (this.#resetting) return Promise.reject(new BackendError(-10, 'Reset already pending'));
        this.discardPendingTime();
        this.#resetting = true;
        return this.#send(method, args).finally(() => { this.#resetting = false; });
    }
    /** Drop pre-pause/pre-reset time explicitly and invalidate an older in-flight atlas. */
    discardPendingTime() {
        this.#discarded += this.#elapsed;
        this.#elapsed = 0;
        this.#epoch++;
    }
    async tick(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0 || seconds > 3600)
            throw new RangeError('Elapsed seconds must be in 0..3600');
        if (this.#closed || this.#closing || this.#resetting) return null;
        if (!this.#ready) throw new Error('Initialize the worker first');
        const total = this.#elapsed + seconds;
        this.#elapsed = Math.min(total, 3600);
        this.#discarded += Math.max(total - 3600, 0);
        if (this.#tick || this.#pending.size >= this.#options.maxPendingRequests) return null;
        const elapsed = this.#elapsed, epoch = this.#epoch;
        this.#elapsed = 0; this.#tick = true;
        try {
            const result = await this.#send('tick', [elapsed]);
            return epoch === this.#epoch && !this.#closing ? result : null;
        } finally { this.#tick = false; }
    }
    dispose() {
        if (this.#disposePromise) return this.#disposePromise;
        if (this.#closed) return Promise.resolve();
        this.#closing = true;
        this.discardPendingTime();
        this.#disposePromise = (async () => {
            try {
                if (this.#ready || this.#initializing)
                    await this.#send('dispose', [], this.#options.shutdownTimeoutMs, true);
            } catch {
                // Termination below is authoritative; a stuck queue cannot hold shutdown open.
            } finally { this.#stop(new BackendError(-2, 'Worker disposed')); }
        })();
        return this.#disposePromise;
    }
}
