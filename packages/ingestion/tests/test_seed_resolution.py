"""Pre-step A — speaker seed-alias resolution + surname-collision safety.

These run against the REAL seed_entities.yaml so a regression in the human-owned
seed (a wrong merge, a forbidden bare-surname alias, a within-group collision) is
caught here. The four-Khumalos rule generalises: any surname with multiple real
people in the corpus (KHUMALO, MKHWANAZI) must never be resolvable on the bare
surname alone, and the role+surname speaker forms must resolve to DISTINCT ids.
"""

from __future__ import annotations

import pytest

from commission_ingestion.resolution.canonical import (
    DEFAULT_SEED_PATH,
    load_store,
    normalise,
)

# Surnames known to belong to more than one real person in this corpus.
_COLLIDING_SURNAMES = {"KHUMALO", "MKHWANAZI"}


@pytest.fixture(scope="module")
def store():
    # load_store raises on any within-type-group alias collision, so a clean
    # load is itself part of the guarantee.
    return load_store(DEFAULT_SEED_PATH)


# ── pre-step A: the COMMISSIONER <surname> speaker labels now resolve ──────────

@pytest.mark.parametrize("label,expected_id", [
    ("COMMISSIONER MKHWANAZI", "person:jd-mkhwanazi"),
    ("COMMISSIONER SPIES",     "person:revo-spies"),
    ("COMMISSIONER FARO",      "person:commissioner-faro"),
    ("COMMISSIONER BOLHUIS",   "person:commissioner-bolhuis"),
    ("COMMISSIONER MALATJI",   "person:commissioner-malatji"),
])
def test_commissioner_speaker_labels_resolve(store, label, expected_id):
    hit = store.lookup(label, entity_type="person")
    assert hit is not None, f"{label!r} must resolve so its claims carry STATED_BY"
    assert hit.entity_id == expected_id


# ── surname collision: distinct people with a shared surname stay distinct ─────

def test_mkhwanazi_pair_resolves_to_distinct_people(store):
    empd = store.lookup("COMMISSIONER MKHWANAZI", entity_type="person")
    kzn = store.lookup("LT-GEN MKHWANAZI", entity_type="person")
    general = store.lookup("GENERAL MKHWANAZI", entity_type="person")
    assert empd.entity_id == "person:jd-mkhwanazi"
    assert kzn.entity_id == "person:nhlanhla-mkhwanazi"
    assert general.entity_id == "person:nhlanhla-mkhwanazi"
    assert empd.entity_id != kzn.entity_id  # the EMPD witness is NOT the KZN general


def test_khumalo_pair_resolves_to_distinct_people(store):
    counsel = store.lookup("ADV KHUMALO SC", entity_type="person")
    general = store.lookup("LT-GEN KHUMALO", entity_type="person")
    assert counsel.entity_id != general.entity_id


@pytest.mark.parametrize("surname", sorted(_COLLIDING_SURNAMES))
def test_bare_colliding_surname_is_not_aliased(store, surname):
    """No alias OR canonical name may be the bare colliding surname on its own —
    the forbidden surname-only merge (resolution/seed_entities.yaml header)."""
    for ent in store.entities:
        if ent.entity_type != "person":
            continue
        forms = {normalise(ent.name)} | {normalise(a) for a in ent.aliases}
        assert surname not in forms, (
            f"{ent.entity_id} has bare {surname!r} as a name/alias — forbidden"
        )


def test_bare_khumalo_does_not_resolve(store):
    """Two seeded Khumalos own the title-stripped 'KHUMALO', so the bare surname
    is ambiguous and must resolve to nothing (raw fallthrough), never to one of
    them. This is the collision protection working."""
    assert store.lookup("KHUMALO", entity_type="person") is None


# ── finding #2: bare-index ambiguity suppression is SEED-DERIVED ───────────────

def test_bare_mkhwanazi_is_suppressed(store):
    """The fix: ≥2 seeded Mkhwanazis (KZN Lt-Gen + EMPD commissioner), so bare
    'MKHWANAZI' must NOT auto-resolve to the general — even though only his
    aliases strip to the bare surname."""
    assert store.lookup("MKHWANAZI", entity_type="person") is None


def test_derived_ambiguity_suppresses_every_colliding_surname(store):
    """The regression guard against the NEXT silent collision: every bare token
    owned by >1 canonical person — derived from the seed, not hand-listed — must
    return None on bare lookup. Adding a 6th commissioner / 5th Khumalo is covered
    automatically with no edit here."""
    ambiguous_person = {tok for grp, tok in store.ambiguous_surnames if grp == "person"}
    assert {"KHUMALO", "MKHWANAZI"} <= ambiguous_person  # both known collisions present
    for tok in ambiguous_person:
        assert store.lookup(tok, entity_type="person") is None, (
            f"ambiguous bare {tok!r} must not auto-resolve"
        )


def test_unique_surname_still_bare_resolves(store):
    """The fix must SUPPRESS only collisions, never over-suppress: a surname with
    a single seeded owner still resolves on the bare index."""
    masemola = store.lookup("MASEMOLA", entity_type="person")
    assert masemola is not None and masemola.entity_id == "person:fannie-masemola"


def test_full_form_resolution_unaffected_by_suppression(store):
    """Suppression touches only the bare index; full-form aliases (incl. every
    speaker label) still resolve to their correct distinct ids."""
    assert store.lookup("LT-GEN MKHWANAZI", "person").entity_id == "person:nhlanhla-mkhwanazi"
    assert store.lookup("COMMISSIONER MKHWANAZI", "person").entity_id == "person:jd-mkhwanazi"
    assert store.lookup("ADV KHUMALO SC", "person").entity_id == "person:sandile-khumalo"
    assert store.lookup("LT-GEN KHUMALO", "person").entity_id == "person:dumisani-khumalo"
