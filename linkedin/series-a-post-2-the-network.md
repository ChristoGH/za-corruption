# LinkedIn — Series A, Post #2 (NETWORK + TEMPORAL angle — supersedes the mention-count draft)

*Plain-text draft. Lead visual: `linkedin/matlala_web.svg` (the alleged-network ego graph). All figures from `scripts/association_analysis.py` over the full corpus — VERIFY the day-density + Senona numbers against the live Neo4j graph before publishing (the graph's NER catches a few more surface variants than the seed-only script).*

---

I stopped counting who gets *mentioned* in the Madlanga Commission. Counts are boring — and worse, they lie. The chairperson and the advocates appear on nearly every day, so a mention-ranking just lists the people *running* the inquiry.

So I asked the graph a sharper question. Across all 106 hearing days and ~49,000 sworn claims: who does the testimony keep tying to one businessman — Vusimuzi "Cat" Matlala?

Not who's in the room. Who's in the story.

Three things fell out.

➊ He comes in waves. Matlala isn't steady background — there are days the hearing is largely about him. Day 65: 119 separate passages of testimony. Day 75: 105. Days 48 and 54 close behind. He appears early (day 9) and the commission keeps circling back to him for the rest of its run.

➋ The mention-counts hid a name. Strip out the ever-present advocates and rank each figure by how *specifically* the record ties them to Matlala — and the standout isn't a household name. It's a senior police general: Maj-Gen Senona. By three independent measures — shared passages, shared claims, and who actually testifies about Matlala — Senona sits closer to him than almost anyone in the proceedings. The headlines miss him. The structure of the testimony does not.

➌ The web has a shape. Weight every connection by the claims themselves — sworn statements that name both parties — and a cluster resolves: Matlala, his companies (Medicare 24, CAT VIP Security), Brown Mogotsi, and generals Senona, Shibiri and Sibiya — reaching outward to the Political Killings Task Team, Police Minister Senzo Mchunu, and IPID.

[ attach: matlala_web.svg ]

Now the part that must be said plainly: this is not a finding of guilt, and "associated" does not mean "friends" or "accomplices." The graph shows who the *testimony* repeatedly discusses together — a senior officer named alongside Matlala could be an accuser just as easily as an ally. This is a map of where to look. A question, not a verdict. Every line in that picture is an allegation in the public record, attributed to named people under oath — never a finding of fact.

That's the difference between a frequency list and an investigation: one tells you who's loud; the other tells you who's load-bearing.

106 days. ~49,000 claims. One graph that holds them all at once.

If you're a journalist working this story — which thread would you pull first?

(Method open to scrutiny. Allegations in the public record, not findings of fact.)

#MadlangaCommission #SouthAfrica #Neo4j #Qdrant #KnowledgeGraph #DataJournalism #StateCapture #Accountability #SAPS

---

## Findings behind the post (from scripts/association_analysis.py, full corpus)

- **Temporal surge days (chunks naming Matlala):** day 65 (119), 75 (105), 48 (94), 54 (92), 9 (83), 55 (76), 73 (75), 53 (73), 66 (62), 47 (60). He enters early and recurs in waves — not evenly spread.
- **Distinctive associates (lift — co-occurrence normalised against overall frequency, so the always-present cast drops out):** Medicare 24 (3.8), Maj-Gen Senona (3.8), Brown Mogotsi (3.5), Lt-Gen Shibiri (2.2), Adv Pooe (2.1), Sibiya (1.8), CAT VIP (1.8). Contrast the *raw* top co-occurrence, which is just the advocates (Baloyi, Hassim, Chaskalson) — i.e. noise.
- **Alleged-network (entities sharing a CLAIM with Matlala):** Senona (308), Mogotsi (247), Shibiri (182), Sibiya (171), SAPS (166), N. Mkhwanazi (44), Political Killings Task Team (38), Medicare 24 (35), JD Mkhwanazi (24), Mchunu (24), IPID (23), CAT VIP (11).
- **Who testifies about Matlala (speaker → #claims):** Maj-Gen Senona (300), Adv Chaskalson SC (283), WITNESS C (253), Lt-Gen Dumisani Khumalo (248), Adv Hassim SC (236), MR CARRIM (205), Brigadier Matjeng (176).

**The discovery to lead with:** Maj-Gen Senona — top by *all three* structural measures, yet invisible in a simple mention ranking. That's the post's hook.

## Notes
- "Friends with the protagonist" can't be answered by co-occurrence alone — co-mention is neutral (accuser vs ally). Friend-vs-foe needs the **stance/sentiment layer** (Track B, `plans/evidentiary-completeness-track.md`). That's the natural next escalation and its own post.
- Verify-before-publish: confirm Senona's role from the public record (don't assert who he is beyond "a senior police general the testimony ties tightly to Matlala"); confirm day-density numbers against the live graph.
