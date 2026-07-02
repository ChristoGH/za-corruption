# LinkedIn follow-up: the questions for the state's new witness

*Immediate follow-up to the plea post. Lead visual: `graph_galaxy_wide.png` (or the Neo4j
Browser screenshot as a second image / carousel). Built from `reports/interrogation_matlala.md`,
generated 2026-07-01. Revised: hook reordered, names corrected, "my person" de-attributed,
disclaimer added, method moved to a first comment.*

---

3,195 sworn claims name one man. He has answered 27 of them.

That man is Vusimuzi "Cat" Matlala. In my last post he had just turned state witness, and the question I kept getting back was the obvious one: so what do you ask him? Or put differently, which questions has the record never closed, or never even asked?

The Madlanga Commission (properly, the Judicial Commission of Inquiry into Alleged Criminality, Political Interference and Corruption in the Criminal Justice System) has me thinking about this daily, not for the revelations alone, but for what graph technology paired with an LLM can do to a record this size. I don't impose myself on the extraction or its direction. Every name and claim is pulled from the record by code, disambiguated, and strung together; I only bring a feel for what might be worth a look. At arm's length. And so far the insight is nothing short of astonishing.

So I ran the record backwards. Not "where is Matlala mentioned", which is just search, but: what has sworn testimony alleged about him, what has he himself already addressed, and what is still sitting open?

The method was:

1. Pull every extracted claim in the Madlanga record that mentions him.
2. Pull every extracted claim attributed to him.
3. Compare the two.
4. Surface the allegations and links the record does not show him answering.

That is the 3,195 against 27: a large map of unresolved questions, drawn purely from who said what.

The highest-value questions are not the broad, fuzzy ones. They are the ones where a single answer could collapse several open threads at once. To me, that is the profound part.

A few the record raises:

- How was the R360-million SAPS contract awarded, who authorised it, and what role did Brown Mogotsi allegedly play in coordinating or expediting payments?
- About six hours before the minister's letter disbanding the Political Killings Task Team was signed on 31 December 2024, Brown Mogotsi allegedly messaged Matlala, an accused man under investigation: "today is the day and Matlala should just stand back." Why did he get advance word?
- The testimony surfaces the line "My person is going to be a National Commissioner now." Whose person, and on whose authority?
- What was the nature of Matlala's alleged relationship with Suleiman Carrim, described in testimony as a go-between with the Minister?
- Did Matlala use a second identity document under the surname "Dlamini", as alleged, and if so, why?
- What was the alleged commercial relationship between Matlala and Thato Senona, son of Maj-Gen Senona?
- Why were sensitive SAPS documents and officer details allegedly moving through channels connected to Matlala?

None of this is a finding. It is the shape of the record: high-uncertainty claims sitting inside one man's knowledge, and he has now agreed to talk.

(Matlala's guilty plea is a matter of court record. Everything here concerning other people is untested allegation, not a finding of fact. These are questions, not accusations.)

#MadlangaCommission #SouthAfrica #StateCapture #DataJournalism

---

## First comment (paste as the first comment on the post)

How the questions were uncovered. `scripts/interrogation_gaps.py --person "Matlala"` pulls three slices from the graph: claims made about Matlala by others, claims stated by Matlala himself, and the entities most tied to him by shared claims. It then surfaces the open threads from that dossier alone. Every question in the generated report carries a day and claim-id citation, and the full source dossier is appended for checking. Totals: 3,195 allegations, 27 statements, 30 linked entities.

Source notes (day, claim-id):
- R360m contract and payment coordination: Day 8, 967a510bc1; Day 3, cc044d5b1e.
- PKTT disbandment communications: Day 3, ccfe105c96 / 1719e1c8b8 / 86f20fa653; Day 5, 630d451c82.
- "Today is the day and Matlala should just stand back" (about six hours before the letter was signed): Day 35, d808c8b74e; Day 37, 9041d9e850.
- "My person is going to be a National Commissioner now": Day 2, 5300ba1086 (quoted in testimony by Lt-Gen Mkhwanazi; revisited Day 123).
- Carrim link: Day 2, 51a6b7d75d / ded69b42f0 / a869dad438.
- "Dlamini" identity allegation: Day 9, 944d49c047 / 5a15b58df7.
- Thato Senona commercial-link allegation: Day 8, 30f56be92b / cea57b70a9.
- Sensitive SAPS documents: Day 8, 99c424e8b1; Day 12, 5d64e16278 / 9885e14113; Day 48, e136aef624; Day 49, e2e180dbc3.

Sources: reports/interrogation_matlala.md (from the Madlanga evidence graph); IOL and Daily Maverick coverage, 24 to 25 June 2026, for the plea and co-accused context.
