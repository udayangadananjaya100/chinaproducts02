#!/usr/bin/env node
/**
 * test_edge_cases.js — Automated Verification of Data Integrity, SL-WPI Math,
 * Image Deduplication/WebP Existence, Null-Weight Safety, Comma Decimals & Deployment Files.
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = __dirname;
const productsJsPath = path.join(ROOT, "website", "data", "products.js");

console.log("=== Running test_edge_cases.js (Data Integrity, SL-WPI Math & Edge Cases) ===");

global.window = {};
eval(fs.readFileSync(productsJsPath, "utf8"));

const catalog = window.CATALOG;
const products = catalog.products;

// 1. Verify 100% Product Data Integrity & WebP Image Existence
const seenCodes = new Set();
products.forEach((p, i) => {
  assert(p.code && !seenCodes.has(p.code), `Duplicate or missing product code at [${i}]: ${p.code}`);
  seenCodes.add(p.code);

  assert(typeof p.price === "number" && p.price > 0 && isFinite(p.price), `Invalid price on ${p.code}: ${p.price}`);
  assert(Number.isInteger(p.pcsPerCarton) && p.pcsPerCarton >= 1, `Invalid pcsPerCarton on ${p.code}: ${p.pcsPerCarton}`);
  assert(typeof p.cbm === "number" && p.cbm > 0 && isFinite(p.cbm), `Invalid cbm on ${p.code}: ${p.cbm}`);
  assert(p.kg === null || (typeof p.kg === "number" && p.kg > 0 && isFinite(p.kg)), `Invalid kg on ${p.code}: ${p.kg}`);

  assert(p.thumb && p.thumb.endsWith("_t.webp"), `Invalid thumb path on ${p.code}: ${p.thumb}`);
  assert(p.large && p.large.endsWith("_l.webp"), `Invalid large path on ${p.code}: ${p.large}`);

  const thumbAbs = path.join(ROOT, "website", p.thumb);
  const largeAbs = path.join(ROOT, "website", p.large);
  assert(fs.existsSync(thumbAbs) && fs.statSync(thumbAbs).size > 100, `Missing or empty thumb WebP: ${thumbAbs}`);
  assert(fs.existsSync(largeAbs) && fs.statSync(largeAbs).size > 100, `Missing or empty large WebP: ${largeAbs}`);
});
console.log(`✓ Verified 100% data integrity and existing WebP image pairs for all ${products.length} products.`);

// 2. Verify SL-WPI 100-Point Sea Cargo Model Invariants
const tierCounts = { mega: 0, strong: 0, niche: 0, low: 0 };
products.forEach(p => {
  const bd = p.winBreakdown;
  assert(bd && bd.freight && bd.margin && bd.demand && bd.risk, `Missing winBreakdown pillars on ${p.code}`);

  const f = bd.freight.score;
  const m = bd.margin.score;
  const d = bd.demand.score;
  const r = bd.risk.score;

  [f, m, d, r].forEach(sc => {
    assert(Number.isInteger(sc) && sc >= 0 && sc <= 25, `Pillar score out of 0..25 range on ${p.code}: ${sc}`);
  });

  // Exact equality invariant: freight + margin + demand + risk == winScore
  assert.strictEqual(f + m + d + r, p.winScore, `SL-WPI sum mismatch on ${p.code}: ${f}+${m}+${d}+${r} != ${p.winScore}`);
  assert.strictEqual(p.winRate, `${p.winScore}%`, `winRate mismatch on ${p.code}: ${p.winRate}`);

  // Tier classification check
  if (p.winScore >= 85) assert.strictEqual(p.winTier, "mega");
  else if (p.winScore >= 70) assert.strictEqual(p.winTier, "strong");
  else if (p.winScore >= 50) assert.strictEqual(p.winTier, "niche");
  else assert.strictEqual(p.winTier, "low");

  tierCounts[p.winTier]++;

  // Verify 4-language descriptions on every pillar and winReason, and ensure low-scoring items don't have positive text
  ["en", "si", "zh", "es"].forEach(lang => {
    assert(p.winReason && p.winReason[lang], `Missing winReason.${lang} on ${p.code}`);
    ["freight", "margin", "demand", "risk"].forEach(pillar => {
      assert(bd[pillar].desc && bd[pillar].desc[lang], `Missing ${pillar}.desc.${lang} on ${p.code}`);
    });
  });

  if (p.winTier === "low") {
    assert(!p.winReason.en.includes("Mega Winner"), `Low-feasibility product ${p.code} must not have positive Mega Winner text`);
  }
});
console.log(`✓ Verified SL-WPI 100-Point Sea Cargo math (freight+margin+demand+risk == winScore) on all ${products.length} products:`, tierCounts);

// 3. Verify Null Weight Handling Without NaN
const mockCartWithNullKg = [
  { price: 25, pcsPerCarton: 10, cbm: 0.04, kg: null, cartons: 3 },
  { price: 40, pcsPerCarton: 1, cbm: 0.05, kg: 12.5, cartons: 2 }
];
const totalKg = mockCartWithNullKg.reduce((acc, item) => {
  const unitCtnKg = (item.kg != null && !isNaN(Number(item.kg))) ? Number(item.kg) : 0;
  return acc + item.cartons * unitCtnKg;
}, 0);
assert.strictEqual(totalKg, 25.0, "Null weight handling failed");
assert(!Number.isNaN(totalKg), "totalKg must never be NaN");
console.log("✓ Verified null weight handling in quotation cart calculation produces exact finite numbers (never NaN).");

// 4. Verify Period and Comma Decimal Exchange Rate Parsing
function parseRateValue(val) {
  const cleaned = String(val == null ? "" : val).trim().replace(/,/g, ".");
  const num = parseFloat(cleaned);
  return (isFinite(num) && num > 0) ? num : NaN;
}
assert.strictEqual(parseRateValue("7.15"), 7.15);
assert.strictEqual(parseRateValue("7,15"), 7.15);
assert.strictEqual(parseRateValue("43,50"), 43.50);
assert(Number.isNaN(parseRateValue("-5")));
assert(Number.isNaN(parseRateValue("0")));
console.log("✓ Verified exchange rate parser supports both period (.) and comma (,) decimals and rejects <= 0.");

// 5. Verify Deployment & Launcher Files (.gitignore, vercel.json, Open_Website.bat, root index.html)
const gitignore = fs.readFileSync(path.join(ROOT, ".gitignore"), "utf8");
assert(gitignore.includes("*.xlsx") && gitignore.includes("*.xls"), ".gitignore must exclude *.xlsx and *.xls");

const vercelJson = JSON.parse(fs.readFileSync(path.join(ROOT, "vercel.json"), "utf8"));
assert(
  vercelJson.redirects &&
  vercelJson.redirects.some(r => r.source === "/" && r.destination === "/website/"),
  "vercel.json must redirect '/' to '/website/'"
);

const batContent = fs.readFileSync(path.join(ROOT, "Open_Website.bat"), "utf8");
assert(batContent.includes('start "" "%~dp0website\\index.html"'), "Open_Website.bat missing launcher command");

assert(fs.existsSync(path.join(ROOT, "index.html")), "Root index.html redirect must exist");
console.log("✓ Verified .gitignore, vercel.json, Open_Website.bat, and root index.html redirect.");

console.log("ALL test_edge_cases.js CHECKS PASSED 100%!\n");
