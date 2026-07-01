# LinkedIn follow-up: the questions for the state's new witness

*Immediate follow-up to the plea post. Lead visual: `graph_galaxy_wide.png` or the live
cosmograph. This draft is based on `reports/interrogation_matlala.md`, generated from the
Madlanga evidence graph on 2026-07-01.*

---

Yesterday I posted that the man at the centre of my Madlanga Commission graph had just turned state witness.

The obvious follow-up is: what do you ask him?

This is where the graph becomes more than a picture.

I ran the record backwards. Not "where is Matlala mentioned?", which is just search. The question was sharper:

What has sworn testimony alleged about Matlala, what has Matlala himself already addressed, and what is still sitting open?

The method was simple:

1. Pull every extracted claim in the Madlanga record that mentions him.
2. Pull every extracted claim attributed to him.
3. Compare the two.
4. Surface allegations and links that the supplied record does not show him answering.

For Matlala, that produced a dossier of 3,195 claims about him and 27 statements by him. The output is not a verdict. It is a map of unresolved questions in the record.

The highest-value questions are not the broad ones. They are the ones where one answer could collapse several open threads at once.

A few the record raises:

- How was the R360-million SAPS contract awarded, who authorised it, and what role did Brown Mogotsi allegedly play in coordinating or expediting payments?
- Why was a private businessman, already under investigation, allegedly being kept informed about the disbandment of the Political Killings Task Team?
- What did Brown Mogotsi mean when, in testimony about Matlala-linked communications, the line appears: "My person is going to be a National Commissioner now"?
- What was the nature of Matlala's alleged relationship with Suliman Carim, who testimony describes as a coordinator between Matlala and the Minister?
- Did Matlala use a second identity document under the surname "Dlamini", as alleged, and if so, why?
- What was the alleged commercial relationship between Matlala and Thato Senona, the son of Maj-Gen Senona?
- Why were sensitive SAPS documents, internal screens, and officer details allegedly moving through channels connected to Matlala?

This is the difference between a search box and an evidence engine.

A search box finds mentions.

An evidence graph finds the questions the record has not closed.

(Matlala's guilty plea is a matter of court record. Everything here concerning other people is untested allegation, not a finding of fact. These are questions, not accusations.)

#MadlangaCommission #SouthAfrica #StateCapture #DataJournalism

---

## How the questions were uncovered

`scripts/interrogation_gaps.py --person "Matlala"` queries Neo4j for three slices of the evidence graph:

- Claims made about Matlala by other speakers.
- Claims stated by Matlala himself.
- Entities most often tied to Matlala by shared claims.

It then asks for open threads using only that dossier. Every question in the generated report has a day and claim-id citation, and the full source dossier is appended to `reports/interrogation_matlala.md` for checking.

Run used:

```sh
uv run --all-extras python scripts/interrogation_gaps.py --person "Matlala" --out reports/interrogation_matlala.md
```

Result:

- 3,195 allegations or claims about Matlala.
- 27 statements by Matlala.
- 30 linked entities.

## Source notes

- R360-million contract and payment coordination: Day 8, `967a510bc1`; Day 3, `cc044d5b1e`.
- PKTT disbandment communications: Day 3, `ccfe105c96`; Day 3, `1719e1c8b8`; Day 3, `86f20fa653`; Day 5, `630d451c82`.
- "My person is going to be a National Commissioner now": Day 2, `5300ba1086`.
- Suliman Carim link: Day 2, `51a6b7d75d`; Day 2, `ded69b42f0`; Day 2, `a869dad438`.
- "Dlamini" identity allegation: Day 9, `944d49c047`; Day 9, `5a15b58df7`.
- Thato Senona commercial-link allegation: Day 8, `30f56be92b`; Day 8, `cea57b70a9`.
- Sensitive SAPS documents and internal screens: Day 8, `99c424e8b1`; Day 12, `05bc2abe61`; Day 12, `5d64e16278`; Day 12, `9885e14113`; Day 48, `e136aef624`; Day 49, `e2e180dbc3`.

## Sources
- `reports/interrogation_matlala.md`, generated from the Madlanga evidence graph.
- IOL / Daily Maverick coverage, 24 to 25 June 2026, for the plea and co-accused context.
