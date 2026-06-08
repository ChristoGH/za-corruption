Yes — the same core ontology holds, but the taxonomy should be extended per commission.

Think of it like this:

One shared commission ontology
+
Commission-specific vocabularies / taxonomies

The ontology is the stable structure: people, organisations, places, hearings, documents, chunks, claims, events, roles, evidence and findings.

The taxonomy is the domain-specific classification layer: types of people, types of events, types of institutions, types of evidence, types of corruption allegations, types of proceedings, and so on.

⸻

1. Core ontology that holds for both

This should be common to Zondo, Madlanga, and probably most South African commissions of inquiry.

(:Commission)
(:HearingDay)
(:Session)
(:Document)
(:Transcript)
(:Page)
(:Chunk)
(:Person)
(:Organisation)
(:Place)
(:Role)
(:Position)
(:Claim)
(:Event)
(:Matter)
(:EvidenceItem)
(:Finding)
(:Recommendation)
(:LegalRepresentative)
(:Witness)
(:Commissioner)
(:EvidenceLeader)

Core relationships:

(:Commission)-[:HAS_HEARING]->(:HearingDay)
(:HearingDay)-[:HAS_DOCUMENT]->(:Document)
(:Document)-[:HAS_CHUNK]->(:Chunk)
(:Person)-[:SPOKE_IN]->(:Chunk)
(:Person)-[:MENTIONED_IN]->(:Chunk)
(:Organisation)-[:MENTIONED_IN]->(:Chunk)
(:Place)-[:MENTIONED_IN]->(:Chunk)
(:Claim)-[:SUPPORTED_BY]->(:Chunk)
(:Claim)-[:STATED_BY]->(:Person)
(:Event)-[:EVIDENCED_BY]->(:Chunk)
(:Person)-[:HAS_PROCEDURAL_ROLE]->(:Role)
(:Person)-[:HELD_POSITION]->(:Position)
(:Position)-[:AT_ORG]->(:Organisation)

That part should be shared.

⸻

2. Where the taxonomy differs

The difference is mainly in the domain vocabulary.

Zondo Commission taxonomy

Zondo is heavily about state capture, procurement, SOEs, political influence, contracts and public finance.

Useful Zondo-specific types:

StateOwnedEntity
GovernmentDepartment
PrivateCompany
PoliticalOffice
BoardPosition
ExecutivePosition
Contract
Tender
Payment
Donation
Meeting
Instruction
Appointment
ProcurementProcess
IrregularExpenditure
Finding
Recommendation
ReportVolume

Example Zondo matters:

Eskom
Transnet
Denel
SAA
Prasa
Bosasa
Gupta family
Free State asbestos
Estina dairy
McKinsey / Trillian
SSA
Parliamentary oversight

So in Zondo, your graph often asks:

Who held what position at which SOE?
Who influenced which appointment?
Which contract involved which company?
Which payment was linked to which entity?
Which finding was made against which person?

⸻

Madlanga Commission taxonomy

Madlanga is more about criminal justice, law enforcement, syndicates, interference, policing, prosecutions and institutional breakdown.

Useful Madlanga-specific types:

LawEnforcementAgency
ProsecutingAuthority
IntelligenceAgency
JudicialInstitution
CorrectionalService
InvestigationUnit
CriminalSyndicate
CaseDocket
Investigation
Prosecution
Threat
Assassination
PoliticalInterference
OperationalInterference
CorruptionAllegation
CriminalMatter
ProtectedDisclosure
SecurityIncident

Example Madlanga matters may involve:

SAPS
IPID
NPA
Crime Intelligence
Hawks
Correctional Services
Judiciary
case dockets
witness intimidation
criminal syndicates
political interference
law-enforcement appointments

So in Madlanga, your graph often asks:

Who interfered in which investigation?
Which official was linked to which syndicate?
Which case docket was mentioned?
Which witness described threats?
Which law-enforcement body failed to act?
Which prosecution decision was questioned?

⸻

3. Recommended design: one ontology, multiple controlled vocabularies

Use one graph structure, but give each classified node a type or taxonomy_class.

For example:

(:Organisation {
  name: "Eskom",
  taxonomy_class: "StateOwnedEntity"
})
(:Organisation {
  name: "IPID",
  taxonomy_class: "LawEnforcementOversightBody"
})

Or better:

(:Organisation)-[:HAS_TYPE]->(:OrganisationType {name: "StateOwnedEntity"})
(:Organisation)-[:HAS_TYPE]->(:OrganisationType {name: "LawEnforcementOversightBody"})

This is more flexible because one organisation can have more than one classification.

⸻

4. The most important shared distinction

Both commissions require this distinction:

Mention ≠ Claim ≠ Finding ≠ Fact

Your graph should separate these:

A person was mentioned in a transcript.
A witness made a claim about that person.
The commission made a finding about that person.
A court or official process later confirmed/rejected something.

So do not model this:

(:Person)-[:CORRUPTLY_INFLUENCED]->(:Contract)

unless you are very explicit about provenance.

Rather model:

(:Claim {
  text: "...",
  status: "testimony",
  confidence: 0.82
})
-[:STATED_BY]->(:Person)
-[:SUPPORTED_BY]->(:Chunk)

And later:

(:Finding {
  text: "...",
  source: "Final Report",
  status: "commission_finding"
})
-[:REFERS_TO]->(:Person)

This allows legally safer and more useful analysis.

⸻

5. Suggested top-level taxonomy

I would start with these common controlled vocabularies.

PersonRole

Commissioner
Chairperson
EvidenceLeader
Witness
LegalRepresentative
Investigator
AccusedPerson
MentionedPerson
PublicOfficial
PoliticalOfficeBearer
Executive
BoardMember
Whistleblower
Journalist
ExpertWitness

OrganisationType

Commission
StateOwnedEntity
GovernmentDepartment
LawEnforcementAgency
ProsecutingAuthority
IntelligenceAgency
JudicialInstitution
CorrectionalService
PrivateCompany
PoliticalParty
Regulator
OversightBody
FinancialInstitution
MediaOrganisation
CivilSocietyOrganisation

DocumentType

Transcript
WitnessStatement
Affidavit
Annexure
EvidenceBundle
Report
FinalReport
InterimReport
Notice
Ruling
Correspondence
Contract
Invoice
BankRecord
Presentation
MeetingMinutes

EventType

Hearing
Testimony
CrossExamination
Meeting
Appointment
Dismissal
ProcurementDecision
ContractAward
Payment
Instruction
Threat
Assassination
Investigation
ProsecutionDecision
Arrest
Complaint
ReportPublication
Recommendation

ClaimStatus

Mentioned
Alleged
Testified
Denied
Admitted
Disputed
Corroborated
CommissionFinding
CourtFinding
Unverified

This ClaimStatus taxonomy is very important.

⸻

6. Practical Neo4j modelling pattern

Instead of hardcoding too many labels like this:

(:Witness)
(:Commissioner)
(:StateOwnedEntity)
(:LawEnforcementAgency)

I would keep broad labels and attach types:

(:Person)-[:HAS_ROLE]->(:Role)
(:Organisation)-[:HAS_TYPE]->(:OrganisationType)
(:Document)-[:HAS_TYPE]->(:DocumentType)
(:Event)-[:HAS_TYPE]->(:EventType)
(:Claim)-[:HAS_STATUS]->(:ClaimStatus)

That makes your graph easier to extend.

Example:

MERGE (p:Person {name: "Anoj Singh"})
MERGE (r:Role {name: "Witness"})
MERGE (p)-[:HAS_PROCEDURAL_ROLE {
  commission: "Zondo Commission",
  source_chunk_id: $chunk_id
}]->(r)

And separately:

MERGE (p:Person {name: "Anoj Singh"})
MERGE (pos:Position {title: "Chief Financial Officer"})
MERGE (org:Organisation {name: "Eskom"})
MERGE (p)-[:HELD_POSITION {
  source_chunk_id: $chunk_id,
  date_text: "former",
  confidence: 0.91
}]->(pos)
MERGE (pos)-[:AT_ORG]->(org)

This avoids confusing procedural role with real-world position.

⸻

7. My recommended answer

Use the same ontology, but not exactly the same taxonomy.

Use:

Common ontology:
  Commission, Hearing, Document, Chunk, Person, Organisation, Place,
  Claim, Event, Evidence, Finding, Recommendation
Shared taxonomy:
  roles, document types, claim statuses, evidence types
Commission-specific taxonomy:
  Zondo: SOEs, procurement, contracts, appointments, payments, political influence
  Madlanga: criminal justice, syndicates, investigations, prosecutions, threats, interference

The best design is therefore:

Stable graph schema
+
Extensible domain dictionaries
+
Strict provenance
+
Claim/status modelling

That will let you ingest Zondo first, then Madlanga, without redesigning the whole system.