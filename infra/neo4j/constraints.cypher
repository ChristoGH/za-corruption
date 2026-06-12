// Uniqueness constraints for the commission evidence graph.
// Canonical source: docs/neo4j-model.md — run before any ingestion, e.g.:
//   cat infra/neo4j/constraints.cypher | docker compose exec -T neo4j \
//     cypher-shell -u neo4j -p "$NEO4J_PASSWORD"

CREATE CONSTRAINT commission_slug IF NOT EXISTS
FOR (c:Commission) REQUIRE c.slug IS UNIQUE;
CREATE CONSTRAINT hearing_day_key IF NOT EXISTS
FOR (h:HearingDay) REQUIRE h.key IS UNIQUE;
CREATE CONSTRAINT document_sha IF NOT EXISTS
FOR (d:Document) REQUIRE d.sha256 IS UNIQUE;
CREATE CONSTRAINT page_key IF NOT EXISTS
FOR (p:Page) REQUIRE p.key IS UNIQUE;
CREATE CONSTRAINT chunk_id IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE;
CREATE CONSTRAINT person_name IF NOT EXISTS
FOR (p:Person) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT organisation_name IF NOT EXISTS
FOR (o:Organisation) REQUIRE o.name IS UNIQUE;
CREATE CONSTRAINT place_name IF NOT EXISTS
FOR (p:Place) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT role_name IF NOT EXISTS
FOR (r:Role) REQUIRE r.name IS UNIQUE;
CREATE CONSTRAINT position_title IF NOT EXISTS
FOR (p:Position) REQUIRE p.title IS UNIQUE;
CREATE CONSTRAINT claim_id IF NOT EXISTS
FOR (c:Claim) REQUIRE c.claim_id IS UNIQUE;
CREATE CONSTRAINT event_id IF NOT EXISTS
FOR (e:Event) REQUIRE e.event_id IS UNIQUE;
