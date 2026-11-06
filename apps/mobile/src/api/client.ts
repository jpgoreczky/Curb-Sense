import { env } from "../config/env";
import type { BBox, PinClusterResponse, PinSummary } from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`API ${status}: ${detail}`);
  }
}

async function getJson<T>(path: string, params: Record<string, string | number>, signal?: AbortSignal): Promise<T> {
  const query = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
  const response = await fetch(`${env.apiUrl}${path}?${query}`, { signal });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = JSON.stringify((await response.json()).detail ?? detail);
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

const bboxParams = ([min_lon, min_lat, max_lon, max_lat]: BBox) => ({ min_lon, min_lat, max_lon, max_lat });

export function fetchPins(bbox: BBox, signal?: AbortSignal): Promise<PinSummary[]> {
  return getJson<PinSummary[]>("/pins", bboxParams(bbox), signal);
}

export function fetchPinClusters(bbox: BBox, zoom: number, signal?: AbortSignal): Promise<PinClusterResponse> {
  return getJson<PinClusterResponse>("/pins/clusters", { ...bboxParams(bbox), zoom }, signal);
}
