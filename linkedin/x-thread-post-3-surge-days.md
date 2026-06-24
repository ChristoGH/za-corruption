# X thread, Post #3: the surge days

Lead image: linkedin/surge_days.png (the per-day timeline). Verify the numbers against the live
graph before posting (queries at the bottom). Each tweet sized for the free 280-char tier.

---

**1/ (attach surge_days.png)**
My last post mapped who the Madlanga Commission keeps naming alongside businessman "Cat" Matlala. Someone asked which thread I'd pull first. Here is one: the calendar. There are days the hearing was almost entirely about him. 🧵

**2/**
Matlala is named on 62 of the 106 hearing days. But it isn't even. On most days he's a passing reference. On a few, he is the day.
Day 53: 73 of 84 passages name him. That is 87% of a full hearing.

**3/**
The peaks read like a heartbeat.
Day 65: 119 passages
Day 75: 105
Day 48: 94
Day 54: 92
Day 9: 83
A handful of days carry most of what the whole commission said about him.

**4/**
That is the use for a reporter. You don't have to read 106 days. The graph points you to the five or six that matter most for one figure, and to the exact passages on each of them.

**5/**
Same rules as before: association in the testimony, not proof of anything. Every passage is an allegation in the public record, attributed under oath, not a finding of fact.
A question for the newsroom: what happened on day 53?
@amaBhungane @dailymaverick @News24

---

## @-mentions (verify handles before posting)
Outlets: @amaBhungane · @dailymaverick · @News24. Optional reply tagging a beat reporter who
covers this. Do not tag anyone named in the testimony as if accusing them.

## Verify against the live graph before posting
```cypher
// top surge days (expect 65, 75, 48, 54, 9 near the top; graph counts may run a little higher)
MATCH (:Person {name:'Vusimuzi Matlala'})-[:MENTIONED_IN]->(c:Chunk)
RETURN c.day_no AS day, count(DISTINCT c) AS passages ORDER BY passages DESC LIMIT 8;

// day 53 proportion (expect ~73 of ~84)
MATCH (c:Chunk {day_no:53}) WITH count(c) AS total
MATCH (:Person {name:'Vusimuzi Matlala'})-[:MENTIONED_IN]->(c2:Chunk {day_no:53})
RETURN count(DISTINCT c2) AS matlala, total;
```
If a number differs, use the graph's number in the post.

## Notes
- The day-9 peak is worth a line if you want it: he enters early and the commission keeps
  returning to him, rather than him surfacing late.
- This is a clean follow-up: it answers Post #2's closing question by pulling a thread, stays
  on the established subject (lower risk), and hands journalists a specific day to chase.
- Series cadence on X: post the thread, then a day later quote-tweet tweet 1 with one more
  finding, so the method does not need re-explaining each time.
