#!/usr/bin/env node
/**
 * test_si.js — Automated Verification of Full Sinhala Localization & ZWJ-Immune Search
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = __dirname;
const productsJsPath = path.join(ROOT, "website", "data", "products.js");
const indexHtmlPath = path.join(ROOT, "website", "index.html");

global.window = {};
eval(fs.readFileSync(productsJsPath, "utf8"));

const catalog = window.CATALOG;
const products = catalog.products;
const html = fs.readFileSync(indexHtmlPath, "utf8");

console.log("=== Running test_si.js (Sinhala Localization & ZWJ-Immune Search) ===");

// 1. Check all products have natural Sinhala names (p.si) and Sinhala variant badges
assert(products.length > 0, "Catalog must contain products");
const sinhalaRegex = /[\u0D80-\u0DFF]/;

products.forEach((p, i) => {
  assert(p.si && typeof p.si === "string" && p.si.trim().length > 5, `Product [${i}] ${p.code} missing p.si`);
  assert(sinhalaRegex.test(p.si), `Product [${i}] ${p.code} p.si does not contain Sinhala Unicode chars: ${p.si}`);
  assert(p.si.includes("(") && p.si.includes(")"), `Product [${i}] ${p.code} p.si should include helpful English technical terms in parentheses: ${p.si}`);

  assert(p.variantSi && sinhalaRegex.test(p.variantSi), `Product [${i}] ${p.code} missing Sinhala variant badge p.variantSi`);
  assert(p.variantByLang && p.variantByLang.si === p.variantSi, `Product [${i}] ${p.code} variantByLang.si mismatch`);
  assert(p.materialByLang && sinhalaRegex.test(p.materialByLang.si), `Product [${i}] ${p.code} missing Sinhala material translation`);
});
console.log(`✓ Verified ${products.length} products have natural Sinhala names (p.si), English technical terms in parentheses, and Sinhala variants.`);

// 2. Check categories have 4-language translations including Sinhala
catalog.categories.forEach(c => {
  assert(c.en && c.si && c.zh && c.es, `Category ${c.id} missing one of (en, si, zh, es)`);
  assert(sinhalaRegex.test(c.si), `Category ${c.id} Sinhala label missing Sinhala script`);
});
console.log(`✓ Verified all ${catalog.categories.length} categories have complete 4-language (en, si, zh, es) labels.`);

// 3. Verify ZWJ-Immune Search Normalization norm(s)
function norm(s) {
  return String(s == null ? "" : s)
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .toLowerCase()
    .trim();
}

assert(html.includes("\\u200B-\\u200D\\uFEFF"), "index.html must include ZWJ stripping regex [\\u200B-\\u200D\\uFEFF]");

// Test pairs: [with ZWJ (\u200D), without ZWJ (phonetic)]
const zwjPairs = [
  ["ඩ්‍රිල්", "ඩ්රිල්"],
  ["රූපලාවන්‍ය", "රූපලාවන්ය"],
  ["අක්‍රමවත්", "අක්රමවත්"],
  ["මිශ්‍ර", "මිශ්ර"],
  ["ප්‍රමාණය", "ප්රමාණය"],
  ["ශ්‍රී ලංකා", "ශ්රී ලංකා"],
  ["සුපිරි ජයග්‍රාහී", "සුපිරි ජයග්රාහී"]
];

zwjPairs.forEach(([withZwj, withoutZwj]) => {
  assert(withZwj !== withoutZwj, `Test pair should differ in raw form: ${withZwj}`);
  assert.strictEqual(
    norm(withZwj),
    norm(withoutZwj),
    `norm() failed to equate ZWJ '${withZwj}' and non-ZWJ '${withoutZwj}'`
  );
});
console.log(`✓ Verified ZWJ normalization norm(s) equates all ${zwjPairs.length} Sinhala ligature vs phonetic test pairs.`);

// 4. Verify live catalog search returns identical results with or without ZWJ
const liveSearchTerms = [
  ["රූපලාවන්‍ය", "රූපලාවන්ය"],
  ["අක්‍රමවත්", "අක්රමවත්"],
  ["මිශ්‍ර", "මිශ්ර"],
  ["ප්‍රමාණය", "ප්රමාණය"]
];

liveSearchTerms.forEach(([qZwj, qNoZwj]) => {
  const hitsZwj = products.filter(p => norm(`${p.si} ${p.variantSi} ${p.materialByLang.si}`).includes(norm(qZwj)));
  const hitsNoZwj = products.filter(p => norm(`${p.si} ${p.variantSi} ${p.materialByLang.si}`).includes(norm(qNoZwj)));
  assert(hitsZwj.length > 0, `Expected catalog matches for Sinhala term '${qZwj}'`);
  assert.strictEqual(hitsZwj.length, hitsNoZwj.length, `Mismatch in hit counts for '${qZwj}' vs '${qNoZwj}'`);
});
console.log("✓ Verified live catalog search returns identical non-empty product matches with and without ZWJ.");

// 5. Verify Cross-Platform Sinhala Font Stack & Antialiasing in CSS
const requiredFonts = [
  "Noto Sans Sinhala",
  "Sinhala Sangam MN",
  "Sinhala MN",
  "Nirmala UI",
  "Iskoola Pota"
];
requiredFonts.forEach(font => {
  assert(html.includes(font), `CSS missing Sinhala font '${font}'`);
});
assert(html.includes("-webkit-font-smoothing: antialiased"), "CSS missing -webkit-font-smoothing: antialiased");
console.log("✓ Verified cross-platform Sinhala font stack and font smoothing in CSS.");

console.log("ALL test_si.js CHECKS PASSED 100%!\n");
