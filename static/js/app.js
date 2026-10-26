/* ReValue AI — front-end wizard.
 * Single-page flow driven entirely by the /api/* endpoints in app.py.
 * No buying, selling, checkout or payment logic exists anywhere here. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const INR = (n) => "₹" + Number(n).toLocaleString("en-IN");

  async function api(path) {
    const r = await fetch(path);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(data.error || "Request failed"), { data });
    return data;
  }
  async function apiPost(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(data.error || "Request failed"), { data });
    return data;
  }

  // Small hand-drawn line-icon set (no emoji) so the UI doesn't read as a default AI build.
  // Every icon is a plain stroked SVG that inherits the surrounding text color via currentColor.
  const svg = (inner, vb = "0 0 24 24") =>
    `<svg viewBox="${vb}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" class="icon" aria-hidden="true">${inner}</svg>`;
  const ICON = {
    laptop: svg('<rect x="4" y="4" width="16" height="10" rx="1.3"/><path d="M2 17.5h20l-1.4 2.3a2 2 0 0 1-1.7 1H5.1a2 2 0 0 1-1.7-1L2 17.5z"/>'),
    desktop: svg('<rect x="6" y="3" width="9" height="14" rx="1.2"/><circle cx="10.5" cy="6.3" r=".4" fill="currentColor" stroke="none"/><line x1="8" y1="10" x2="13" y2="10"/><line x1="8" y1="12.5" x2="13" y2="12.5"/><line x1="10.5" y1="17" x2="10.5" y2="20"/><line x1="7.5" y1="21" x2="13.5" y2="21"/>'),
    chip: svg('<rect x="7" y="7" width="10" height="10" rx="1"/><line x1="9" y1="2" x2="9" y2="7"/><line x1="15" y1="2" x2="15" y2="7"/><line x1="9" y1="17" x2="9" y2="22"/><line x1="15" y1="17" x2="15" y2="22"/><line x1="2" y1="9" x2="7" y2="9"/><line x1="2" y1="15" x2="7" y2="15"/><line x1="17" y1="9" x2="22" y2="9"/><line x1="17" y1="15" x2="22" y2="15"/>'),
    monitor: svg('<rect x="3" y="4" width="18" height="12" rx="1.3"/><line x1="8" y1="20" x2="16" y2="20"/><line x1="12" y1="16" x2="12" y2="20"/>'),
    keyboard: svg('<rect x="2" y="6" width="20" height="12" rx="1.3"/><line x1="5" y1="10" x2="6.6" y2="10"/><line x1="9" y1="10" x2="10.6" y2="10"/><line x1="13" y1="10" x2="14.6" y2="10"/><line x1="17" y1="10" x2="18.6" y2="10"/><line x1="5" y1="13.3" x2="6.6" y2="13.3"/><line x1="9" y1="13.3" x2="10.6" y2="13.3"/><line x1="13" y1="13.3" x2="14.6" y2="13.3"/><line x1="17" y1="13.3" x2="18.6" y2="13.3"/><line x1="7" y1="16.3" x2="17" y2="16.3"/>'),
    cable: svg('<path d="M9 7V4M15 7V4M7 7h10v3.5a5 5 0 0 1-10 0V7z"/><line x1="12" y1="15.5" x2="12" y2="20"/>'),
    chart: svg('<line x1="4" y1="20" x2="20" y2="20"/><rect x="6" y="12" width="3" height="8"/><rect x="11" y="8" width="3" height="12"/><rect x="16" y="4" width="3" height="16"/>'),
    ban: svg('<circle cx="12" cy="12" r="9"/><line x1="5.8" y1="5.8" x2="18.2" y2="18.2"/>'),
    warning: svg('<path d="M12 3 2 20h20L12 3z"/><line x1="12" y1="9.5" x2="12" y2="14"/><circle cx="12" cy="16.8" r=".4" fill="currentColor"/>'),
    info: svg('<circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16.5"/><circle cx="12" cy="7.8" r=".4" fill="currentColor"/>'),
    check: svg('<polyline points="4 12 9 17 20 6"/>'),
    arrowLeft: svg('<line x1="19" y1="12" x2="5" y2="12"/><polyline points="11 6 5 12 11 18"/>'),
    box: svg('<path d="M12 3 3 7.5 12 12l9-4.5L12 3z"/><path d="M3 7.5V17L12 21.5 21 17V7.5"/><line x1="12" y1="12" x2="12" y2="21.5"/>'),
  };

  // ---------------------------------------------------------------- state
  const state = () => ({
    category: null, categoryName: "", subtype: null, subtypeName: "",
    schema: null, steps: [], stepPos: 0,
    brand: null, brandName: "", model_id: null,
    modelInfo: null,         // {model, fields, variants} from /api/model-specs
    specs: {}, condition: {}, accessories: [],
  });
  let S = state();

  function resetAll() { S = state(); }

  // -------------------------------------------------------------- view switch
  function showView(id) {
    ["home-view", "subtype-view", "wizard-view", "results-view"].forEach((v) => $("#" + v).classList.toggle("hidden", v !== id));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ------------------------------------------------------------------ home
  async function loadCategories() {
    const grid = $("#category-grid");
    try {
      const { categories } = await api("/api/categories");
      grid.innerHTML = categories.map((c) => `
        <button class="cat-card" data-cat="${c.id}">
          <div class="ic">${ICON[c.icon] || ICON.box}</div>
          <h3>${c.name}</h3>
          <p>${c.description}</p>
        </button>`).join("");
      $$(".cat-card", grid).forEach((btn) => btn.addEventListener("click", () => openCategory(btn.dataset.cat, categories)));
    } catch (e) {
      grid.innerHTML = `<div class="error-box">Could not load categories. Is the server running? (${e.message})</div>`;
    }
  }

  function openCategory(catId, categories) {
    const cat = categories.find((c) => c.id === catId);
    resetAll();
    S.category = catId; S.categoryName = cat.name;
    if (cat.subtypes && cat.subtypes.length) {
      renderSubtypeChoice(cat);
    } else {
      S.subtype = null;
      beginWizard();
    }
  }

  function renderSubtypeChoice(cat) {
    $("#subtype-heading").textContent = cat.name;
    $("#subtype-sub").textContent = "Choose the type that matches what you have.";
    const grid = $("#subtype-grid");
    grid.innerHTML = cat.subtypes.map((s) => `<button class="cat-card" data-sub="${s.id}"><h3>${s.name}</h3></button>`).join("");
    $$(".cat-card", grid).forEach((btn) => btn.addEventListener("click", () => {
      S.subtype = btn.dataset.sub; S.subtypeName = cat.subtypes.find((s) => s.id === btn.dataset.sub).name;
      beginWizard();
    }));
    showView("subtype-view");
  }

  // ---------------------------------------------------------------- wizard
  async function beginWizard() {
    showView("wizard-view");
    $("#step-card").innerHTML = `<div class="loading"><span class="spinner"></span> Loading form…</div>`;
    try {
      const qs = `category=${S.category}` + (S.subtype ? `&subtype=${S.subtype}` : "");
      S.schema = await api(`/api/schema?${qs}`);
      S.steps = S.schema.flow.filter((s) => s !== "accessories" || S.schema.accessories.length > 0);
      S.stepPos = 0;
      $("#wizard-title").textContent = `Value your ${S.schema.name}`;
      renderStep();
    } catch (e) {
      $("#step-card").innerHTML = `<div class="error-box">${e.message}</div>`;
    }
  }

  function stepTypeAt(pos) { return S.steps[pos]; }

  function updateProgress() {
    const total = S.steps.length + 1; // +1 for the final "review & calculate" moment
    const done = Math.min(S.stepPos, S.steps.length);
    $("#progress-fill").style.width = `${Math.round((done / total) * 100)}%`;
    $("#progress-label").textContent = `Step ${done + 1} of ${total}`;
  }

  async function renderStep() {
    updateProgress();
    renderSummary();
    const type = stepTypeAt(S.stepPos);
    if (type === undefined) return submitValuation();
    if (type === "brand") return renderBrandStep();
    if (type === "model") return renderModelStep();
    if (type === "specs" || type === "components") return renderSpecsStep();
    if (type === "condition") return renderConditionStep();
    if (type === "accessories") return renderAccessoriesStep();
  }

  let lastDirection = 1;    // tracks which way we're moving so auto-skipped steps (e.g. no models for
                             // this brand) skip in the SAME direction, instead of bouncing back and forth
  function goNext() { lastDirection = 1; S.stepPos += 1; renderStep(); }
  function goBack() {
    if (S.stepPos === 0) { backToCategories(); return; }
    lastDirection = -1; S.stepPos -= 1; renderStep();
  }
  function backToCategories() { resetAll(); showView("home-view"); }

  function stepCard(title, sub, bodyHtml, { backLabel = "Back", nextLabel = "Continue", nextDisabled = false } = {}) {
    $("#step-card").innerHTML = `
      <div class="step-head"><h3>${title}</h3>${sub ? `<p>${sub}</p>` : ""}</div>
      <div id="step-body">${bodyHtml}</div>
      <div class="wizard-actions">
        <button class="btn btn-ghost" id="back-btn">${backLabel}</button>
        <button class="btn btn-primary" id="next-btn" ${nextDisabled ? "disabled" : ""}>${nextLabel}</button>
      </div>`;
    $("#back-btn").addEventListener("click", goBack);
  }

  // ----------------------------------------------------------------- brand
  async function renderBrandStep() {
    $("#step-card").innerHTML = `<div class="loading"><span class="spinner"></span> Loading brands…</div>`;
    const qs = `category=${S.category}` + (S.subtype ? `&subtype=${S.subtype}` : "");
    const { brands } = await api(`/api/brands?${qs}`);
    stepCard("Select the brand", "Pick the brand that made your product.",
      `<div class="option-grid">${brands.map((b) => `
        <button class="option-card${S.brand === b.id ? " selected" : ""}" data-id="${b.id}" data-name="${b.name}">${b.name}</button>`).join("")}</div>`,
      { nextDisabled: true });
    $("#next-btn").classList.add("hidden"); // selecting a brand card advances automatically
    $$(".option-card", $("#step-body")).forEach((btn) => btn.addEventListener("click", () => {
      if (S.brand !== btn.dataset.id) { S.model_id = null; S.modelInfo = null; }
      S.brand = btn.dataset.id; S.brandName = btn.dataset.name;
      renderSummary(); goNext();
    }));
  }

  // ----------------------------------------------------------------- model
  async function renderModelStep() {
    $("#step-card").innerHTML = `<div class="loading"><span class="spinner"></span> Loading models…</div>`;
    const qs = `category=${S.category}${S.subtype ? `&subtype=${S.subtype}` : ""}&brand=${S.brand}`;
    const { models, manual_entry } = await api(`/api/models?${qs}`);
    if (manual_entry) {
      // No database entries for this brand: the specs step collects the model by hand instead.
      // Skip in whichever direction the user was already moving, so "Back" from the next step
      // returns to the brand step instead of bouncing forward through this one again.
      if (lastDirection < 0) goBack(); else goNext();
      return;
    }
    stepCard("Select the exact model", "Pick the specific model so we can retrieve known specifications.",
      `<div class="option-grid">${models.map((m) => `
        <button class="option-card${S.model_id === m.id ? " selected" : ""}${m.verified === false ? " unverified" : ""}" data-id="${m.id}" data-name="${m.name}">
          ${m.name}${m.series ? `<span class="sub">${m.series}</span>` : ""}
        </button>`).join("")}</div>`,
      { nextDisabled: true });
    $("#next-btn").classList.add("hidden");
    $$(".option-card", $("#step-body")).forEach((btn) => btn.addEventListener("click", async () => {
      S.model_id = btn.dataset.id;
      const nameOnly = btn.dataset.name;
      const msQs = `category=${S.category}${S.subtype ? `&subtype=${S.subtype}` : ""}&model_id=${S.model_id}`;
      S.modelInfo = await api(`/api/model-specs?${msQs}`);
      // pre-fill known/confirm values so the specs step opens already populated
      Object.entries(S.modelInfo.fields || {}).forEach(([fid, f]) => {
        if ((f.status === "known" || f.status === "confirm") && "value" in f) S.specs[fid] = f.value;
      });
      if (!S.modelInfo.model) S.modelInfo.model = { name: nameOnly };
      renderSummary(); goNext();
    }));
  }

  // ----------------------------------------------------------------- specs
  function isVisible(field, values) {
    if (!field.show_if) return true;
    const v = values[field.show_if.field];
    return field.show_if.in.map(String).includes(String(v));
  }

  function fieldStatus(fid) {
    const f = S.modelInfo && S.modelInfo.fields && S.modelInfo.fields[fid];
    return f || null;
  }

  function renderSelectField(field, value, opts) {
    const options = opts || field.options || [];
    const labelOf = (o) => (field.option_labels && field.option_labels[o]) || o;
    if (options.length > 0 && options.length <= 4 && field.type === "select") {
      return `<div class="pill-group" data-field="${field.id}" data-type="select">
        ${options.map((o) => `<button type="button" class="pill${String(value) === String(o) ? " selected" : ""}" data-val="${o}">${labelOf(o)}</button>`).join("")}
      </div>`;
    }
    return `<select data-field="${field.id}">
      <option value="">Select…</option>
      ${options.map((o) => `<option value="${o}" ${String(value) === String(o) ? "selected" : ""}>${labelOf(o)}</option>`).join("")}
    </select>`;
  }

  function renderMultiselect(field, value) {
    const sel = Array.isArray(value) ? value : [];
    return `<div class="pill-group" data-field="${field.id}" data-type="multiselect">
      ${(field.options || []).map((o) => `<button type="button" class="pill${sel.includes(o) ? " selected" : ""}" data-val="${o}">${o}</button>`).join("")}
    </div>`;
  }

  function renderOneField(field, values, { forceOptions } = {}) {
    if (field.type === "info") return "";
    const status = fieldStatus(field.id);
    if (status && status.status === "known") {
      return `<div class="field"><label>${field.label}</label>
        <input type="text" value="${status.value ?? ""}" disabled>
        <span class="known-tag">Confirmed from model data</span></div>`;
    }
    // A "choose" status from the model (e.g. this GPU chip came in 8GB or 12GB) sets the
    // options the user must pick between; it always wins over any generic options passed in.
    if (status && status.status === "choose" && status.options) forceOptions = status.options;
    const note = (status && status.note) || field.note;
    const value = values[field.id];
    let control;
    if (field.type === "select") control = renderSelectField(field, value, forceOptions);
    else if (field.type === "multiselect") control = renderMultiselect(field, value);
    else if (field.type === "number") control = `<input type="number" data-field="${field.id}" value="${value ?? ""}" placeholder="${field.allow_unknown ? 'Leave blank if unknown' : ''}">`;
    else control = `<input type="text" data-field="${field.id}" value="${value ?? ""}" placeholder="${field.allow_unknown ? 'Leave blank if unknown' : ''}">`;
    return `<div class="field ${field.type === 'select' && (forceOptions || field.options || []).length > 4 ? '' : ''}">
      <label>${field.label}${field.required ? " *" : ""}</label>
      ${control}
      ${note ? `<span class="hint">${note}</span>` : ""}
      ${field.allow_unknown && field.type !== "multiselect" ? `<label style="font-weight:400;font-size:.78rem;color:var(--muted)">
        <input type="checkbox" data-unknown-for="${field.id}" ${value === "Unknown" ? "checked" : ""}> I don't know</label>` : ""}
    </div>`;
  }

  // Replacing a form's innerHTML while the user is mid-keystroke destroys and recreates the
  // input element, so the browser drops focus and the next character goes nowhere. Every form
  // repaint in this file goes through here instead of a bare `el.innerHTML = ...` so focus and
  // the cursor position survive the rebuild.
  function setHtmlPreservingFocus(container, html) {
    const active = container.contains(document.activeElement) ? document.activeElement : null;
    const focusField = active && active.dataset ? active.dataset.field : null;
    const selStart = active && typeof active.selectionStart === "number" ? active.selectionStart : null;
    const selEnd = active && typeof active.selectionEnd === "number" ? active.selectionEnd : null;
    container.innerHTML = html;
    if (!focusField) return;
    const el = container.querySelector(`[data-field="${focusField}"]`);
    if (el && (el.tagName === "INPUT" || el.tagName === "SELECT")) {
      el.focus();
      if (selStart !== null && el.setSelectionRange) { try { el.setSelectionRange(selStart, selEnd); } catch (e) { /* not a text-selectable input type */ } }
    }
  }

  function wireFieldEvents(container, values, onChange) {
    $$("select[data-field], input[type=text][data-field], input[type=number][data-field]", container).forEach((el) => {
      el.addEventListener("input", () => { values[el.dataset.field] = el.value === "" ? null : el.value; onChange(el.dataset.field); });
    });
    $$("input[data-unknown-for]", container).forEach((el) => {
      el.addEventListener("change", () => {
        const fid = el.dataset.unknownFor;
        values[fid] = el.checked ? "Unknown" : null;
        const sibling = container.querySelector(`[data-field="${fid}"]`);
        if (sibling) { sibling.disabled = el.checked; if (el.checked) sibling.value = ""; }
        onChange(fid);
      });
    });
    $$('[data-type="select"] .pill', container).forEach((btn) => {
      btn.addEventListener("click", () => {
        const group = btn.closest("[data-field]");
        values[group.dataset.field] = btn.dataset.val;
        $$(".pill", group).forEach((p) => p.classList.toggle("selected", p === btn));
        onChange(group.dataset.field);
      });
    });
    $$('[data-type="multiselect"]', container).forEach((group) => {
      $$(".pill", group).forEach((btn) => btn.addEventListener("click", () => {
        const fid = group.dataset.field; const cur = Array.isArray(values[fid]) ? values[fid].slice() : [];
        const v = btn.dataset.val;
        if (v === "None") { values[fid] = cur.includes("None") ? [] : ["None"]; }
        else {
          let next = cur.filter((x) => x !== "None");
          next = next.includes(v) ? next.filter((x) => x !== v) : [...next, v];
          values[fid] = next;
        }
        $$(".pill", group).forEach((p) => p.classList.toggle("selected", (values[fid] || []).includes(p.dataset.val)));
        onChange(fid);
      }));
    });
  }

  async function renderSpecsStep() {
    const fields = S.schema.spec_fields;
    const modelLine = S.modelInfo && S.modelInfo.model
      ? `<p class="hint">${S.modelInfo.model.name}${S.modelInfo.model.source_note ? " — " + S.modelInfo.model.source_note : ""}</p>` : "";
    stepCard("Specifications", "We only ask what we don't already know." + "", modelLine +
      `<div class="form-grid" id="specs-grid"></div>`);
    const grid = $("#specs-grid");

    function paint() {
      const html = fields.filter((f) => isVisible(f, S.specs)).map((f) => {
        const full = f.type === "multiselect" || (f.options || []).length > 6;
        return `<div class="${full ? 'field full' : ''}">${renderOneField(f, S.specs)}</div>`;
      }).join("");
      setHtmlPreservingFocus(grid, html);
      wireFieldEvents(grid, S.specs, onFieldChange);
      refreshValidity();
    }

    async function onFieldChange(fid) {
      // Only rebuild the form when the changed field actually affects something else on the
      // page (it shows/hides a dependent field, or drives a dynamic option list like the
      // graphics dropdowns). A plain field with no dependents never needs a repaint — and
      // skipping it is what keeps typing in a text/number box from losing your cursor, since
      // the input element is never destroyed while you're mid-keystroke.
      const isOptionDriver = (fid === "cpu" && fields.some((f) => f.id === "igpu_model")) || fid === "dgpu_model";
      const hasDependents = fields.some((f) => f.show_if && f.show_if.field === fid);
      if (isOptionDriver) {
        if (fid === "cpu") await loadIgpuOptions();
        if (fid === "dgpu_model") await loadVramOptions();
      }
      if (isOptionDriver || hasDependents) paint();
      else refreshValidity();
      renderSummary();
    }

    async function loadIgpuOptions() {
      const f = fields.find((x) => x.id === "igpu_model"); if (!f) return;
      const cpu = S.specs.cpu || "";
      try {
        const r = await api(`/api/graphics/options?cpu=${encodeURIComponent(cpu)}`);
        f.options = r.options.map((o) => o.name);
        f._memoryNote = r.options[0] ? r.options[0].memory.label : null;
      } catch (e) { /* keep previous options */ }
    }
    async function loadVramOptions() {
      const f = fields.find((x) => x.id === "dgpu_vram_gb"); if (!f) return;
      const dgpu = S.specs.dgpu_model || "";
      if (!dgpu) { f.options = []; return; }
      try { const r = await api(`/api/graphics/vram?dgpu=${encodeURIComponent(dgpu)}`); f.options = r.vram_gb; }
      catch (e) { f.options = []; }
    }
    if (fields.some((f) => f.id === "igpu_model")) await loadIgpuOptions();
    if (S.specs.dgpu_model) await loadVramOptions();

    function refreshValidity() {
      const missing = fields.filter((f) => f.required && isVisible(f, S.specs) && f.type !== "info")
        .filter((f) => S.specs[f.id] === undefined || S.specs[f.id] === null || S.specs[f.id] === "");
      $("#next-btn").disabled = missing.length > 0;
    }

    paint();
    $("#next-btn").addEventListener("click", goNext);
  }

  // -------------------------------------------------------------- condition
  async function renderConditionStep() {
    const fields = S.schema.condition_fields;
    stepCard("Condition assessment", "Tell us about its age and condition.", `<div class="form-grid" id="cond-grid"></div>`);
    const grid = $("#cond-grid");
    function paint() {
      const html = fields.filter((f) => isVisible(f, S.condition)).map((f) => {
        const full = f.type === "multiselect" || (f.options || []).length > 6;
        return `<div class="${full ? 'field full' : ''}">${renderConditionField(f, S.condition)}</div>`;
      }).join("");
      setHtmlPreservingFocus(grid, html);
      wireFieldEvents(grid, S.condition, (fid) => {
        // Same rule as the specs step: only rebuild when the field controls another field's
        // visibility (e.g. warranty_available shows/hides warranty_left); otherwise just revalidate.
        const hasDependents = fields.some((f) => f.show_if && f.show_if.field === fid);
        if (hasDependents) paint(); else refreshValidity();
        renderSummary();
      });
      refreshValidity();
    }
    function renderConditionField(field) {
      // condition fields never come from model data, so reuse the generic renderer without "known" short-circuit
      const saved = fieldStatus; // no-op shadow to keep renderOneField generic-safe
      return renderOneFieldNoModel(field, S.condition);
    }
    function refreshValidity() {
      const missing = fields.filter((f) => f.required && isVisible(f, S.condition)).filter((f) => {
        const v = S.condition[f.id];
        return v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0);
      });
      $("#next-btn").disabled = missing.length > 0;
    }
    paint();
    $("#next-btn").addEventListener("click", goNext);
  }

  function renderOneFieldNoModel(field, values) {
    if (field.type === "info") return "";
    const value = values[field.id];
    let control;
    if (field.type === "select") control = renderSelectField(field, value);
    else if (field.type === "multiselect") control = renderMultiselect(field, value);
    else if (field.type === "number") control = `<input type="number" data-field="${field.id}" value="${value ?? ""}">`;
    else control = `<input type="text" data-field="${field.id}" value="${value ?? ""}">`;
    return `<div class="field"><label>${field.label}${field.required ? " *" : ""}</label>${control}</div>`;
  }

  // ------------------------------------------------------------ accessories
  function renderAccessoriesStep() {
    const list = S.schema.accessories;
    stepCard("Included accessories", "Select anything that comes with it. This only affects the valuation — nothing is shipped.",
      `<div class="accessory-grid" id="acc-grid">${list.map((a) => `
        <button type="button" class="accessory-card${S.accessories.includes(a) ? " selected" : ""}" data-val="${a}">
          <span class="box">${S.accessories.includes(a) ? ICON.check : ""}</span>${a}</button>`).join("")}</div>`,
      { nextLabel: "Review & calculate" });
    $$(".accessory-card", $("#acc-grid")).forEach((btn) => btn.addEventListener("click", () => {
      const v = btn.dataset.val;
      S.accessories = S.accessories.includes(v) ? S.accessories.filter((x) => x !== v) : [...S.accessories, v];
      btn.classList.toggle("selected"); btn.querySelector(".box").innerHTML = S.accessories.includes(v) ? ICON.check : "";
      renderSummary();
    }));
    $("#next-btn").addEventListener("click", goNext);
  }

  // ------------------------------------------------------------------ summary
  function fmtVal(v) { return Array.isArray(v) ? v.join(", ") : v; }
  function renderSummary() {
    const rows = [];
    if (S.categoryName) rows.push(["Category", S.subtypeName || S.categoryName]);
    if (S.brandName) rows.push(["Brand", S.brandName]);
    if (S.modelInfo && S.modelInfo.model) rows.push(["Model", S.modelInfo.model.name]);
    if (S.schema) {
      S.schema.spec_fields.forEach((f) => { if (f.type !== "info" && isVisible(f, S.specs) && S.specs[f.id]) rows.push([f.label, fmtVal(S.specs[f.id])]); });
      S.schema.condition_fields.forEach((f) => { if (isVisible(f, S.condition) && S.condition[f.id]) rows.push([f.label, fmtVal(S.condition[f.id])]); });
    }
    if (S.accessories.length) rows.push(["Accessories", S.accessories.join(", ")]);
    $("#summary-body").innerHTML = rows.length
      ? rows.map(([k, v]) => `<div class="summary-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join("")
      : `<p class="summary-empty">Nothing selected yet.</p>`;
  }

  // --------------------------------------------------------------- submit
  async function submitValuation() {
    $("#step-card").innerHTML = `<div class="loading"><span class="spinner"></span> Calculating your estimate…</div>`;
    try {
      const body = { category: S.category, subtype: S.subtype, brand: S.brand, model_id: S.model_id,
                     specs: S.specs, condition: S.condition, accessories: S.accessories };
      const result = await apiPost("/api/predict", body);
      renderResults(result);
    } catch (e) {
      const details = (e.data && e.data.details) ? `<ul>${e.data.details.map((d) => `<li>${d}</li>`).join("")}</ul>` : "";
      stepCard("Something needs attention", "", `<div class="error-box">${e.message}${details}</div>`, { nextLabel: "" });
      $("#next-btn").classList.add("hidden");
    }
  }

  function renderResults(r) {
    const specRows = r.confirmed_specs.map((x) => `<span class="k">${x.label}</span><span class="v">${x.value}</span>`).join("");
    const condRows = r.condition_summary.map((x) => `<span class="k">${x.label}</span><span class="v">${x.value}</span>`).join("");
    const factors = r.factors.length
      ? r.factors.map((f) => `<div class="factor"><span>${f.text}</span><span class="amt ${f.impact_inr < 0 ? "neg" : "pos"}">${f.impact_inr < 0 ? "−" : "+"}${INR(Math.abs(f.impact_inr))}</span></div>`).join("")
      : `<p class="muted">No single factor stood out for this item.</p>`;
    const unknownNote = r.unknown_inputs.length
      ? `<div class="banner">${ICON.warning} <span>Treated as unknown and estimated from typical values: ${r.unknown_inputs.join(", ")}.</span></div>` : "";
    const assumptions = r.assumptions.length ? `<div class="banner">${ICON.info} <span>${r.assumptions.join(" ")}</span></div>` : "";

    $("#results-body").innerHTML = `
      <button class="btn-text" id="results-back-btn">${ICON.arrowLeft} Edit answers</button>
      <h2>${r.product.name}</h2>
      <p class="section-sub">${r.product.type}${r.product.brand ? " · " + r.product.brand : ""}</p>
      ${unknownNote}${assumptions}
      <div class="result-top">
        <div class="price-card">
          <div class="label">Estimated resale value</div>
          <div class="price">${INR(r.estimate_inr)}</div>
          <div class="range">Typical range: ${INR(r.range_inr.low)} – ${INR(r.range_inr.high)}</div>
          <div class="algo">${r.range_basis}<br>Model: ${r.model_info.algorithm} · ${r.data_note}</div>
        </div>
        <div class="card info-card">
          <h4>Confirmed specifications</h4>
          <div class="spec-list">${specRows || "<span class='muted'>—</span>"}</div>
          <h4 style="margin-top:16px">Condition summary</h4>
          <div class="spec-list">${condRows || "<span class='muted'>—</span>"}</div>
        </div>
      </div>
      <div class="card">
        <h4>What affects this estimate</h4>
        <div class="factor-list">${factors}</div>
      </div>
      <div class="result-actions">
        <button class="btn btn-primary" id="value-another-btn">Value another item</button>
        <button class="btn btn-ghost" id="edit-answers-btn">Edit this valuation</button>
      </div>
      <div class="disclaimer-box">${r.disclaimer}</div>`;
    showView("results-view");
    $("#results-back-btn").addEventListener("click", () => { showView("wizard-view"); S.stepPos = S.steps.length - 1; renderStep(); });
    $("#edit-answers-btn").addEventListener("click", () => { showView("wizard-view"); S.stepPos = S.steps.length - 1; renderStep(); });
    $("#value-another-btn").addEventListener("click", () => { resetAll(); showView("home-view"); });
  }

  // ------------------------------------------------------------------- init
  document.addEventListener("DOMContentLoaded", () => {
    loadCategories();
    $("#start-btn").addEventListener("click", () => document.getElementById("categories").scrollIntoView({ behavior: "smooth" }));
    $("#brand-home-btn").addEventListener("click", () => { resetAll(); showView("home-view"); });
    $("#subtype-back-btn").addEventListener("click", () => { resetAll(); showView("home-view"); });
    $("#wizard-back-to-cats").addEventListener("click", () => { resetAll(); showView("home-view"); });
  });
})();
