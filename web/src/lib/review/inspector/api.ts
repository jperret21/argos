/**
 * The frame inspector's routes, client side of API 2 wave 7 (README rows A71-A75; contract in
 * argos/server/protocol.md "Frames (A71-A73)", "Solve and catalogue (A74, A75)").
 *
 * - A71 is binary (the `/ws/frames` layout, decoded by api/frames.ts) and is never published
 *   on `/ws/frames`: opening a frame in Review never replaces the live image (W3).
 * - A74 and A75 are jobs (`file_solve`, `file_catalogue`): the start returns the job id, the
 *   result arrives as the job's `result`; A74's last good solution is kept by the server and
 *   read again with `GET /api/files/solution` (404 when the file was never solved).
 */

import { ApiError, errorFromResponse, NETWORK_ERROR, type RequestOptions } from '../../api/client';
import { decodeFrame, type DecodedFrame } from '../../api/frames';
import type { LayerMarkers, Marker } from '../../viewer/overlay/layers';
import { LAYER_IDS, type LayerId } from '../../viewer/overlay/layers';

export interface InspectorRequest {
  request<T>(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown, options?: RequestOptions): Promise<T>;
}

/** Binary GET (A71): resolves with the body, rejects with an ApiError. */
export type BinaryFetch = (path: string, signal?: AbortSignal) => Promise<ArrayBuffer>;

/** A binary fetch over the app's config (base URL and token), as ArgosClient.jobDownload does. */
export function binaryFetch(config: { apiBase: string; token: string }, fetchImpl: typeof fetch = (i, init) => globalThis.fetch(i, init)): BinaryFetch {
  return async (path, signal) => {
    let response: Response;
    try {
      response = await fetchImpl(`${config.apiBase}${path}`, { method: 'GET', headers: { Authorization: `Bearer ${config.token}` }, signal });
    } catch (err) {
      if (signal?.aborted) throw new ApiError(0, 'aborted', 'Request cancelled');
      const detail = err instanceof Error ? err.message : String(err);
      throw new ApiError(0, NETWORK_ERROR, `Cannot reach the ARGOS server at ${config.apiBase} (${detail})`);
    }
    if (!response.ok) throw errorFromResponse(response.status, response.statusText, await response.text());
    return response.arrayBuffer();
  };
}

// -- Records -------------------------------------------------------------------------------------

/** A71's header beyond the v1 fields (the file's own). */
export interface FileFrameInfo {
  path: string | null;
  file_name: string | null;
  date_obs: string | null;
  /** Exposure midpoint (S39 rule). */
  epoch_utc: string | null;
  bayer: string | null;
  filter: string | null;
  image_type: string | null;
  object: string | null;
  /** false: converted for display (float data); measurements use the file's values. */
  raw: boolean;
}

export interface FitsCard {
  key: string;
  value: string;
  comment: string;
}

export interface FitsHeader {
  path: string;
  file_name: string;
  text: string;
  cards: FitsCard[];
  keywords: Record<string, string>;
}

export interface MeasureStarBody {
  path: string;
  x: number;
  y: number;
  radius?: number;
  snap?: boolean;
}

export interface StarMeasure {
  found: boolean;
  message: string | null;
  x: number | null;
  y: number | null;
  fwhm_px: number | null;
  hfd_px: number | null;
  fwhm_arcsec: number | null;
  hfd_arcsec: number | null;
  scale_arcsec_px: number | null;
  scale_source: 'solution' | 'profile' | null;
  eccentricity: number | null;
  snr: number | null;
  peak_adu: number | null;
  sky_adu: number | null;
  flux: number | null;
  radius_green_px: number | null;
  ra_hours: number | null;
  dec_deg: number | null;
}

export interface FileSolution {
  path: string;
  file_name: string;
  solution: {
    ra_hours: number;
    dec_deg: number;
    scale_arcsec_px: number | null;
    rotation_deg: number | null;
    mirrored: boolean;
    frame_shape: [number, number] | null;
    hint: { ra_hours: number; dec_deg: number; source: string } | null;
    solved_utc: string | null;
    summary: string;
  };
  /** FrameWcs as Field's (A43); read with viewer/hud/wcs.ts fromFrameWcs. */
  wcs: unknown;
  /** Grid as Field's (A43): polylines and labels in frame px. */
  grid: { lines: [number, number][][]; labels: { x: number; y: number; text: string; axis?: string }[] } | null;
}

export interface FileLayers {
  path: string;
  frame_shape: [number, number] | null;
  display_mag_limit: number | null;
  layers: LayerMarkers;
  counts: Partial<Record<LayerId, number>>;
  warnings: string[];
}

// -- Edge checks ---------------------------------------------------------------------------------

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);

export function fileFrameInfo(header: unknown): FileFrameInfo {
  const h = isObj(header) ? header : {};
  return {
    path: str(h.path),
    file_name: str(h.file_name),
    date_obs: str(h.date_obs),
    epoch_utc: str(h.epoch_utc),
    bayer: str(h.bayer),
    filter: str(h.filter),
    image_type: str(h.image_type),
    object: str(h.object),
    raw: h.raw !== false,
  };
}

export function parseFitsHeader(v: unknown): FitsHeader {
  if (!isObj(v) || typeof v.text !== 'string') throw new Error('Unexpected answer from GET /api/files/fits-header');
  const cards = (Array.isArray(v.cards) ? v.cards : []).filter(isObj).map((c) => ({ key: String(c.key ?? ''), value: c.value === null || c.value === undefined ? '' : String(c.value), comment: String(c.comment ?? '') }));
  const keywords: Record<string, string> = {};
  if (isObj(v.keywords)) for (const [k, val] of Object.entries(v.keywords)) if (val !== null && val !== undefined) keywords[k] = String(val);
  return { path: str(v.path) ?? '', file_name: str(v.file_name) ?? '', text: v.text, cards, keywords };
}

export function parseStarMeasure(v: unknown): StarMeasure {
  if (!isObj(v) || typeof v.found !== 'boolean') throw new Error('Unexpected answer from POST /api/files/measure-star');
  return {
    found: v.found,
    message: str(v.message),
    x: num(v.x),
    y: num(v.y),
    fwhm_px: num(v.fwhm_px),
    hfd_px: num(v.hfd_px),
    fwhm_arcsec: num(v.fwhm_arcsec),
    hfd_arcsec: num(v.hfd_arcsec),
    scale_arcsec_px: num(v.scale_arcsec_px),
    scale_source: v.scale_source === 'solution' || v.scale_source === 'profile' ? v.scale_source : null,
    eccentricity: num(v.eccentricity),
    snr: num(v.snr),
    peak_adu: num(v.peak_adu),
    sky_adu: num(v.sky_adu),
    flux: num(v.flux),
    radius_green_px: num(v.radius_green_px),
    ra_hours: num(v.ra_hours),
    dec_deg: num(v.dec_deg),
  };
}

export function parseFileSolution(v: unknown): FileSolution | null {
  if (!isObj(v) || !isObj(v.solution)) return null;
  const s = v.solution;
  const ra = num(s.ra_hours);
  const dec = num(s.dec_deg);
  if (ra === null || dec === null) return null;
  const shape = Array.isArray(s.frame_shape) && s.frame_shape.length === 2 ? ([Number(s.frame_shape[0]), Number(s.frame_shape[1])] as [number, number]) : null;
  const hint = isObj(s.hint) && num(s.hint.ra_hours) !== null ? { ra_hours: num(s.hint.ra_hours)!, dec_deg: num(s.hint.dec_deg) ?? 0, source: str(s.hint.source) ?? 'header' } : null;
  let grid: FileSolution['grid'] = null;
  if (isObj(v.grid)) {
    const lines = Array.isArray(v.grid.lines) ? (v.grid.lines as [number, number][][]) : Array.isArray(v.grid.polylines) ? (v.grid.polylines as [number, number][][]) : [];
    const labels = Array.isArray(v.grid.labels) ? (v.grid.labels as NonNullable<FileSolution['grid']>['labels']) : [];
    grid = { lines, labels };
  }
  return {
    path: str(v.path) ?? '',
    file_name: str(v.file_name) ?? '',
    solution: {
      ra_hours: ra,
      dec_deg: dec,
      scale_arcsec_px: num(s.scale_arcsec_px),
      rotation_deg: num(s.rotation_deg),
      mirrored: s.mirrored === true,
      frame_shape: shape,
      hint,
      solved_utc: str(s.solved_utc),
      summary: str(s.summary) ?? '',
    },
    wcs: v.wcs ?? null,
    grid,
  };
}

/** A75's FileLayers; tolerates a flat `markers: [{layer, …}]` list too. */
export function parseFileLayers(v: unknown): FileLayers | null {
  if (!isObj(v)) return null;
  const layers: Partial<Record<LayerId, Marker[]>> = {};
  if (isObj(v.layers)) {
    for (const id of LAYER_IDS) {
      const list = v.layers[id];
      if (Array.isArray(list)) layers[id] = list.filter((m): m is Marker => isObj(m) && num(m.x) !== null && num(m.y) !== null);
    }
  } else if (Array.isArray(v.markers)) {
    for (const m of v.markers) {
      if (!isObj(m) || !(LAYER_IDS as readonly string[]).includes(String(m.layer)) || num(m.x) === null || num(m.y) === null) continue;
      const id = m.layer as LayerId;
      (layers[id] ??= []).push(m as unknown as Marker);
    }
  }
  const counts: Partial<Record<LayerId, number>> = {};
  if (isObj(v.counts)) for (const id of LAYER_IDS) if (num(v.counts[id]) !== null) counts[id] = num(v.counts[id])!;
  for (const id of LAYER_IDS) if (counts[id] === undefined && layers[id]) counts[id] = layers[id]!.length;
  const catalog = isObj(v.catalog) ? v.catalog : {};
  const warnings = Array.isArray(catalog.warnings) ? catalog.warnings.filter((w): w is string => typeof w === 'string') : [];
  const shape = Array.isArray(v.frame_shape) && v.frame_shape.length === 2 ? ([Number(v.frame_shape[0]), Number(v.frame_shape[1])] as [number, number]) : null;
  return { path: str(v.path) ?? '', frame_shape: shape, display_mag_limit: num(v.display_mag_limit), layers, counts, warnings };
}

const q = (path: string) => `path=${encodeURIComponent(path)}`;

export class InspectorApi {
  constructor(
    private readonly client: InspectorRequest,
    private readonly binary: BinaryFetch,
  ) {}

  /** A71: the frame, decoded (throws FrameDecodeError on a malformed message). */
  async frame(path: string, signal?: AbortSignal): Promise<DecodedFrame> {
    return decodeFrame(await this.binary(`/api/files/frame?${q(path)}&view=raw`, signal));
  }

  /** A72. */
  async header(path: string, signal?: AbortSignal): Promise<FitsHeader> {
    return parseFitsHeader(await this.client.request<unknown>('GET', `/api/files/fits-header?${q(path)}`, undefined, { signal }));
  }

  /** A73: `found: false` is a 200 with the core's message. */
  async measure(body: MeasureStarBody, signal?: AbortSignal): Promise<StarMeasure> {
    return parseStarMeasure(await this.client.request<unknown>('POST', '/api/files/measure-star', body, { signal }));
  }

  /** A74: start the `file_solve` job. */
  async solve(path: string): Promise<{ job_id: string; job: unknown }> {
    const v = await this.client.request<unknown>('POST', '/api/files/solve', { path });
    if (!isObj(v) || typeof v.job_id !== 'string') throw new Error('Unexpected answer from POST /api/files/solve');
    return { job_id: v.job_id, job: v.job };
  }

  /** A74: the last good solution the server kept for this file, or null (404). */
  async solution(path: string, signal?: AbortSignal): Promise<FileSolution | null> {
    try {
      return parseFileSolution(await this.client.request<unknown>('GET', `/api/files/solution?${q(path)}`, undefined, { signal }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  }

  /** A75: start the `file_catalogue` job (409 not_solved without a kept solution). */
  async catalogue(path: string): Promise<{ job_id: string; job: unknown }> {
    const v = await this.client.request<unknown>('POST', '/api/files/catalogue', { path });
    if (!isObj(v) || typeof v.job_id !== 'string') throw new Error('Unexpected answer from POST /api/files/catalogue');
    return { job_id: v.job_id, job: v.job };
  }
}
