// End-to-end UI test: loads the real page + app.js in jsdom against the live Flask
// server and drives real clicks, exactly like a user. Run: node check_ui.mjs
// (requires `python app.py` running on http://127.0.0.1:5050 and `npm i jsdom`)
import { JSDOM } from "jsdom";

const BASE = "http://127.0.0.1:5050";
let failures = 0;
const fail = (msg) => { failures++; console.log("FAIL:", msg); };
const ok = (cond, msg) => { if (!cond) fail(msg); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function newPage() {
  const html = await (await fetch(BASE + "/")).text();
  const js = await (await fetch(BASE + "/static/js/app.js")).text();
  const css = ""; // not needed for logic tests
  const dom = new JSDOM(html, { url: BASE + "/", runScripts: "outside-only", pretendToBeVisual: true });
  dom.window.fetch = (url, opts) => fetch(url.startsWith("http") ? url : BASE + url, opts);
  dom.window.scrollTo = () => {};
  dom.window.HTMLElement.prototype.scrollIntoView = () => {};
  dom.window.onerror = (m) => console.log("WINDOW ERROR:", m);
  dom.window.addEventListener("unhandledrejection", (e) => console.log("UNHANDLED REJECTION:", e.reason));
  dom.window.eval(js);
  dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true, cancelable: true }));
  await sleep(150);
  return dom;
}

const $ = (dom, sel) => dom.window.document.querySelector(sel);
const $$ = (dom, sel) => Array.from(dom.window.document.querySelectorAll(sel));
const visible = (el) => el && !el.closest(".hidden") && !el.classList.contains("hidden");
const click = async (el) => { el.dispatchEvent(new (el.ownerDocument.defaultView).Event("click", { bubbles: true })); await sleep(120); };
const setVal = async (dom, sel, val) => {
  const el = $(dom, sel); el.value = val;
  el.dispatchEvent(new dom.window.Event("input", { bubbles: true })); await sleep(60);
};

// ---------------------------------------------------------------- Test 1: homepage
{
  const dom = await newPage();
  const cards = $$(dom, "#category-grid .cat-card");
  ok(cards.length === 6, `homepage: expected 6 category cards, got ${cards.length}`);
  ok(cards.some((c) => c.textContent.includes("Laptops")), "homepage: Laptops card present");
  ok(!dom.window.document.body.innerHTML.toLowerCase().includes("buy now"), "homepage: no 'buy now' text");
  ok(!dom.window.document.body.innerHTML.toLowerCase().includes("sell now"), "homepage: no 'sell now' text");
}

// ----------------------------------------- Test 2: full laptop flow (verified model)
{
  const dom = await newPage();
  $$(dom, "#category-grid .cat-card").find((c) => c.dataset.cat === "laptops").dispatchEvent(new dom.window.Event("click", { bubbles: true }));
  await sleep(250);
  ok(visible($(dom, "#wizard-view")), "laptop: wizard view should open directly (no subtype step)");

  // brand step: pick HP
  let brandBtn = $$(dom, ".option-card").find((b) => b.textContent.trim() === "HP");
  ok(!!brandBtn, "laptop: HP brand card present");
  await click(brandBtn);

  // model step: pick the verified Victus
  await sleep(200);
  let modelBtn = $$(dom, ".option-card").find((b) => b.textContent.includes("HP Victus 15 fb3009AX"));
  ok(!!modelBtn, "laptop: Victus model card present");
  ok(!modelBtn.classList.contains("unverified"), "laptop: verified Victus must not show the unverified badge");
  let dellPav = $$(dom, ".option-card").find((b) => b.textContent.includes("HP Pavilion"));
  ok(dellPav && dellPav.classList.contains("unverified"), "laptop: unverified Pavilion seed should show the unverified badge");
  await click(modelBtn);

  // specs step: CPU/RAM/storage/display should be pre-filled & disabled ("known"), only battery_health asked
  await sleep(200);
  const cpuInput = $$(dom, "input[disabled]").find((i) => i.value.includes("Ryzen 5 8645HS"));
  ok(!!cpuInput, "laptop: CPU field shown as a disabled, confirmed value");
  const ramLayoutLabel = $$(dom, ".field label").find((l) => l.textContent.includes("RAM configuration"));
  ok(!!ramLayoutLabel, "laptop: disputed RAM layout must still be asked (not silently assumed)");
  let nextBtn = $(dom, "#next-btn");
  ok(nextBtn.disabled, "laptop: Continue should be disabled until required battery_health is answered");
  const batteryGroup = $$(dom, '[data-field="battery_health"] .pill')[0];
  ok(!!batteryGroup, "laptop: battery_health pill options present");
  await click(batteryGroup);
  ok(!$(dom, "#next-btn").disabled, "laptop: Continue should enable once battery_health is answered");
  await click($(dom, "#next-btn"));

  // condition step
  await sleep(150);
  ok($(dom, "#step-body").textContent.includes("Purchase year"), "laptop: condition step shows purchase year");
  await setVal(dom, '[data-field="purchase_year"]', "2024");
  const physPill = $$(dom, '[data-field="physical_condition"] .pill').find((p) => p.dataset.val === "Good (light wear)");
  await click(physPill);
  const workPill = $$(dom, '[data-field="working_status"] .pill').find((p) => p.dataset.val === "Fully working");
  await click(workPill);
  const repairPill = $$(dom, '[data-field="repair_history"] .pill').find((p) => p.dataset.val === "No");
  await click(repairPill);
  const warrPill = $$(dom, '[data-field="warranty_available"] .pill').find((p) => p.dataset.val === "No");
  await click(warrPill);
  const nonePill = $$(dom, '[data-field="issues"] .pill').find((p) => p.dataset.val === "None");
  await click(nonePill);
  ok(!$(dom, "#next-btn").disabled, "laptop: Continue should enable once all required condition fields are answered");
  await click($(dom, "#next-btn"));

  // accessories step
  await sleep(150);
  ok($(dom, "#step-body").textContent.includes("Original charger"), "laptop: accessories step lists Original charger");
  const chargerCard = $$(dom, ".accessory-card").find((c) => c.dataset.val === "Original charger");
  await click(chargerCard);
  ok(chargerCard.classList.contains("selected"), "laptop: accessory card should toggle selected");
  await click($(dom, "#next-btn"));

  // results
  await sleep(400);
  ok(visible($(dom, "#results-view")), "laptop: results view should be visible after submit");
  const priceText = $(dom, ".price-card .price")?.textContent || "";
  ok(/₹[\d,]+/.test(priceText), `laptop: a rupee price should render, got "${priceText}"`);
  ok($(dom, "#results-body").textContent.includes("HP Victus"), "laptop: results show the product name");
  ok($(dom, "#results-body").textContent.toLowerCase().includes("not a guaranteed"), "laptop: disclaimer text present");
  const bodyLower = $(dom, "#results-body").textContent.toLowerCase();
  // whole-word check: "selling price" legitimately contains "sell", so match word boundaries, not substrings
  ["buy", "sell", "checkout", "payment", "pickup", "cart"].forEach((w) =>
    ok(!new RegExp(`\\b${w}\\b`).test(bodyLower), `laptop results: must not mention '${w}' as a standalone word`));
}

// ------------------------------------------------------- Test 3: components -> GPU (subtype step + graphics-free flow)
{
  const dom = await newPage();
  $$(dom, "#category-grid .cat-card").find((c) => c.dataset.cat === "components").dispatchEvent(new dom.window.Event("click", { bubbles: true }));
  await sleep(200);
  ok(visible($(dom, "#subtype-view")), "components: subtype view should show (multiple subtypes)");
  const gpuCard = $$(dom, "#subtype-grid .cat-card").find((c) => c.dataset.sub === "gpu");
  ok(!!gpuCard, "components: GPU subtype card present");
  await click(gpuCard);

  await sleep(200);
  const asusBrand = $$(dom, ".option-card").find((b) => b.textContent.trim() === "ASUS");
  ok(!!asusBrand, "gpu: ASUS board brand present");
  await click(asusBrand);
  await sleep(200);
  const rtxModel = $$(dom, ".option-card").find((b) => b.textContent.includes("RTX 3060"));
  ok(!!rtxModel, "gpu: RTX 3060 model card present");
  await click(rtxModel);

  await sleep(250);
  // interface renders as a pill-group (<=4 options): pick PCIe 4.0
  const ifacePill = $$(dom, '[data-field="interface"] .pill').find((p) => p.dataset.val === "PCIe 4.0");
  ok(!!ifacePill, "gpu: interface pill options present");
  if (ifacePill) await click(ifacePill);
  // VRAM capacity: the GPU has 2 known options (8/12 GB); with <=4 options the UI renders pills, not a <select>
  const vramPills = $$(dom, '[data-field="vram_gb"] .pill');
  const vramOptionValues = vramPills.map((p) => p.dataset.val);
  ok(vramOptionValues.length === 2 && vramOptionValues.includes("8") && vramOptionValues.includes("12"),
    `gpu: vram_gb options should be the model's own [8, 12], got [${vramOptionValues}]`);
  const vram8 = vramPills.find((p) => p.dataset.val === "8");
  if (vram8) await click(vram8);
  await sleep(100);
  if (!$(dom, "#next-btn").disabled) await click($(dom, "#next-btn"));
  else fail("gpu: Continue stayed disabled on the specs step — a required field may be unhandled");

  await sleep(150);
  // condition
  await setVal(dom, '[data-field="purchase_year"]', "2023");
  let p;
  p = $$(dom, '[data-field="physical_condition"] .pill').find((x) => x.dataset.val === "Good (light wear)"); if (p) await click(p);
  p = $$(dom, '[data-field="working_status"] .pill').find((x) => x.dataset.val === "Fully working"); if (p) await click(p);
  p = $$(dom, '[data-field="repair_history"] .pill').find((x) => x.dataset.val === "No"); if (p) await click(p);
  p = $$(dom, '[data-field="warranty_available"] .pill').find((x) => x.dataset.val === "No"); if (p) await click(p);
  p = $$(dom, '[data-field="issues"] .pill').find((x) => x.dataset.val === "None"); if (p) await click(p);
  if (!$(dom, "#next-btn").disabled) await click($(dom, "#next-btn"));
  else fail("gpu: Continue stayed disabled on the condition step");

  await sleep(150);
  if (visible($(dom, "#wizard-view")) && ($(dom, ".step-head h3")?.textContent || "").includes("accessories")) {
    await click($(dom, "#next-btn"));
  }
  await sleep(400);
  ok(visible($(dom, "#results-view")), "gpu: results view should show after full flow");
  ok(/₹[\d,]+/.test($(dom, ".price-card .price")?.textContent || ""), "gpu: a price should render");
}

// --------------------------------------------------------- Test 4: back navigation
{
  const dom = await newPage();
  $$(dom, "#category-grid .cat-card").find((c) => c.dataset.cat === "monitors").dispatchEvent(new dom.window.Event("click", { bubbles: true }));
  await sleep(200);
  ok(visible($(dom, "#wizard-view")), "monitors: wizard should open (brand-only first step)");
  const dellBrand = $$(dom, ".option-card").find((b) => b.textContent.trim() === "Dell");
  await click(dellBrand);
  await sleep(150);
  ok($(dom, "#step-body").textContent.includes("Exact model"), "monitors: manual entry should ask for the exact model");
  await click($(dom, "#back-btn"));
  await sleep(150);
  ok($(dom, "#step-body").textContent.includes("Dell"), "monitors: going back should return to the brand step");
}

// ----------------------------------------------- Test 5: typing must not lose focus (regression)
// Bug: every keystroke repainted the whole form, destroying and recreating the input, so the
// browser dropped focus after a single character. This simulates real typing, one key at a time.
{
  const dom = await newPage();
  $$(dom, "#category-grid .cat-card").find((c) => c.dataset.cat === "monitors").dispatchEvent(new dom.window.Event("click", { bubbles: true }));
  await sleep(200);
  const dellBrand = $$(dom, ".option-card").find((b) => b.textContent.trim() === "Dell");
  await click(dellBrand);
  await sleep(200); // now on the specs step: "Exact model" is a free-text field

  const typeChar = async (sel, ch) => {
    const el = $(dom, sel);
    el.focus();
    el.value = (el.value || "") + ch;
    el.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    await sleep(40);
  };
  const target = "Dell UltraSharp U2422H";
  for (const ch of target) await typeChar('input[data-field="model_name"]', ch);

  const finalEl = $(dom, 'input[data-field="model_name"]');
  ok(finalEl.value === target, `typing: value should accumulate to "${target}", got "${finalEl?.value}"`);
  ok(dom.window.document.activeElement === finalEl, "typing: the field must still be focused after typing, not kicked out");
}

// -------------------------------------- Test 6: number fields must not reverse digits (regression)
// Bug: every keystroke repainted the whole grid; <input type=number> doesn't reliably report a
// cursor position in all browsers, so the cursor restore could land at position 0, and each new
// digit got inserted at the START instead of the end — typing "5600" produced "0065". The fix
// stops repainting fields that have no effect on anything else on the page.
{
  const dom = await newPage();
  $$(dom, "#category-grid .cat-card").find((c) => c.dataset.cat === "laptops").dispatchEvent(new dom.window.Event("click", { bubbles: true }));
  await sleep(200);
  await click($$(dom, ".option-card").find((b) => b.textContent.trim() === "HP"));
  // Pavilion is an unverified seed model, so ram_speed_mts stays a free-typed number field
  await click($$(dom, ".option-card").find((b) => b.textContent.includes("HP Pavilion")));
  await sleep(200);

  const typeDigits = async (sel, digits) => {
    for (const ch of digits) {
      const el = $(dom, sel);
      el.focus();
      el.value = (el.value || "") + ch;
      el.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
      await sleep(30);
    }
  };
  // ram_speed_mts has no show_if dependents and isn't a graphics option driver, so it must never
  // trigger a repaint — this is the exact field type/shape that reproduced the bug.
  const ramField = $(dom, 'input[data-field="ram_speed_mts"]');
  ok(!!ramField, "number-typing: ram_speed_mts field should be present for an unverified model");
  if (ramField) {
    // The real root cause: a field with no dependents must never be repainted while typed in, so
    // the exact same DOM node should still be there afterwards. (jsdom doesn't reproduce the
    // real-browser cursor quirk that turned a repaint into reversed digits, so this checks the
    // actual fix — no repaint at all — rather than relying on cursor-position emulation.)
    await typeDigits('input[data-field="ram_speed_mts"]', "5600");
    const finalEl = $(dom, 'input[data-field="ram_speed_mts"]');
    ok(finalEl === ramField, "number-typing: the input element must not be recreated while typing (no repaint)");
    ok(finalEl.value === "5600", `number-typing: typing "5600" should produce "5600", got "${finalEl?.value}"`);
    ok(dom.window.document.activeElement === finalEl, "number-typing: field must stay focused while typing digits");
  }
}

console.log(failures === 0 ? "\nOK: all UI checks passed" : `\n${failures} UI check(s) FAILED`);
process.exit(failures === 0 ? 0 : 1);
