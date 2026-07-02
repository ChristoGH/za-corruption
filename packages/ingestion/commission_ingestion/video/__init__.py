"""Video caption ingestion: fetch YouTube caption tracks, parse WebVTT,
and segment them into time-provenanced chunks.

The captions lane (plans/staying-current-pipeline.md component 2) ingests
hearing days that exist only as video. Machine text is never presented as
official transcript: the registry record is authoritative=false and carries
transcription_method, and every chunk carries time provenance instead of
page provenance.
"""
