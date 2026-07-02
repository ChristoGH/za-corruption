# LinkedIn — Series A, Post #2 · FINAL (publish-ready)

*Plainer rewrite: numbered-reveal structure dropped, single disclaimer, artifacts removed, hashtags trimmed. Lead visual: screen-record of `matlala_live_cosmograph.html` (~20s: settle, click Senona, click Medicare 24). Numbers verified against the live graph (queries below) before posting.*

---

A while back I built a small graph from two days of Madlanga Commission testimony - graph being the network of entities.  I reckon a graph is the way to make sense of the vast amount of information One businessman kept turning up as the link between hearings that LOOKED unrelated. I wanted to know whether that held across the whole record, so I ran all 106 hearing days through it.

Well it seems it did.  Vusimuzi "Cat" Matlala was named on 62 of the 106 hearing days. The only people named on more days are the 'functionaries', the chairperson and the evidence leaders. Take them out and he is the most-named person in the proceedings thus far, ahead of the generals, the national commissioner and the police minister. And two company names trail him through all of it, Medicare 24 on 32 days and CAT VIP Security on 26.

The counts also surfaced a name I didn't expect to sit so central: Major-General Senona. Whether you measure it by shared passages, shared claims, or who actually gives evidence about Matlala, Senona is closer to him than almost anyone in the proceedings. He hasn't featured much in the coverage I've seen.

The graph shows where a connection is disputed. Of everyone tied to Matlala, two come up repeatedly denying the link, Senona and Lieutenant-General Shadrack Sibiya. Senona, for one, denied making arrangements for Matlala to meet about a contract. So the picture isn't only who is connected to whom, it is which of those connections are being fought over in the testimony itself.


The data is stored in Neo4j and Qdrant.

Now.  If you are reporting on this, what questions would you ask?

#MadlangaCommission #SouthAfrica #StateCapture #DataJournalism

---

## Pre-publish verification — run these against the live graph, confirm the figures match

```cypher
// A. Matlala day-span — expect 62
MATCH (:Person {name:'Vusimuzi Matlala'})-[:MENTIONED_IN]->(c:Chunk)
RETURN count(DISTINCT c.day_no) AS days;

// B. Companies day-span — expect Medicare 24 ≈ 32, CAT VIP ≈ 26
MATCH (o:Organisation)-[:MENTIONED_IN]->(c:Chunk)
WHERE o.name IN ['Medicare 24','CAT VIP Security Services']
RETURN o.name, count(DISTINCT c.day_no) AS days ORDER BY days DESC;

// C. The contested signal — denials naming both Matlala and (Senona | Sibiya)
MATCH (cl:Claim)-[:MENTIONS]->(:Person {name:'Vusimuzi Matlala'})
MATCH (cl)-[:MENTIONS]->(p:Person)
WHERE (p.name CONTAINS 'Senona' OR p.name CONTAINS 'Sibiya')
  AND cl.text =~ '(?i).*(denied|denies|disputed|vehemently).*'
RETURN p.name, count(DISTINCT cl) AS denials ORDER BY denials DESC;
```

If a number differs from the graph, use the graph's number in the post (the graph's NER resolves a few more surface forms than the seed-only analysis). The shape of the finding holds either way.

## Final checklist
- [ ] A/B/C above run; post cites the graph's figures.
- [ ] Disclaimer line present; Senona and Sibiya shown as contested (they deny), not condemned.
- [ ] You're comfortable naming Matlala, Senona, Sibiya — your call as author.
- [ ] ~20s cosmograph recording attached (MP4).
- [ ] First comment ready (optional): the method, or "ask me what else it found".

## What changed from the earlier FINAL, and why
- Dropped the numbered-reveal skeleton — it is the single strongest "generated post" tell.
- One disclaimer instead of five; the repeated caveating read as legal over-correction.
- Removed slogan lines ("cold and clinical and doesn't blink", "association from accusation from denial") and the contrast couplets.
- Fixed artifacts: "center piece" to "central", "more focussed" to "sharper", deleted "I imposed no additional human narrative".
- Hashtags cut from 11 to 4 (topic, place, subject, beat); the wide block looked like discoverability-maxxing.
- Tradeoff to know: losing the emoji bullets costs some skim-ability on LinkedIn. If you want the scannability back, the honest middle path is bold lead-ins on two or three paragraphs (not numbered icons), which keeps the structure human.
