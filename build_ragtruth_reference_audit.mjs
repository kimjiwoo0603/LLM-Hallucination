#!/usr/bin/env node
/** Build source-level human-label references from RAGTruth for a second audit of HALO responses. */
import fs from "node:fs/promises";

const [primaryPath, ragtruthResponsesPath, outputPath] = process.argv.slice(2);
if (![primaryPath, ragtruthResponsesPath, outputPath].every(Boolean)) throw new Error("Usage: build_ragtruth_reference_audit.mjs <primary.jsonl> <ragtruth_response.jsonl> <output.jsonl>");
const readJsonl = async (file) => (await fs.readFile(file, "utf8")).trim().split(/\r?\n/).filter(Boolean).map(JSON.parse);
const normalize = (text) => String(text).toLowerCase().replace(/\s+/g, " ").trim();
const primary = await readJsonl(primaryPath);
const sourceIds = new Set(primary.map((row) => String(row.source_id)));
const references = (await readJsonl(ragtruthResponsesPath)).filter((row) => sourceIds.has(String(row.source_id)));
const bySource = new Map();
for (const row of references) {
  const sourceId = String(row.source_id);
  if (!bySource.has(sourceId)) bySource.set(sourceId, []);
  for (const label of row.labels ?? []) bySource.get(sourceId).push({
    original_model: row.model,
    label_type: label.label_type,
    span: String(label.text ?? ""),
    annotator_meta: String(label.meta ?? ""),
    implicit_true: Boolean(label.implicit_true),
  });
}
const audit = primary.map((row) => {
  const referenceLabels = bySource.get(String(row.source_id)) ?? [];
  const response = normalize(row.response);
  const directOverlaps = referenceLabels.filter((label) => {
    const span = normalize(label.span);
    return span.length >= 12 && response.includes(span);
  });
  const uniqueReferences = [...new Map(referenceLabels.map((label) => [`${label.label_type}|${label.span}|${label.annotator_meta}`, label])).values()];
  return {
    packet_id: row.packet_id,
    source_id: String(row.source_id),
    response_sha256: row.response_sha256,
    original_human_label_count_for_source: uniqueReferences.length,
    original_label_types_for_source: [...new Set(uniqueReferences.map((label) => label.label_type))],
    original_human_label_references: uniqueReferences,
    direct_span_overlaps_in_our_response: directOverlaps,
    second_review_priority: directOverlaps.length ? "DIRECT_SPAN_OVERLAP" : (uniqueReferences.length ? "SOURCE_HAS_HUMAN_LABELED_RISKS" : "NO_REFERENCE_LABEL_FOR_SOURCE"),
  };
});
await fs.writeFile(outputPath, audit.map((row) => JSON.stringify(row)).join("\n") + "\n", "utf8");
console.log(JSON.stringify({ rows: audit.length, sources: bySource.size, direct_overlap_rows: audit.filter((row) => row.direct_span_overlaps_in_our_response.length).length, source_risk_rows: audit.filter((row) => row.original_human_label_count_for_source > 0).length }, null, 2));
