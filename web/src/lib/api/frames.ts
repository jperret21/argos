/**
 * Binary image frames from WS /ws/frames.
 *
 * Message layout (contract v1), all little-endian:
 *   [0, 4)              uint32 N = byte length of the JSON header
 *   [4, 4+N)            UTF-8 JSON header (FrameHeader)
 *   ...                 zero padding up to pixel_offset (a multiple of 8)
 *   [pixel_offset, …)   width*height*channels uint16, row-major, interleaved
 *                       channels, row 0 = TOP of the displayed image
 *
 * decodeFrame() is zero-copy: the pixels are a Uint16Array *view* into the
 * received ArrayBuffer (the 8-byte alignment of pixel_offset makes that legal).
 */

import type { ArgosConfig } from '../config';
import { type LinkState, ReconnectingSocket, type BackoffOptions, withToken } from './socket';
import type { FrameHeader } from './types';

export interface DecodedFrame {
  header: FrameHeader;
  /** width*height*channels samples, view into the message buffer (no copy). */
  pixels: Uint16Array;
  /** Size of the whole binary message. */
  byteLength: number;
  /** Set by FrameStream: performance.now() at reception. */
  receivedAt?: number;
  /** Set by FrameStream: time spent in decodeFrame (ms). */
  decodeMs?: number;
}

export class FrameDecodeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'FrameDecodeError';
  }
}

/** True on every platform ARGOS targets (x86-64, arm64); checked, not assumed. */
export const HOST_IS_LITTLE_ENDIAN = new Uint8Array(new Uint16Array([1]).buffer)[0] === 1;

const utf8 = new TextDecoder('utf-8', { fatal: true });

function isNonNegInt(v: unknown): v is number {
  return typeof v === 'number' && Number.isInteger(v) && v >= 0;
}

function validateHeader(h: unknown): FrameHeader {
  if (typeof h !== 'object' || h === null) throw new FrameDecodeError('header is not an object');
  const r = h as Record<string, unknown>;
  if (!isNonNegInt(r.seq)) throw new FrameDecodeError('header.seq must be a non-negative integer');
  if (!isNonNegInt(r.width) || r.width === 0) throw new FrameDecodeError('header.width must be > 0');
  if (!isNonNegInt(r.height) || r.height === 0) throw new FrameDecodeError('header.height must be > 0');
  if (r.channels !== 1 && r.channels !== 3) throw new FrameDecodeError('header.channels must be 1 or 3');
  if (r.dtype !== 'uint16') throw new FrameDecodeError(`unsupported dtype ${String(r.dtype)}`);
  if (!isNonNegInt(r.pixel_offset)) throw new FrameDecodeError('header.pixel_offset must be an integer');
  return h as FrameHeader;
}

/**
 * Decode one binary frame message. Throws FrameDecodeError on any layout
 * violation (short buffer, bad JSON, misaligned or overlapping pixel_offset).
 */
export function decodeFrame(buffer: ArrayBuffer): DecodedFrame {
  const total = buffer.byteLength;
  if (total < 4) throw new FrameDecodeError(`message too short (${total} bytes)`);
  const headerLen = new DataView(buffer).getUint32(0, true);
  if (4 + headerLen > total) {
    throw new FrameDecodeError(`header length ${headerLen} exceeds message size ${total}`);
  }

  let header: FrameHeader;
  try {
    header = validateHeader(JSON.parse(utf8.decode(new Uint8Array(buffer, 4, headerLen))));
  } catch (err) {
    if (err instanceof FrameDecodeError) throw err;
    throw new FrameDecodeError(`invalid JSON header: ${(err as Error).message}`);
  }

  const offset = header.pixel_offset;
  if (offset < 4 + headerLen) throw new FrameDecodeError('pixel_offset overlaps the header');
  if (offset % 8 !== 0) throw new FrameDecodeError(`pixel_offset ${offset} is not a multiple of 8`);
  const count = header.width * header.height * header.channels;
  if (offset + count * 2 > total) {
    throw new FrameDecodeError(
      `pixel data truncated: need ${count * 2} bytes at ${offset}, message is ${total}`,
    );
  }

  let pixels: Uint16Array;
  if (HOST_IS_LITTLE_ENDIAN) {
    pixels = new Uint16Array(buffer, offset, count);
  } else {
    // Big-endian host (none in practice): byte-swap into a copy.
    const view = new DataView(buffer, offset, count * 2);
    pixels = new Uint16Array(count);
    for (let i = 0; i < count; i++) pixels[i] = view.getUint16(i * 2, true);
  }
  return { header, pixels, byteLength: total };
}

/** Build a frame message (inverse of decodeFrame): tests and local tools. */
export function encodeFrame(
  header: Omit<FrameHeader, 'pixel_offset'>,
  pixels: Uint16Array,
): ArrayBuffer {
  // pixel_offset depends on the header length, which depends on pixel_offset's
  // own digits: iterate until stable (converges in <= 2 rounds).
  let offset = 0;
  let json = '';
  for (let i = 0; i < 4; i++) {
    json = JSON.stringify({ ...header, pixel_offset: offset });
    const len = new TextEncoder().encode(json).byteLength;
    const next = Math.ceil((4 + len) / 8) * 8;
    if (next === offset) break;
    offset = next;
  }
  const jsonBytes = new TextEncoder().encode(json);
  const buf = new ArrayBuffer(offset + pixels.length * 2);
  const dv = new DataView(buf);
  dv.setUint32(0, jsonBytes.byteLength, true);
  new Uint8Array(buf, 4, jsonBytes.byteLength).set(jsonBytes);
  for (let i = 0; i < pixels.length; i++) dv.setUint16(offset + i * 2, pixels[i], true);
  return buf;
}

export interface FrameStreamOptions {
  /** Every decoded frame, with receivedAt / decodeMs filled in. */
  onFrame: (frame: DecodedFrame) => void;
  onState?: (state: LinkState) => void;
  onError?: (err: FrameDecodeError) => void;
  backoff?: BackoffOptions;
}

/**
 * Reconnecting /ws/frames client. The server already drops frames for slow
 * clients (latest-frame-wins); the viewer additionally coalesces frames that
 * arrive between two animation frames, so decoding is the only per-message
 * cost here.
 */
export class FrameStream {
  private readonly socket: ReconnectingSocket;
  private readonly opts: FrameStreamOptions;
  /** Count of messages that failed to decode (diagnostics). */
  decodeErrors = 0;

  constructor(config: ArgosConfig, options: FrameStreamOptions) {
    this.opts = options;
    this.socket = new ReconnectingSocket({
      url: withToken(`${config.wsBase}/ws/frames`, config.token),
      binaryType: 'arraybuffer',
      backoff: options.backoff,
      onMessage: (data) => this.handle(data),
      onState: (state) => options.onState?.(state),
    });
  }

  get state(): LinkState {
    return this.socket.state;
  }

  start(): void {
    this.socket.start();
  }

  stop(): void {
    this.socket.stop();
  }

  restart(): void {
    this.socket.restart();
  }

  private handle(data: unknown): void {
    if (!(data instanceof ArrayBuffer)) return; // text frames are not part of the contract
    const receivedAt = performance.now();
    let frame: DecodedFrame;
    try {
      frame = decodeFrame(data);
    } catch (err) {
      if (!(err instanceof FrameDecodeError)) throw err;
      this.decodeErrors += 1;
      this.opts.onError?.(err);
      return;
    }
    frame.receivedAt = receivedAt;
    frame.decodeMs = performance.now() - receivedAt;
    this.opts.onFrame(frame);
  }
}
