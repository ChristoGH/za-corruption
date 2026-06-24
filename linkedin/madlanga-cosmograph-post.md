# LinkedIn post — Madlanga cosmograph

*Plain-text draft (LinkedIn doesn't render markdown — copy the text between the lines as-is). Attach `video-delivery/MadlangaGraph.mp4`.*

---

I fed two days of Madlanga Commission testimony into a graph framework - and one businessman lit up as the relationship/hinge between two hearings that, on paper, have nothing to do with each other.

Like a lot of South Africans, I've found the Commission hard to follow. And sad to be confronted by the level of curruption in our country.  Hundreds of hours of "he said, she said," spread across 106 hearing days. Too much to hold in your head, let alone make sense of.   What ultimately do I want to achieve?  I don't quite know!  Seriously, I want to see unexpected details emerge. And I want to have fun doing it.

So I tried something. I took the raw transcripts and let the testimonies build a picture of itself.

A few things I want to be upfront about, because the *method* matters as much as the result:

→ This is TWO days. Day 36 and Day 43 — picked arbitrarily, 2 out of 106. A small, low-cost testable slice. Proof of method, not a verdict.

→ I didn't imposed narrative. I didn't decide who matters. The questions and answers *as they were actually spoken in the room* drove the entire layout. Entities that get discussed together sit closer together. That's it.

→ Even from two days, it already reveals structure you'd struggle to see by just reading.

THE TAXONOMY (what the nodes are)
Four kinds of node, pulled straight from the testimony: people, organisations, places, and roles (the office of "Chairperson" or "Commissioner", kept separate from whoever holds it). Size = how often something is mentioned.  Of course there can be many more types of nodes, but that is for another day.

THE ONTOLOGY (how the nodes get linked)
Every name is resolved against a master list (call it a "curated canonical store" if you want) — aliases collapse onto one identity ("Cat Matlala", "Mr Vusi Matlala", "Vusimuzi Cat Matlala" → one node), while two different people who share a surname are deliberately kept apart (no lazy surname-merging). Two entities are linked when they're spoken about together; the more often, the stronger the line. Anything named in BOTH hearings becomes a "bridge". The linking node/bridge - the one linking two separate stories together — I call the hinge.

WHAT SURFACED
The link for these two day is Vusimuzi "Cat" Matlala. And here's the part that reading either day alone won't give you: the connection resolves from the man to his companies — CAT VIP Security and Medicare 24. Medicare 24 is the single entity named across BOTH days. The corporate vehicles are how the thread actually travels between two otherwise-unconnected hearings.

I am careful here: these are ALLEGATIONS in the public record, attributed to named speakers under oath. NOT findings of fact. The graph is not meant (and doesn't) accuse anyone — it surfaces questions worth asking. For example: why does one man's company bridge surfaces  hearings that share almost no other cast?

THE STACK (and why it's open to scrutiny)
This isn't a static picture. Behind it:
• Neo4j — the graph database. Answers the structural questions: who connects whom, who's related, how many steps apart.
• Qdrant — a vector database over the testimony itself. Answers questions in plain English by context, not keywords, with every answer traceable back to day, page and speaker.

Wire those together and the corpus becomes interrogable. You can ask it things. And because every claim points back to a transcript line, anyone can check the working.

This is two days of 106. I'm building up the nerve to let it loose on the full corpus.

If you're a journalist or just a South African who cares about where this Commission goes — what would you ask it?

(Allegations in the public record, not findings of fact.)

#MadlangaCommission #SouthAfrica #GraphDatabase #Neo4j #Qdrant #KnowledgeGraph #DataJournalism #OpenData #SAPS #Accountability

---

## Notes / variants

**Hook alternatives** (first line is the scroll-stopper — swap if you prefer):
- "Two days. 106 in total. One businessman holding both together."
- "I didn't tell this graph what mattered in the Madlanga Commission. The testimony did — and it pointed at one man."

**Trim-for-length option:** if it feels long, the TAXONOMY and ONTOLOGY blocks can be merged into one "How it works" paragraph. The method + the Matlala reveal + the stack are the load-bearing parts.

**Concrete linkages you could name** (all attributed, all in the public record — use sparingly):
- Matlala ↔ Brown Mogotsi (Day 36) and Matlala ↔ EMPD (Day 43): the same man surfacing in two different rooms.
- CAT VIP Security and Medicare 24 both tying strongly to the EMPD on Day 43.
- The MOU thread: a memorandum testimony says contemplated signature by a senior police figure and Matlala.

**Compliance line to keep:** always retain an "allegations, not findings" statement. Non-negotiable given real names in a corruption context.
