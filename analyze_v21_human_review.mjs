#!/usr/bin/env node
/** Condition restoration and paired analysis for the HALO 2.1 human-reviewed primary run. */
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [workbookPath, primaryPath, auditPath, outputDir] = process.argv.slice(2);
if (![workbookPath, primaryPath, auditPath, outputDir].every(Boolean)) {
  throw new Error("Usage: analyze_v21_human_review.mjs <review.xlsx> <primary.jsonl> <audit.jsonl> <output-dir>");
}
const conditions = ["single_oneshot", "single_sequential", "multi_raw", "multi_gated"];
const labelFields = ["fact", "numeric", "causal", "link"];
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");
const jsonl = async (file) => (await fs.readFile(file, "utf8")).trim().split(/\r?\n/).filter(Boolean).map(JSON.parse);
const asNumber = (value, label) => {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) return Number(value);
  throw new Error(`Missing or invalid ${label}: ${String(value)}`);
};
const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
const sd = (xs) => xs.length < 2 ? 0 : Math.sqrt(xs.reduce((a, b) => a + (b - mean(xs)) ** 2, 0) / (xs.length - 1));
const clamp01 = (x) => Math.max(0, Math.min(1, x));

function logGamma(z) {
  const c = [676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.984369578019572e-6, 1.5056327351493116e-7];
  if (z < 0.5) return Math.log(Math.PI) - Math.log(Math.sin(Math.PI * z)) - logGamma(1 - z);
  z -= 1; let x = 0.99999999999980993;
  for (let i = 0; i < c.length; i += 1) x += c[i] / (z + i + 1);
  const t = z + c.length - 0.5;
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(x);
}
function gammaQ(a, x) {
  if (x <= 0) return 1;
  if (x < a + 1) {
    let sum = 1 / a; let term = sum;
    for (let n = 1; n < 200; n += 1) { term *= x / (a + n); sum += term; if (Math.abs(term) < Math.abs(sum) * 1e-14) break; }
    return clamp01(1 - sum * Math.exp(-x + a * Math.log(x) - logGamma(a)));
  }
  let b = x + 1 - a; let c = 1 / 1e-30; let d = 1 / b; let h = d;
  for (let i = 1; i < 200; i += 1) {
    const an = -i * (i - a); b += 2; d = an * d + b; if (Math.abs(d) < 1e-30) d = 1e-30;
    c = b + an / c; if (Math.abs(c) < 1e-30) c = 1e-30;
    d = 1 / d; const delta = d * c; h *= delta; if (Math.abs(delta - 1) < 1e-14) break;
  }
  return clamp01(Math.exp(-x + a * Math.log(x) - logGamma(a)) * h);
}
const chiSquareP = (statistic, df) => gammaQ(df / 2, statistic / 2);
function erf(x) { const sign = x < 0 ? -1 : 1; x = Math.abs(x); const t = 1 / (1 + 0.3275911 * x); const y = 1 - (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t) * Math.exp(-x * x); return sign * y; }
const normalTwoSided = (z) => clamp01(1 - erf(Math.abs(z) / Math.SQRT2));
function holm(rows) {
  const sorted = [...rows].sort((a, b) => a.p - b.p); let prior = 0;
  for (let i = 0; i < sorted.length; i += 1) { prior = Math.max(prior, Math.min(1, (sorted.length - i) * sorted[i].p)); sorted[i].p_holm = prior; }
  return sorted;
}
function exactMcNemar(a, b) {
  let onlyA = 0; let onlyB = 0;
  for (let i = 0; i < a.length; i += 1) { if (a[i] === 1 && b[i] === 0) onlyA += 1; if (a[i] === 0 && b[i] === 1) onlyB += 1; }
  const n = onlyA + onlyB; const k = Math.min(onlyA, onlyB);
  let probability = 2 ** (-n); let cumulative = probability;
  for (let i = 0; i < k; i += 1) { probability *= (n - i) / (i + 1); cumulative += probability; }
  return { discordant_a1_b0: onlyA, discordant_a0_b1: onlyB, p: Math.min(1, 2 * cumulative), odds_ratio_haldane: (onlyA + 0.5) / (onlyB + 0.5) };
}
function cochranQ(matrix) {
  const n = matrix.length; const k = matrix[0].length;
  const columns = Array.from({ length: k }, (_, j) => matrix.reduce((sum, row) => sum + row[j], 0));
  const rows = matrix.map((row) => row.reduce((sum, x) => sum + x, 0));
  const total = columns.reduce((a, b) => a + b, 0);
  const denominator = k * total - rows.reduce((sum, value) => sum + value * value, 0);
  const statistic = denominator === 0 ? 0 : ((k - 1) * (k * columns.reduce((sum, value) => sum + value * value, 0) - total * total)) / denominator;
  return { statistic, df: k - 1, p: denominator === 0 ? 1 : chiSquareP(statistic, k - 1), condition_totals: columns };
}
function ranks(values) {
  const sorted = values.map((value, index) => ({ value, index })).sort((a, b) => a.value - b.value);
  const output = Array(values.length); let start = 0;
  while (start < sorted.length) { let end = start; while (end + 1 < sorted.length && sorted[end + 1].value === sorted[start].value) end += 1; const rank = (start + 1 + end + 1) / 2; for (let i = start; i <= end; i += 1) output[sorted[i].index] = rank; start = end + 1; }
  return output;
}
function friedman(matrix) {
  const n = matrix.length; const k = matrix[0].length; const ranked = matrix.map(ranks); const sums = Array.from({ length: k }, (_, j) => ranked.reduce((sum, row) => sum + row[j], 0));
  let stat = (12 / (n * k * (k + 1))) * sums.reduce((sum, x) => sum + x * x, 0) - 3 * n * (k + 1);
  let tieTerm = 0;
  for (const row of matrix) { const counts = new Map(); for (const x of row) counts.set(x, (counts.get(x) ?? 0) + 1); for (const t of counts.values()) tieTerm += t ** 3 - t; }
  const correction = 1 - tieTerm / (n * k * (k ** 2 - 1)); if (correction > 0) stat /= correction;
  return { statistic: stat, df: k - 1, p: chiSquareP(stat, k - 1), rank_sums: sums };
}
function wilcoxon(a, b) {
  const differences = a.map((x, i) => x - b[i]).filter((x) => x !== 0);
  if (!differences.length) return { n_nonzero: 0, w_plus: 0, z: 0, p: 1 };
  const abs = differences.map(Math.abs); const rs = ranks(abs); const wPlus = differences.reduce((sum, d, i) => sum + (d > 0 ? rs[i] : 0), 0); const n = differences.length;
  const counts = new Map(); for (const x of abs) counts.set(x, (counts.get(x) ?? 0) + 1);
  const tie = [...counts.values()].reduce((sum, t) => sum + (t ** 3 - t), 0);
  const variance = n * (n + 1) * (2 * n + 1) / 24 - tie / 48;
  const z = variance > 0 ? (Math.abs(wPlus - n * (n + 1) / 4) - 0.5) / Math.sqrt(variance) : 0;
  return { n_nonzero: n, w_plus: wPlus, z, p: normalTwoSided(z) };
}

const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const sheet = wb.worksheets.getItem("02_재검수");
const values = sheet.getRange("A1:Q193").values;
const headers = values[0]; const ix = Object.fromEntries(headers.map((header, index) => [header, index]));
const finalRows = await jsonl(primaryPath); const auditRows = await jsonl(auditPath);
if (values.length !== 193 || finalRows.length !== 192 || auditRows.length !== 192) throw new Error("Expected exactly 192 review, primary, and audit rows");
const reviewed = values.slice(1).map((row, index) => {
  const audit = auditRows[index]; const primary = finalRows[index];
  if (row[ix.packet_id] !== audit.packet_id || row[ix.packet_id] !== primary.packet_id || String(row[ix["모델 최종응답"]]) !== String(audit.response) || sha256(String(row[ix["모델 최종응답"]])) !== primary.response_sha256) throw new Error(`Blind order mismatch at review row ${index + 2}`);
  if (String(row[ix["검토 상태"]]) !== "완료") throw new Error(`Review row ${index + 2} is not complete`);
  const labels = Object.fromEntries(labelFields.map((field, i) => [field, asNumber(row[ix[`사람: ${["사실", "수치", "인과", "링크"][i]} 0/1`]], field)]));
  for (const [field, value] of Object.entries(labels)) if (![0, 1].includes(value)) throw new Error(`Invalid ${field} label at review row ${index + 2}`);
  const composite = Number(Object.values(labels).some((value) => value === 1));
  const accuracy = asNumber(row[ix["정확도 1–5"]], "accuracy"); const usefulness = asNumber(row[ix["유용성 1–5"]], "usefulness");
  if (![1, 2, 3, 4, 5].includes(accuracy) || ![1, 2, 3, 4, 5].includes(usefulness)) throw new Error(`Invalid rating at review row ${index + 2}`);
  return { review_id: row[ix.review_id], packet_id: primary.packet_id, condition: primary.condition, question_type: primary.question_type, ...labels, composite, accuracy, usefulness };
});
const units = new Map();
for (const row of reviewed) { if (!units.has(row.packet_id)) units.set(row.packet_id, {}); units.get(row.packet_id)[row.condition] = row; }
if (units.size !== 48 || [...units.values()].some((rows) => conditions.some((condition) => !rows[condition]))) throw new Error("Each of 48 packets must have all four conditions");
const summaries = conditions.map((condition) => {
  const rows = reviewed.filter((row) => row.condition === condition);
  const result = { condition, n: rows.length, hallucination_count: rows.reduce((s, r) => s + r.composite, 0), fact_count: rows.reduce((s, r) => s + r.fact, 0), numeric_count: rows.reduce((s, r) => s + r.numeric, 0), causal_count: rows.reduce((s, r) => s + r.causal, 0), link_count: rows.reduce((s, r) => s + r.link, 0), accuracy_mean: mean(rows.map((r) => r.accuracy)), accuracy_sd: sd(rows.map((r) => r.accuracy)), usefulness_mean: mean(rows.map((r) => r.usefulness)), usefulness_sd: sd(rows.map((r) => r.usefulness)) };
  result.hallucination_rate = result.hallucination_count / result.n; return result;
});
const packetOrder = [...units.keys()];
const matrixFor = (field) => packetOrder.map((packet) => conditions.map((condition) => units.get(packet)[condition][field]));
const cochran = cochranQ(matrixFor("composite"));
const pairwiseHallucination = [];
const pairwiseRatings = { accuracy: [], usefulness: [] };
for (let i = 0; i < conditions.length; i += 1) for (let j = i + 1; j < conditions.length; j += 1) {
  const a = conditions[i], b = conditions[j]; const ha = packetOrder.map((packet) => units.get(packet)[a].composite); const hb = packetOrder.map((packet) => units.get(packet)[b].composite);
  pairwiseHallucination.push({ comparison: `${a} vs ${b}`, condition_a: a, condition_b: b, ...exactMcNemar(ha, hb) });
  for (const metric of ["accuracy", "usefulness"]) pairwiseRatings[metric].push({ comparison: `${a} vs ${b}`, condition_a: a, condition_b: b, ...wilcoxon(packetOrder.map((packet) => units.get(packet)[a][metric]), packetOrder.map((packet) => units.get(packet)[b][metric])) });
}
const analysis = { protocol: "HALO 2.1 primary human-reviewed analysis v1", validation: { completed_rows: reviewed.length, packets: units.size, conditions, restored_by: "blind review row order + packet_id + response SHA-256" }, descriptive: summaries, primary_hallucination: { cochran_q: cochran, pairwise_mcnemar_holm: holm(pairwiseHallucination) }, supplementary_ratings: { accuracy_friedman: friedman(matrixFor("accuracy")), usefulness_friedman: friedman(matrixFor("usefulness")), pairwise_wilcoxon_holm: { accuracy: holm(pairwiseRatings.accuracy), usefulness: holm(pairwiseRatings.usefulness) } } };
const subtypePairwiseAll = [];
const subtypeAnalysis = {};
for (const subtype of labelFields) {
  const matrix = matrixFor(subtype);
  const pairs = [];
  for (let i = 0; i < conditions.length; i += 1) for (let j = i + 1; j < conditions.length; j += 1) {
    const conditionA = conditions[i]; const conditionB = conditions[j];
    const entry = { subtype, comparison: `${conditionA} vs ${conditionB}`, condition_a: conditionA, condition_b: conditionB, ...exactMcNemar(packetOrder.map((packet) => units.get(packet)[conditionA][subtype]), packetOrder.map((packet) => units.get(packet)[conditionB][subtype])) };
    pairs.push(entry); subtypePairwiseAll.push(entry);
  }
  subtypeAnalysis[subtype] = {
    cochran_q: cochranQ(matrix),
    condition_counts: conditions.map((condition) => ({ condition, count: reviewed.filter((row) => row.condition === condition).reduce((sum, row) => sum + row[subtype], 0), rate: reviewed.filter((row) => row.condition === condition).reduce((sum, row) => sum + row[subtype], 0) / 48 })),
    pairwise_mcnemar_holm_within_subtype: holm(pairs),
  };
}
const globalSubtypeHolm = holm(subtypePairwiseAll);
const globalSubtypeLookup = new Map(globalSubtypeHolm.map((row) => [`${row.subtype}|${row.comparison}`, row.p_holm]));
for (const subtype of labelFields) for (const row of subtypeAnalysis[subtype].pairwise_mcnemar_holm_within_subtype) row.p_holm_across_all_24_subtype_tests = globalSubtypeLookup.get(`${subtype}|${row.comparison}`);
const questionTypes = [...new Set(reviewed.map((row) => row.question_type))].sort();
const questionTypeDescriptives = questionTypes.flatMap((question_type) => conditions.map((condition) => {
  const rows = reviewed.filter((row) => row.question_type === question_type && row.condition === condition);
  return { question_type, condition, n: rows.length, composite_count: rows.reduce((sum, row) => sum + row.composite, 0), composite_rate: rows.reduce((sum, row) => sum + row.composite, 0) / rows.length, fact_count: rows.reduce((sum, row) => sum + row.fact, 0), numeric_count: rows.reduce((sum, row) => sum + row.numeric, 0), causal_count: rows.reduce((sum, row) => sum + row.causal, 0), link_count: rows.reduce((sum, row) => sum + row.link, 0) };
}));
analysis.hallucination_subtypes = subtypeAnalysis;
analysis.question_type_descriptives_exploratory = questionTypeDescriptives;
await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(path.join(outputDir, "analysis_summary.json"), JSON.stringify(analysis, null, 2));
const csv = (rows) => rows.length ? [Object.keys(rows[0]).join(","), ...rows.map((row) => Object.values(row).map((v) => typeof v === "string" ? `"${v.replaceAll('"', '""')}"` : v).join(","))].join("\n") : "";
await fs.writeFile(path.join(outputDir, "condition_descriptives.csv"), csv(summaries));
await fs.writeFile(path.join(outputDir, "hallucination_pairwise.csv"), csv(analysis.primary_hallucination.pairwise_mcnemar_holm));
await fs.writeFile(path.join(outputDir, "hallucination_subtype_pairwise.csv"), csv(globalSubtypeHolm));
await fs.writeFile(path.join(outputDir, "question_type_descriptives_exploratory.csv"), csv(questionTypeDescriptives));
console.log(JSON.stringify(analysis, null, 2));
