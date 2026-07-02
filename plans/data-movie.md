# Plan — the data movie: the commission's evidence graph, day 1 to day 124

Status: spec. A short, cinematic animation that grows the whole evidence graph across all
hearing days, so a viewer watches the network of people, organisations and claims accrete in
real time and sees the structure form. Eye candy, deliberately, because it travels. Built on
the galaxy aesthetic already in `scripts/graph_galaxy.py`.

## The one idea

Fix the layout once, on the final 124-day graph. Then play time forward: reveal each node and
edge on the hearing day it first enters the record. Nothing jumps; the galaxy assembles itself.
The eye is drawn to where mass accumulates, and the Matlala core lights up on its own, the same
finding the static image makes, now earned over time.

## What the viewer sees evolve

- **Nodes appear** on their first-mention day, with a brief bright flash, then settle to a
  steady glow. Size grows as the cumulative claim-count rises, so hubs swell over the run.
- **Filaments accrete** between entities as shared claims accumulate; busy clusters thicken.
- **Contested ties flare** (a warm red pulse) on days a denial is logged against an existing
  link, so the viewer sees where the testimony fights, not just where it connects.
- **The core brightens** as the most-wired node (Matlala) pulls ahead, a visual of the same
  result the analysis found.
- **A day counter and date** tick in a corner; the recess gaps (December, the 104/105 break)
  show as the animation visibly pauses, which reads as real rhythm.

## Narrative arc (about 45 to 70 seconds)

1. Black. Title card: "124 hearing days. ~54,000 sworn claims. Watch the record assemble."
2. Day 1 to ~10: sparse first nodes (Mkhwanazi, Masemola, Khumalo) flash in.
3. Day 35 to 65: the network thickens; Mogotsi, Senona, Sibiya clusters form; first contested
   flares.
4. Day 100 to 124: density peaks; the Matlala core dominates.
5. Final beat: hold on the full galaxy, then a one-line card: "The man at the centre just
   turned state witness." Cut to black.
6. Mandatory foot card: "Allegations in the public record, not findings of fact."

A single restrained caption can mark two or three marquee days (e.g. "Day 47: Senona takes the
stand"), no more, or it turns into a slideshow.

## Technical approach

- **Data, one pass.** Query Neo4j for: every entity with its `first_day` (min day_no over its
  mentions) and a per-day cumulative claim-count; every entity-entity tie with the day it first
  co-occurs; and the days each tie gains a denial. (`MATCH (e)<-[:MENTIONS]-(cl)-[:SUPPORTED_BY]->(c)`
  grouped by `c.day_no`.)
- **Layout once.** Run the `graph_galaxy` spring-plus-core-pull layout on the final graph and
  freeze the positions. Stability is the whole trick.
- **Frame loop.** For `day` in 1..124, draw only elements with `first_day <= day`; ramp a
  node's brightness from a flash on its entry day down to steady over ~6 frames; scale size by
  cumulative degree to date. Render at, say, 4 to 8 frames per hearing day with easing so it
  glides rather than stutters. Reuse the nebula, starfield, dust, and bloom from `graph_galaxy`.
- **Encode.** Frames to `video-delivery/` then `ffmpeg` to MP4 (1080p or 1440p, H.264, ~30 to
  60s). Optionally a second square crop for vertical/social.
- **Audio (optional).** A quiet ambient bed; no voiceover needed. Keep it royalty-free.

## Deliverables

- `scripts/render_movie.py` (builds on `graph_galaxy.py`; emits frames + calls ffmpeg).
- `video-delivery/commission_evolution.mp4` (wide) and an optional square cut.
- The frames are regenerable and gitignored (like the other video artifacts).

## Effort and risks

- Roughly a half-day build: the data query and the freeze-then-reveal loop are the work; the
  rendering is already solved.
- Risk: layout stability (solved by computing once), frame count vs file size (tune fps), and
  the contested-flare needing per-day denial data (a second small query). All tractable.
- Performance: ~600 to 1000 frames at this scale is minutes to render, not hours.

## Honesty guardrail (same as everything else)

The motion must not imply causation or guilt. Nodes appearing near each other is co-mention,
not collusion; a contested flare is a logged denial, not a verdict. The closing card carries the
standing disclaimer. The movie dramatises the *scale and structure* of the record, never a
finding.

## Next step

Confirm the arc and length, then I build `render_movie.py` against the data queries above and
produce a first cut for review.
