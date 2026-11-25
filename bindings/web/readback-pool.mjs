import { BackendError } from './gpu-protocol.mjs';

/** Bounded staging-buffer reuse. This manages transfers, not fluid computation.
 * Every read returns an owned ArrayBuffer. A busy/closed pool never submits work.
 * Timeout is fail-stop: a stalled device is not silently replaced with CPU.
 */
export class ReadbackPool {
    constructor(device, { capacity = 2, timeoutMs = 15000, onFailure = () => {} } = {}) {
        if (!Number.isInteger(capacity) || capacity < 1 || capacity > 8 ||
            !Number.isFinite(timeoutMs) || timeoutMs < 1) throw new RangeError('Invalid readback pool limits');
        this.device = device;
        this.capacity = capacity;
        this.timeoutMs = timeoutMs;
        this.onFailure = onFailure;
        this.slots = [];
        this.closed = false;
        this.counts = { allocations: 0, reuses: 0, completed: 0, failures: 0,
            bytesCopied: 0, peakPending: 0, peakAllocatedBytes: 0 };
    }
    get pending() { return this.slots.filter(slot => slot.busy).length; }
    get stats() {
        return Object.freeze({ ...this.counts, pending: this.pending,
            allocatedBytes: this.slots.reduce((sum, slot) => sum + slot.buffer.size, 0),
            buffers: this.slots.length, capacity: this.capacity });
    }
    _reserve(bytes) {
        if (this.closed) throw new BackendError(-2, 'Readback pool disposed');
        if (this.pending >= this.capacity) throw new BackendError(-10, 'Readback capacity reached');
        let slot = this.slots.filter(s => !s.busy && s.buffer.size >= bytes)
            .sort((a, b) => a.buffer.size - b.buffer.size)[0];
        if (slot) this.counts.reuses++;
        else {
            // Grow an idle slot instead of letting differently-sized requests expand the pool.
            slot = this.slots.find(s => !s.busy);
            const buffer = this.device.createBuffer({ label: 'vapor-pooled-readback', size: bytes,
                usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
            if (slot) { slot.buffer.destroy(); slot.buffer = buffer; }
            else { slot = { buffer, busy: false, abort: null }; this.slots.push(slot); }
            this.counts.allocations++;
        }
        slot.busy = true;
        this.counts.peakPending = Math.max(this.counts.peakPending, this.pending);
        this.counts.peakAllocatedBytes = Math.max(this.counts.peakAllocatedBytes, this.stats.allocatedBytes);
        return slot;
    }
    async read(regions, encodeBeforeCopy = null) {
        if (this.closed) throw new BackendError(-2, 'Readback pool disposed');
        let bytes = 0;
        for (const [buffer, size] of regions) {
            if (!Number.isSafeInteger(size) || size <= 0 || size % 4 || size > buffer.size)
                throw new BackendError(-1, 'Invalid readback region');
            bytes += size;
        }
        if (!bytes || !Number.isSafeInteger(bytes) || bytes > this.device.limits.maxBufferSize)
            throw new BackendError(-4, 'Readback exceeds buffer budget');
        const slot = this._reserve(bytes);
        let timer;
        try {
            const encoder = this.device.createCommandEncoder({ label: 'vapor-snapshot' });
            encodeBeforeCopy?.(encoder);
            let offset = 0;
            for (const [source, size] of regions) {
                encoder.copyBufferToBuffer(source, 0, slot.buffer, offset, size);
                offset += size;
            }
            this.device.queue.submit([encoder.finish()]);
            const cancelled = new Promise((_, reject) => {
                slot.abort = reject;
                timer = setTimeout(() => reject(new BackendError(-8,
                    `GPU readback exceeded ${this.timeoutMs} ms; recreate the simulation`)), this.timeoutMs);
            });
            await Promise.race([slot.buffer.mapAsync(GPUMapMode.READ, 0, bytes), cancelled]);
            if (this.closed) throw new BackendError(-2, 'Readback pool disposed');
            const result = slot.buffer.getMappedRange(0, bytes).slice(0, bytes);
            this.counts.completed++;
            this.counts.bytesCopied += bytes;
            return result;
        } catch (cause) {
            const error = cause instanceof BackendError ? cause :
                new BackendError(-8, `GPU readback failed: ${cause.message ?? cause}`);
            this.counts.failures++;
            if (!this.closed && error.code !== -2) {
                // A failed mapping is not a reusable slot. Recreating the simulation is explicit.
                slot.buffer.destroy();
                this.slots = this.slots.filter(s => s !== slot);
                this.onFailure(error);
            }
            throw error;
        } finally {
            clearTimeout(timer);
            slot.abort = null;
            slot.buffer.unmap();
            slot.busy = false;
        }
    }
    dispose() {
        if (this.closed) return;
        this.closed = true;
        for (const slot of this.slots) {
            slot.abort?.(new BackendError(-2, 'Readback pool disposed'));
            slot.buffer.destroy();
        }
        this.slots = [];
    }
}
