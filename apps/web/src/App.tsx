import { useState } from "react";
import {
  search,
  chunkGraph,
  claimDetail,
  type SearchHit,
  type ChunkGraph,
  type ClaimBrief,
  type ClaimDetail,
} from "./api";

// One read-only page: search box -> results list -> detail panel. useState only,
// no router, no state library. Mentions (leads) and claims (attributed
// allegations) are rendered with visibly different treatment and never merged.

function pages(start: number | null, end: number | null): string {
  if (start == null) return "p. n/a";
  return end != null && end !== start ? `pp. ${start}-${end}` : `p. ${start}`;
}

function ResultRow(props: { hit: SearchHit; active: boolean; onClick: () => void }) {
  const { hit, active, onClick } = props;
  return (
    <button className={`result-row${active ? " active" : ""}`} onClick={onClick}>
      <div className="result-meta">
        <span className="commission">{hit.commission_slug ?? "?"}</span>
        <span>day {hit.day_no ?? "?"}{hit.date ? ` (${hit.date})` : ""}</span>
        <span>{pages(hit.page_start, hit.page_end)}</span>
        {!hit.authoritative && <span className="flag">non-authoritative</span>}
      </div>
      <div className="speakers">{hit.speakers.join(", ") || "no speaker label"}</div>
      <div className="snippet">{hit.snippet}</div>
      <a className="source" href={hit.source_url} target="_blank" rel="noreferrer"
         onClick={(e) => e.stopPropagation()}>
        official source
      </a>
    </button>
  );
}

function MentionsBlock(props: { graph: ChunkGraph }) {
  const { mentions } = props.graph;
  const groups: [string, string[]][] = [
    ["People", mentions.person],
    ["Organisations", mentions.org],
    ["Places", mentions.place],
  ];
  return (
    <section className="mentions">
      <h3>
        Mentioned here{" "}
        <span className="badge badge-mention">mentioned: a lead, not a finding</span>
      </h3>
      {groups.map(([label, names]) => (
        <div key={label} className="mention-group">
          <span className="mention-label">{label}</span>
          {names.length ? (
            <ul>{names.map((n) => <li key={n}>{n}</li>)}</ul>
          ) : (
            <span className="empty">none</span>
          )}
        </div>
      ))}
    </section>
  );
}

function ClaimCard(props: { claim: ClaimBrief; sourceUrl: string | null; onOpen: () => void }) {
  const { claim, sourceUrl, onOpen } = props;
  return (
    <article className="claim-card" onClick={onOpen}>
      <div className="claim-head">
        <span className="badge badge-claim">{claim.status}</span>
        <span className="stated-by">
          stated by {claim.speaker}
          {claim.speaker_unresolved && (
            <span className="badge badge-raw" title="raw, uncanonicalised speaker">
              unverified speaker
            </span>
          )}
        </span>
      </div>
      {claim.quote && <blockquote className="quote">{claim.quote}</blockquote>}
      {claim.text && <p className="predicate">{claim.text}</p>}
      {sourceUrl && (
        <a href={sourceUrl} target="_blank" rel="noreferrer"
           onClick={(e) => e.stopPropagation()}>
          official source
        </a>
      )}
    </article>
  );
}

function ClaimDetailPanel(props: { detail: ClaimDetail; onClose: () => void }) {
  const { detail, onClose } = props;
  return (
    <div className="claim-detail">
      <button className="close" onClick={onClose}>close</button>
      <div className="claim-head">
        <span className="badge badge-claim">{detail.status}</span>
        <span className="stated-by">
          stated by {detail.speaker}
          {detail.speaker_unresolved && (
            <span className="badge badge-raw">unverified speaker</span>
          )}
        </span>
      </div>
      {detail.quote && <blockquote className="quote">{detail.quote}</blockquote>}
      {detail.text && <p className="predicate">{detail.text}</p>}
      <dl className="provenance">
        <dt>day</dt><dd>{detail.day_no ?? "?"}</dd>
        <dt>page</dt><dd>{pages(detail.page_start, detail.page_end)}</dd>
        <dt>certainty</dt><dd>{detail.certainty ?? "n/a"}</dd>
        <dt>attribution</dt><dd>{detail.attribution ?? "n/a"}</dd>
      </dl>
      {detail.mentions.length > 0 && (
        <div className="claim-mentions">
          <span className="mention-label">Names in this claim</span>
          <ul>
            {detail.mentions.map((m) => (
              <li key={`${m.name}:${m.role}`}>
                {m.name}{m.role ? ` (${m.role})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {detail.source_url && (
        <a href={detail.source_url} target="_blank" rel="noreferrer">official source</a>
      )}
    </div>
  );
}

export function App() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [activeChunk, setActiveChunk] = useState<string | null>(null);
  const [graph, setGraph] = useState<ChunkGraph | null>(null);
  const [claim, setClaim] = useState<ClaimDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    setGraph(null);
    setClaim(null);
    setActiveChunk(null);
    try {
      const resp = await search(query.trim(), { limit: 20 });
      setHits(resp.hits);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function openChunk(chunkId: string) {
    setActiveChunk(chunkId);
    setClaim(null);
    setError(null);
    try {
      setGraph(await chunkGraph(chunkId));
    } catch (err) {
      setError(String(err));
    }
  }

  async function openClaim(claimId: string) {
    setError(null);
    try {
      setClaim(await claimDetail(claimId));
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Commission Transcript Intelligence</h1>
        <form onSubmit={runSearch}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder='e.g. "disbanding of the task team"'
            aria-label="search query"
          />
          <button type="submit" disabled={busy}>{busy ? "searching…" : "search"}</button>
        </form>
      </header>

      {error && <div className="error">{error}</div>}

      <main>
        <section className="results">
          {hits.map((hit) => (
            <ResultRow
              key={hit.chunk_id}
              hit={hit}
              active={hit.chunk_id === activeChunk}
              onClick={() => openChunk(hit.chunk_id)}
            />
          ))}
          {!hits.length && !busy && <p className="empty">No results yet. Run a search.</p>}
        </section>

        <section className="detail">
          {graph ? (
            <>
              <MentionsBlock graph={graph} />
              <section className="claims">
                <h3>
                  Claims on this passage{" "}
                  <span className="badge badge-claim">attributed testimony</span>
                </h3>
                {graph.claims.length ? (
                  graph.claims.map((c) => (
                    <ClaimCard
                      key={c.claim_id}
                      claim={c}
                      sourceUrl={graph.source_url}
                      onOpen={() => openClaim(c.claim_id)}
                    />
                  ))
                ) : (
                  <p className="empty">No claims recorded on this passage.</p>
                )}
              </section>
              {claim && <ClaimDetailPanel detail={claim} onClose={() => setClaim(null)} />}
            </>
          ) : (
            <p className="empty">Select a result to see its evidence neighborhood.</p>
          )}
        </section>
      </main>

      <footer>
        Allegations in the public record, attributed to named speakers under oath,
        not findings of fact.
      </footer>
    </div>
  );
}
