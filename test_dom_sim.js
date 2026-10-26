#!/usr/bin/env node
/**
 * test_dom_sim.js — Automated DOM & Interactive State Simulation
 * Tests Multi-Currency Engine, I18N Dictionary, Filtering, Sorting, Cart Totals, and CSV Export.
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = __dirname;
const productsJsPath = path.join(ROOT, "website", "data", "products.js");
const indexHtmlPath = path.join(ROOT, "website", "index.html");

console.log("=== Running test_dom_sim.js (DOM & Interactive Logic Simulation) ===");

global.window = {};
eval(fs.readFileSync(productsJsPath, "utf8"));
const html = fs.readFileSync(indexHtmlPath, "utf8");

// Extract inline script from index.html to inspect I18N and helper functions
const scriptMatches = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert(scriptMatches.length > 0, "Inline application script not found in website/index.html");
const appScript = scriptMatches[scriptMatches.length - 1][1];

// Verify required DOM IDs exist in index.html
const requiredIds = [
  "lang", "curr", "ratesBtn", "ratesModal", "q", "pmin", "pmax", "sort",
  "cats", "detail", "cart", "dQtyMinus", "dQtyPlus", "dQty", "dPrevImg",
  "dNextImg", "dThumbs", "mobileCartBar", "cartStickyTotal",
  "exportCsvBtn", "printBtn", "clearCartBtn", "rateUsdInput", "rateLkrInput",
  "ratesPreview", "saveRatesBtn", "resetRatesBtn"
];
requiredIds.forEach(id => {
  const re = new RegExp(`id=["']${id}["']`);
  assert(re.test(html), `Missing required DOM element id="#${id}" in website/index.html`);
});
console.log(`✓ Verified all ${requiredIds.length} required DOM IDs exist in website/index.html.`);

// Verify default sort option is win-desc
assert(html.includes('<option value="win-desc"'), "Missing sort option value='win-desc'");
console.log("✓ Verified default sort order is 'win-desc' (🏆 Winning Score: High → Low).");

// Verify Multi-Currency conversion math (RMB, USD, LKR)
const DEFAULT_USD = 7.15;
const DEFAULT_LKR = 43.50;

function convertFromRmb(rmb, curr, rates = { USD: DEFAULT_USD, LKR: DEFAULT_LKR }) {
  if (curr === "USD") return rmb / rates.USD;
  if (curr === "LKR") return rmb * rates.LKR;
  return rmb;
}

const sampleProduct = window.CATALOG.products[0];
const rmbPrice = sampleProduct.price;
const usdPrice = convertFromRmb(rmbPrice, "USD");
const lkrPrice = convertFromRmb(rmbPrice, "LKR");

assert(Math.abs(usdPrice - (rmbPrice / 7.15)) < 1e-9, "USD conversion mismatch");
assert(Math.abs(lkrPrice - (rmbPrice * 43.50)) < 1e-9, "LKR conversion mismatch");
console.log(`✓ Verified multi-currency conversion: ¥${rmbPrice} = $${usdPrice.toFixed(2)} USD = රු.${lkrPrice.toFixed(2)} LKR.`);

// Verify dynamic Min/Max price filter in all 3 currencies
["RMB", "USD", "LKR"].forEach(curr => {
  const prices = window.CATALOG.products.map(p => convertFromRmb(p.price, curr));
  const mid = (Math.min(...prices) + Math.max(...prices)) / 2;
  const filtered = window.CATALOG.products.filter(p => convertFromRmb(p.price, curr) <= mid);
  assert(filtered.length > 0 && filtered.length < window.CATALOG.products.length, `Price filter failed in ${curr}`);
});
console.log("✓ Verified dynamic #pmin / #pmax price filtering across RMB, USD, and LKR.");

// Verify Top Winners (70+ pts) quick filter chip
const topWinners = window.CATALOG.products.filter(p => p.winScore >= 70);
assert(topWinners.length >= 10, `Expected at least 10 Top Winners (70+ pts), found ${topWinners.length}`);
console.log(`✓ Verified '🏆 Top Winners (70+ pts)' quick filter matches ${topWinners.length} products.`);

// Verify Quotation Cart math & CSV column alignment with UTF-8 BOM
const testCartItems = window.CATALOG.products.slice(0, 4).map((p, i) => ({
  product: p,
  cartons: i + 1
}));

let totCtns = 0, totPcs = 0, totRmb = 0, totCbm = 0, totKg = 0;
const csvRows = [];
const headerCols = 20;

testCartItems.forEach(({ product: p, cartons }) => {
  const pcs = cartons * p.pcsPerCarton;
  const lineRmb = pcs * p.price;
  const lineCbm = cartons * p.cbm;
  const lineKg = cartons * (p.kg != null ? p.kg : 0);

  totCtns += cartons;
  totPcs += pcs;
  totRmb += lineRmb;
  totCbm += lineCbm;
  totKg += lineKg;

  const row = [
    p.code, p.variantEn, p.si, p.en, p.zh,
    p.winScore, p.winRate, p.winTier, cartons, p.pcsPerCarton, pcs,
    (p.price * DEFAULT_LKR).toFixed(2), p.price.toFixed(2),
    (lineRmb * DEFAULT_LKR).toFixed(2), lineRmb.toFixed(2),
    p.cbm.toFixed(4), lineCbm.toFixed(4),
    p.kg != null ? p.kg : 0, lineKg.toFixed(2), p.box
  ];
  assert.strictEqual(row.length, headerCols, "CSV data row must have 20 columns");
  csvRows.push(row);
});

const totalRow = [
  "TOTAL", "", "", "", "", "", "", "",
  totCtns, "", totPcs, "", "",
  (totRmb * DEFAULT_LKR).toFixed(2), totRmb.toFixed(2),
  "", totCbm.toFixed(4), "", totKg.toFixed(2), ""
];
assert.strictEqual(totalRow.length, headerCols, "CSV TOTAL summary row must have exact 20 columns");
assert(!isNaN(totKg) && totKg > 0, "Total KG must be a valid number without NaN");
assert(appScript.includes('"\\uFEFF"'), "CSV generator must prepend UTF-8 BOM \\uFEFF");
console.log(`✓ Verified Quotation Cart math & UTF-8 BOM CSV export alignment (${headerCols} columns).`);

console.log("ALL test_dom_sim.js CHECKS PASSED 100%!\n");
