// Typed client for the read-only commission API. Types mirror the FastAPI
// Pydantic schemas in apps/api/app/schemas. The base URL is configured at build
// time via VITE_API_BASE (defaults to the local API).

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export interface SearchHit {
  score: number;
  chunk_id: string;
  source_url: string;
  commission_slug: string | null;
  commission_name: string | null;
  day_no: number | null;
  date: string | null;
  page_start: number | null;
  page_end: number | null;
  authoritative: boolean;
  speakers: string[];
  snippet: string;
}

export interface SearchResponse {
  query: string;
  count: number;
  hits: SearchHit[];
}

export interface Mentions {
  person: string[];
  org: string[];
  place: string[];
}

// A claim attached to a chunk. status is the stored value (never synthesised);
// speaker is the STATED_BY attribution; speaker_unresolved flags a raw,
// uncanonicalised speaker (ADR 0007).
export interface ClaimBrief {
  claim_id: string;
  status: string;
  speaker: string;
  speaker_unresolved: boolean;
  quote: string | null;
  text: string | null;
}

export interface ChunkGraph {
  chunk_id: string;
  text: string | null;
  commission_slug: string | null;
  day_no: number | null;
  date: string | null;
  page_start: number | null;
  page_end: number | null;
  source_url: string | null;
  authoritative: boolean | null;
  mentions: Mentions;
  speakers: string[];
  claims: ClaimBrief[];
}

export interface ClaimMention {
  name: string;
  role: string | null;
  labels: string[];
}

export interface ClaimDetail {
  claim_id: string;
  status: string;
  speaker: string;
  speaker_unresolved: boolean;
  quote: string | null;
  text: string | null;
  certainty: string | null;
  attribution: string | null;
  chunk_id: string | null;
  day_no: number | null;
  page_start: number | null;
  page_end: number | null;
  source_url: string | null;
  mentions: ClaimMention[];
}

async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`);
  if (!resp.ok) {
    throw new Error(`${resp.status} ${resp.statusText} for ${path}`);
  }
  return (await resp.json()) as T;
}

export function search(
  q: string,
  opts: { commission?: string; day?: number; speaker?: string; limit?: number } = {},
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q });
  if (opts.commission) params.set("commission", opts.commission);
  if (opts.day != null) params.set("day", String(opts.day));
  if (opts.speaker) params.set("speaker", opts.speaker);
  if (opts.limit != null) params.set("limit", String(opts.limit));
  return getJSON<SearchResponse>(`/search?${params.toString()}`);
}

export function chunkGraph(chunkId: string): Promise<ChunkGraph> {
  return getJSON<ChunkGraph>(`/chunk/${encodeURIComponent(chunkId)}/graph`);
}

export function claimDetail(claimId: string): Promise<ClaimDetail> {
  return getJSON<ClaimDetail>(`/claim/${encodeURIComponent(claimId)}`);
}
