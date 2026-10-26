#!/usr/bin/env node
/**
 * test_mobile.js — Automated Verification of Mobile UX & Ergonomics (320px–480px)
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = __dirname;
const indexHtmlPath = path.join(ROOT, "website", "index.html");
const html = fs.readFileSync(indexHtmlPath, "utf8");

console.log("=== Running test_mobile.js (Mobile UX & Ergonomics 320px–480px) ===");

// 1. Viewport Meta Tag with viewport-fit=cover
assert(
  /meta\s+name=["']viewport["']\s+content=["']width=device-width,\s*initial-scale=1,\s*viewport-fit=cover["']/i.test(html),
  "Missing <meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'>"
);
console.log("✓ Verified viewport meta tag with viewport-fit=cover.");

// 2. Minimum 44x44px touch targets on interactive elements
assert(html.includes("min-width: 44px"), "CSS must enforce min-width: 44px on interactive controls");
assert(html.includes("min-height: 44px"), "CSS must enforce min-height: 44px on interactive controls");
const touchClasses = [".qadd", ".qty-step", ".gal-nav", ".rm", ".x", ".chip", "select"];
touchClasses.forEach(cls => {
  assert(html.includes(cls), `Missing touch target selector ${cls} in CSS`);
});
console.log(`✓ Verified minimum 44×44px touch target rules across ${touchClasses.join(", ")}.`);

// 3. iOS Auto-Zoom Prevention: font-size: 16px on inputs & selects
assert(/input,\s*select[\s\S]*?font-size:\s*16px/i.test(html), "Inputs and selects must have font-size: 16px");
console.log("✓ Verified font-size: 16px on <input> and <select> elements to prevent iOS auto-zoom.");

// 4. 2-Column Mobile Product Grid & 2-Line Clamped Titles
assert(
  html.includes("grid-template-columns: repeat(2, minmax(0, 1fr))"),
  "Missing 2-column mobile product card grid rule: grid-template-columns: repeat(2, minmax(0, 1fr))"
);
assert(
  html.includes("-webkit-line-clamp: 2"),
  "Missing 2-line title clamp rule: -webkit-line-clamp: 2"
);
console.log("✓ Verified 2-column mobile product grid and 2-line clamped card titles.");

// 5. Bottom Sheets on mobile (<= 640px) with .sheet-handle grabber bars & pull-down-to-dismiss
assert(html.includes("@media (max-width: 640px)"), "Missing @media (max-width: 640px) mobile breakpoint");
const handleMatches = [...html.matchAll(/class=["']sheet-handle["']/g)];
assert(handleMatches.length >= 3, "Expected .sheet-handle grabber bars on #detail, #cart, and #ratesModal");
assert(html.includes('data-dismiss="detail"'), "Missing data-dismiss='detail' on #detail .sheet-handle");
assert(html.includes('data-dismiss="cart"'), "Missing data-dismiss='cart' on #cart .sheet-handle");
assert(html.includes('data-dismiss="ratesModal"'), "Missing data-dismiss='ratesModal' on #ratesModal .sheet-handle");
assert(html.includes("translateY("), "Missing pull-down-to-dismiss touchmove transform on bottom sheets");
console.log("✓ Verified Bottom Sheet modals (#detail, #cart, #ratesModal) with .sheet-handle pull-down-to-dismiss.");

// 6. Product Detail Modal Mobile Ergonomics
assert(html.includes('id="dQtyMinus"') && html.includes('id="dQtyPlus"'), "Missing #dQtyMinus / #dQtyPlus steppers");
assert(html.includes('id="dPrevImg"') && html.includes('id="dNextImg"'), "Missing #dPrevImg / #dNextImg gallery arrows");
assert(html.includes('id="dThumbs"'), "Missing #dThumbs thumbnail strip");
assert(
  html.includes("#dThumbs, input, button, select"),
  "Touch swipe navigation must exclude #dThumbs, inputs, buttons, and selects"
);
assert(html.includes("detail-sticky-bar"), "Missing sticky bottom bar in Product Detail Modal");
console.log("✓ Verified Detail Modal steppers, gallery arrows, swipe navigation exclusions, and sticky bottom bar.");

// 7. Floating Mobile Cart Bar (#mobileCartBar) & Sticky Cart Total (#cartStickyTotal) + @media print
assert(html.includes('id="mobileCartBar"'), "Missing #mobileCartBar");
assert(html.includes('id="cartStickyTotal"'), "Missing #cartStickyTotal");
assert(html.includes("@media print"), "Missing @media print rules");
console.log("✓ Verified #mobileCartBar, #cartStickyTotal, and @media print stylesheet.");

console.log("ALL test_mobile.js CHECKS PASSED 100%!\n");
