# LinkedIn — Series A, Post #2: the hinge at full scale

*Plain-text draft (LinkedIn doesn't render markdown — copy the text between the lines). Builds on Post #1 (the 2-day cosmograph). Lead visual: a bar chart of "days named" for the top figures, with the procedural cast (Chair + evidence-leading SCs) greyed out so Matlala visibly tops the actual subjects. Alt visual: the full-corpus cosmograph.*

---

My first cut of this used two days of Madlanga Commission testimony — two arbitrary days out of 106. One businessman lit up as the unlikely link between two hearings that looked unrelated. I said I'd need more nerve to run the full corpus.

I ran the full corpus.

All 106 hearing days. 14,783 passages of testimony. Nearly 49,000 individual claims pulled out and wired into a knowledge graph — every one tied back to who said it, on what day, on what page.

The businessman didn't shrink. He grew.

Vusimuzi "Cat" Matlala is named on 62 of the 106 hearing days.

Let that land. Not two days. Sixty-two.

Now, the careful part — because this matters. The only people named across more days than him are the people *running* the inquiry: the Chairperson, Justice Madlanga (100 days), and the senior advocates leading evidence (96 days each). They're there by function — they speak every single day. Strip out the cast running the commission, and Matlala is the most-named figure in the entire proceedings: ahead of the generals, ahead of the national commissioner, ahead of the police minister.

His companies trail him through it — Medicare 24 surfaces on 32 days, CAT VIP Security on 26.

Here's what I want to be just as clear about: this is not a finding of guilt. It's a map of who the testimony keeps returning to. A name appearing often is a question, not a verdict. Everything here is allegation in the public record, attributed to named people under oath — never a finding of fact. The graph doesn't accuse anyone. It shows you where to look.

How it works, briefly. I never told the system who mattered. Every name was extracted from the transcripts and resolved against a curated identity store — so "Cat Matlala", "Mr Vusi Matlala" and "Vusimuzi Cat Matlala" collapse into one person, while two different Khumalos are deliberately kept apart. People, organisations and places are then linked wherever the testimony discusses them together. A graph database (Neo4j) holds the connections; a vector database (Qdrant) makes the testimony semantically searchable. No narrative is imposed — the questions and answers, exactly as they were spoken in the room, drive the entire picture.

Two days was a teaser. 106 days is the real thing — and this is only the first finding.

Next up: which hearing days exist only as YouTube video and never made it into the searchable public record — and which days the key players actually took the stand.

If you're a journalist, or just a South African who cares where this commission lands — what would you ask a system that holds all 106 days in its head at once?

(Allegations in the public record, not findings of fact. Method open to scrutiny.)

#MadlangaCommission #SouthAfrica #Neo4j #Qdrant #KnowledgeGraph #DataJournalism #StateCapture #Accountability #SAPS

---

## Notes & variants

**Hook alternatives** (swap line 1):
- "Two days of testimony made one businessman look important. All 106 days made him unavoidable."
- "I was too nervous to run the whole commission through my graph. So I ran it. Here's what 106 days say that two days only hinted at."

**The load-bearing honesty (keep it):** the procedural-vs-subject distinction is what makes the claim rigorous and defensible. Don't drop it — a sharp reader (or a lawyer) will note that the Chair and counsel top any raw mention count, and pre-empting that is exactly what earns trust. "Most-named *non-procedural* figure" is the precise, true claim.

**Numbers used (all from the live graph, verifiable):** 106 days · 14,783 chunks · ~49,000 claims · Matlala 62 days / 1,722 chunks · Medicare 24 32 days · CAT VIP 26 days · Madlanga 100 · evidence-leading SCs 96 · Sibiya 47 · Masemola 31 · Mogotsi 29 · Mchunu 28.

**Lead visual to build:** horizontal bar chart, "Hearing days named (of 106)", top ~12 people. Grey/hatch the three procedural roles (Madlanga, the two SCs) and label them "present by function"; colour Matlala gold; the gap between him and the next subject (Sibiya, 47) is the story. This single chart carries the post.

**Compliance line to keep:** always retain the "allegation in the public record, not a finding of fact" statement — non-negotiable with named individuals.

**Series placement:** Post #2 of Series A ("we scaled it"). Post #3 = the coverage map (transcript vs YouTube-only days). Series B (evidentiary states) is the separate, later arc — see plans/evidentiary-completeness-track.md.
