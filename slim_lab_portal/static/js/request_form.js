// New testing request form. Choices come from GET /api/reference (the SLIM reference cache);
// the form posts JSON to POST /api/submissions and shows the server's field errors.
// Samples are a spreadsheet-like table with one checkbox column per analysis in use (the
// "analysis matrix"): add analyses by searching (or "Browse all"); tick rows to change several
// samples at once from the selection bar; paste a column of IDs to add rows; Ctrl+D fills down.
// No inline scripts (CSP): this file is loaded with <script src> and wires everything up.
(() => {
  "use strict";

  const form = document.getElementById("request-form");
  if (!form) return;
  const isStaff = form.dataset.staff === "1";
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const $ = (id) => document.getElementById(id);
  const tbody = $("samples");
  const errorBox = $("form-error");

  let ref = null;           // /api/reference payload
  let requestType = null;   // RequestType value (1 Chemical, 2 Water, 3 Wafer)
  let samples = [];         // [{key, sample_name, chemical_id, wafer_size, reporting_unit, processing_time,
                            //   requested_time, additional_element_ids, additional_notes, analyses: Set}]
  let columns = [];          // analysis ids shown as matrix columns, in the order they were added
  const selected = new Set(); // keys of ticked rows (selection bar acts on these)
  let nextKey = 1;

  const TEXT_FIELDS = ["sample_name", "chemical_id", "wafer_size", "reporting_unit", "processing_time",
                       "requested_time", "additional_element_ids", "additional_notes"];

  // ------------------------------------------------------------ helpers

  const el = (tag, attrs = {}, text = "") => {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    if (text) node.textContent = text;
    return node;
  };
  const option = (value, label) => el("option", { value: String(value) }, label);
  const fillSelect = (select, items, placeholder) => {
    select.replaceChildren();
    if (placeholder !== undefined) select.append(option("", placeholder));
    items.forEach(([value, label]) => select.append(option(value, label)));
  };
  const splitList = (text) => text.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
  const splitLines = (text) => text.split(/\r?\n/).map((s) => s.split("\t")[0].trim()).filter(Boolean);
  const typeInfo = () => ref.request_types.find((rt) => rt.value === requestType);
  const analysisName = (id) => (typeInfo().analyses.find((a) => a.id === id) || {}).name || `#${id}`;
  const timeLimited = (s) => Number(s.processing_time) === ref.processing_time_requiring_requested_time;

  function radioRow(container, name, items, onChange) {
    container.replaceChildren();
    items.forEach(({ value, label }) => {
      const id = `${name}-${value}`;
      const input = el("input", { type: "radio", name, id, value: String(value) });
      input.addEventListener("change", () => onChange(value));
      const lab = el("label", { for: id, class: "choice" });
      lab.append(input, document.createTextNode(` ${label}`));
      container.append(lab);
    });
  }

  // ------------------------------------------------------------ sample state

  function newSample(name = "") {
    const above = samples[samples.length - 1];
    const sample = { key: nextKey++, sample_name: name, analyses: new Set() };
    TEXT_FIELDS.slice(1).forEach((f) => { sample[f] = above ? above[f] : ""; });
    if (above) sample.analyses = new Set(above.analyses);  // new rows copy the row above
    samples.push(sample);
    return sample;
  }

  function addSamples(names) {
    // Fill an empty last row first, so pasting into a fresh form doesn't leave a blank row.
    const last = samples[samples.length - 1];
    let start = 0;
    if (last && !last.sample_name && names.length) { last.sample_name = names[0]; start = 1; }
    names.slice(start).forEach((n) => newSample(n));
    render();
  }

  const targets = () => (selected.size ? samples.filter((s) => selected.has(s.key)) : samples);

  function addColumn(id) {
    if (!columns.includes(id)) columns.push(id);
    targets().forEach((s) => s.analyses.add(id));   // selected rows, or every row when none ticked
    render();
  }

  function removeColumn(id) {
    columns = columns.filter((c) => c !== id);
    samples.forEach((s) => s.analyses.delete(id));
    render();
  }

  // ------------------------------------------------------------ table

  function cell(sample, field, control) {
    control.dataset.f = field;
    control.dataset.key = String(sample.key);
    control.value = sample[field] ?? "";
    control.setAttribute("aria-label", field.replace(/_/g, " "));
    const td = el("td", { "data-f": field });
    td.append(control);
    return td;
  }

  function renderHead() {
    const head = $("sample-head");
    head.replaceChildren();
    const all = el("input", { type: "checkbox", id: "select-all", "aria-label": "Select all samples" });
    all.checked = samples.length > 0 && selected.size === samples.length;
    all.indeterminate = selected.size > 0 && selected.size < samples.length;
    const thAll = el("th", { scope: "col" }); thAll.append(all); head.append(thAll);
    head.append(el("th", { scope: "col" }, "#"), el("th", { scope: "col" }, "Sample ID"));
    if (requestType === 1) head.append(el("th", { scope: "col" }, "Chemical"));
    if (requestType === 3) head.append(el("th", { scope: "col" }, "Wafer size"), el("th", { scope: "col" }, "Units"));
    head.append(el("th", { scope: "col" }, "Processing time"), el("th", { scope: "col" }, "Report by"));
    columns.forEach((id) => {
      const th = el("th", { scope: "col", class: "analysis-col" });
      const count = samples.filter((s) => s.analyses.has(id)).length;
      const box = el("input", { type: "checkbox", "data-col-all": String(id),
                                "aria-label": `${analysisName(id)} for every sample` });
      box.checked = count === samples.length;
      box.indeterminate = count > 0 && count < samples.length;
      const remove = el("button", { type: "button", class: "col-remove", "data-col-remove": String(id),
                                    "aria-label": `Remove ${analysisName(id)}` }, "✕");
      const name = el("span", { class: "col-name" }, analysisName(id));
      th.append(name, el("br"), box, remove);
      head.append(th);
    });
    if (!columns.length) head.append(el("th", { scope: "col", class: "muted" }, "Analyses"));
    head.append(el("th", { scope: "col" }, "Extra elements"), el("th", { scope: "col" }, "Notes"),
                el("th", { scope: "col" }, ""));
  }

  function render() {
    const info = typeInfo();
    renderHead();
    tbody.replaceChildren();
    samples.forEach((s, i) => {
      const tr = el("tr", { "data-key": String(s.key) });
      if (selected.has(s.key)) tr.classList.add("is-selected");
      const pick = el("input", { type: "checkbox", "data-select": String(s.key), "aria-label": `Select sample ${i + 1}` });
      pick.checked = selected.has(s.key);
      const tdPick = el("td"); tdPick.append(pick); tr.append(tdPick);
      tr.append(el("td", { class: "row-no" }, String(i + 1)));
      tr.append(cell(s, "sample_name", el("input", { maxlength: "100", placeholder: "Sample ID" })));
      if (requestType === 1) {
        const sel = el("select"); fillSelect(sel, ref.chemicals.map((c) => [c.id, c.name]), "Choose…");
        tr.append(cell(s, "chemical_id", sel));
      }
      if (requestType === 3) {
        const size = el("select"); fillSelect(size, ref.wafer_sizes.map((w) => [w.value, w.label]), "Choose…");
        const unit = el("select"); fillSelect(unit, ref.reporting_units.map((u) => [u.value, u.label]), "Choose…");
        tr.append(cell(s, "wafer_size", size), cell(s, "reporting_unit", unit));
      }
      const pt = el("select"); fillSelect(pt, info.processing_times.map((p) => [p.value, p.label]), "Choose…");
      tr.append(cell(s, "processing_time", pt));
      const time = el("input", { type: "time" });
      const tdTime = cell(s, "requested_time", time);
      time.disabled = !timeLimited(s);
      tr.append(tdTime);
      columns.forEach((id) => {
        const box = el("input", { type: "checkbox", "data-analysis": String(id), "data-key": String(s.key),
                                  "aria-label": `${analysisName(id)} for sample ${i + 1}` });
        box.checked = s.analyses.has(id);
        const td = el("td", { class: "analysis-cell", "data-f": "analysis_ids" }); td.append(box); tr.append(td);
      });
      if (!columns.length) tr.append(el("td", { class: "muted analysis-cell", "data-f": "analysis_ids" }, "—"));
      tr.append(cell(s, "additional_element_ids", el("input", { placeholder: "e.g. Fe, Li", size: "8" })));
      tr.append(cell(s, "additional_notes", el("input", { maxlength: "2000", placeholder: "optional" })));
      const remove = el("button", { type: "button", class: "btn btn--secondary btn--small", "data-remove": String(s.key),
                                    "aria-label": `Remove sample ${i + 1}` }, "✕");
      remove.disabled = samples.length === 1;
      const tdRemove = el("td"); tdRemove.append(remove); tr.append(tdRemove);
      tbody.append(tr);
    });
    renderSelectionBar();
    syncBrowser();
  }

  function renderSelectionBar() {
    const n = selected.size;
    $("selection-bar").hidden = n === 0;
    $("selection-count").textContent = `${n} sample${n === 1 ? "" : "s"} selected`;
    $("bulk-chemical-wrap").hidden = requestType !== 1;
    $("adder-target").textContent = n
      ? `Adds to the ${n} selected sample${n === 1 ? "" : "s"}`
      : "Adds to every sample";
  }

  function buildAnalysisChoices() {
    const info = typeInfo();
    const list = $("analysis-options");
    list.replaceChildren(...info.analyses.map((a) => el("option", { value: a.name }, a.group)));
    const groups = $("analysis-groups");
    groups.replaceChildren();
    const byGroup = new Map();
    info.analyses.forEach((a) => {
      if (!byGroup.has(a.group)) byGroup.set(a.group, []);
      byGroup.get(a.group).push(a);
    });
    byGroup.forEach((items, group) => {
      const box = el("div", { class: "analysis-group" });
      box.append(el("h4", {}, group || "Other"));
      items.forEach((a) => {
        const id = `browse-${a.id}`;
        const input = el("input", { type: "checkbox", id, value: String(a.id) });
        const lab = el("label", { for: id, class: "check" });
        if (a.description && a.description !== a.name) lab.title = a.description;
        lab.append(input, document.createTextNode(` ${a.name}`));
        box.append(lab);
      });
      groups.append(box);
    });
  }

  function syncBrowser() {
    // In "Browse all", a tick means "this analysis is a column".
    document.querySelectorAll("#analysis-groups input").forEach((box) => {
      box.checked = columns.includes(Number(box.value));
    });
  }

  // ------------------------------------------------------------ events

  $("analysis-search").addEventListener("change", (event) => {
    const name = event.target.value.trim().toLowerCase();
    const match = typeInfo().analyses.find((a) => a.name.toLowerCase() === name);
    if (match) { addColumn(match.id); event.target.value = ""; }
  });
  $("analysis-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); event.target.dispatchEvent(new Event("change")); }
  });
  $("browse-analyses").addEventListener("click", (event) => {
    const browser = $("analysis-browser");
    browser.hidden = !browser.hidden;
    event.target.setAttribute("aria-expanded", String(!browser.hidden));
    event.target.textContent = browser.hidden ? "Browse all" : "Hide list";
  });
  $("analysis-groups").addEventListener("change", (event) => {
    const id = Number(event.target.value);
    if (event.target.checked) addColumn(id); else removeColumn(id);
  });

  $("sample-head").addEventListener("change", (event) => {
    if (event.target.id === "select-all") {
      samples.forEach((s) => (event.target.checked ? selected.add(s.key) : selected.delete(s.key)));
      render();
    } else if (event.target.dataset.colAll) {
      const id = Number(event.target.dataset.colAll);
      samples.forEach((s) => (event.target.checked ? s.analyses.add(id) : s.analyses.delete(id)));
      render();
    }
  });
  $("sample-head").addEventListener("click", (event) => {
    if (event.target.dataset.colRemove) removeColumn(Number(event.target.dataset.colRemove));
  });

  tbody.addEventListener("input", (event) => {
    const { f, key } = event.target.dataset;
    if (!f) return;
    const sample = samples.find((s) => String(s.key) === key);
    sample[f] = event.target.value;
    if (f === "processing_time") {
      if (!timeLimited(sample)) sample.requested_time = "";
      const time = event.target.closest("tr").querySelector('[data-f="requested_time"] input');
      time.disabled = !timeLimited(sample);
      time.value = sample.requested_time;
    }
  });
  tbody.addEventListener("change", (event) => {
    const t = event.target;
    if (t.dataset.select) {
      const key = Number(t.dataset.select);
      if (t.checked) selected.add(key); else selected.delete(key);
      render();
    } else if (t.dataset.analysis) {
      const sample = samples.find((s) => String(s.key) === t.dataset.key);
      const id = Number(t.dataset.analysis);
      if (t.checked) sample.analyses.add(id); else sample.analyses.delete(id);
      renderHead();
    }
  });
  tbody.addEventListener("click", (event) => {
    const key = event.target.dataset.remove;
    if (!key || samples.length === 1) return;
    samples = samples.filter((s) => String(s.key) !== key);
    selected.delete(Number(key));
    render();
  });
  // Paste a column of IDs into a Sample ID cell: one row per line, starting at that row.
  tbody.addEventListener("paste", (event) => {
    if (event.target.dataset.f !== "sample_name") return;
    const names = splitLines(event.clipboardData.getData("text"));
    if (names.length < 2) return;
    event.preventDefault();
    const index = samples.findIndex((s) => String(s.key) === event.target.dataset.key);
    names.forEach((name, i) => {
      if (index + i < samples.length) samples[index + i].sample_name = name;
      else newSample(name);
    });
    render();
  });
  // Ctrl+D (Cmd+D on a Mac): copy this cell's value from the row above, like Excel's fill down.
  tbody.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "d") return;
    const { f, key, analysis } = event.target.dataset;
    if (!f && !analysis) return;
    event.preventDefault();
    const index = samples.findIndex((s) => String(s.key) === key);
    if (index < 1) return;
    const [above, here] = [samples[index - 1], samples[index]];
    if (analysis) {
      const id = Number(analysis);
      if (above.analyses.has(id)) here.analyses.add(id); else here.analyses.delete(id);
    } else {
      here[f] = above[f];
      if (f === "processing_time" && !timeLimited(here)) here.requested_time = "";
    }
    render();
    const again = tbody.querySelector(analysis ? `[data-key="${key}"][data-analysis="${analysis}"]`
                                               : `[data-key="${key}"][data-f="${f}"]`);
    if (again) again.focus();
  });

  // selection bar
  $("bulk-processing-time").addEventListener("change", (event) => {
    if (!event.target.value) return;
    samples.filter((s) => selected.has(s.key)).forEach((s) => {
      s.processing_time = event.target.value;
      if (!timeLimited(s)) s.requested_time = "";
    });
    event.target.value = "";
    render();
  });
  $("bulk-chemical").addEventListener("change", (event) => {
    if (!event.target.value) return;
    samples.filter((s) => selected.has(s.key)).forEach((s) => { s.chemical_id = event.target.value; });
    event.target.value = "";
    render();
  });
  $("bulk-duplicate").addEventListener("click", () => {
    const copies = samples.filter((s) => selected.has(s.key)).map((s) => ({
      ...s, key: nextKey++, sample_name: s.sample_name ? `${s.sample_name} (copy)` : "", analyses: new Set(s.analyses),
    }));
    samples.push(...copies);
    selected.clear();
    copies.forEach((c) => selected.add(c.key));
    render();
  });
  $("bulk-remove").addEventListener("click", () => {
    const remaining = samples.filter((s) => !selected.has(s.key));
    if (!remaining.length) { showErrors([{ text: "A request needs at least one sample." }]); return; }
    samples = remaining;
    selected.clear();
    render();
  });
  $("bulk-clear").addEventListener("click", () => { selected.clear(); render(); });

  $("add-sample").addEventListener("click", () => {
    newSample();
    render();
    tbody.lastElementChild.querySelector('[data-f="sample_name"] input, input[data-f="sample_name"]').focus();
  });
  $("add-pasted").addEventListener("click", () => {
    const names = splitLines($("paste-ids").value);
    if (!names.length) return;
    addSamples(names);
    $("paste-ids").value = "";
  });

  function setRequestType(value) {
    const changed = requestType !== null && requestType !== value;
    requestType = value;
    $("samples-section").hidden = false;
    $("submit-button").disabled = false;
    const info = typeInfo();
    const allowedTimes = new Set(info.processing_times.map((p) => String(p.value)));
    const allowedAnalyses = new Set(info.analyses.map((a) => a.id));
    columns = columns.filter((id) => allowedAnalyses.has(id));
    samples.forEach((s) => {   // keep what still applies to the new type
      if (!allowedTimes.has(String(s.processing_time))) s.processing_time = "";
      s.analyses = new Set([...s.analyses].filter((id) => allowedAnalyses.has(id)));
      if (changed) { s.chemical_id = ""; s.wafer_size = ""; s.reporting_unit = ""; }
    });
    if (!samples.length) newSample();
    fillSelect($("bulk-processing-time"), info.processing_times.map((p) => [p.value, p.label]), "Set…");
    fillSelect($("bulk-chemical"), ref.chemicals.map((c) => [c.id, c.name]), "Set…");
    buildAnalysisChoices();
    render();
  }

  // ------------------------------------------------------------ customer, payment, locations

  function setLocations(locations) {
    $("location-field").classList.toggle("hidden", !locations.length);
    fillSelect($("location"), locations.map((l) => [l, l]), locations.length ? "Choose a site…" : "");
  }

  function setPayment(value) {
    const po = value === 1;
    $("po-field").classList.toggle("hidden", !po);
    $("card-hint").classList.toggle("hidden", po);
    if (!po) $("po_number").value = "";
  }

  async function prefillFromLastRequest() {
    // Customers: start from their most recent request's contact and distribution lists.
    const response = await fetch("/api/submissions?per_page=1", { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const last = (await response.json()).items[0];
    if (!last) return;
    ["customer_contact", "customer_phone"].forEach((f) => { $(f).value = last[f]; });
    ["results_to", "results_cc", "invoice_to", "invoice_cc"].forEach((f) => { $(f).value = last[f].join(", "); });
    const pay = $(`payment_method-${last.payment_method}`);
    if (pay) { pay.checked = true; setPayment(last.payment_method); }
    $("po_number").value = last.po_number;
    if (last.location) $("location").value = last.location;
  }

  // ------------------------------------------------------------ submit

  function collect() {
    const problems = [];
    const intOrNull = (v) => (v === "" || v === undefined || v === null ? null : Number(v));
    const symbols = new Map(ref.elements.map((e) => [e.symbol.toLowerCase(), e.id]));
    const body = {
      request_type: requestType,
      location: $("location").value,
      expected_arrival_date: $("expected_arrival_date").value || null,
      customer_contact: $("customer_contact").value.trim(),
      customer_phone: $("customer_phone").value.trim(),
      payment_method: intOrNull((document.querySelector('input[name="payment_method"]:checked') || {}).value),
      po_number: $("po_number").value.trim(),
      results_to: splitList($("results_to").value),
      results_cc: splitList($("results_cc").value),
      invoice_to: splitList($("invoice_to").value),
      invoice_cc: splitList($("invoice_cc").value),
      samples: samples.map((s, i) => {
        const elementIds = splitList(s.additional_element_ids || "").map((sym) => {
          const id = symbols.get(sym.toLowerCase());
          if (id === undefined) problems.push({ text: `Sample ${i + 1}: "${sym}" is not an element symbol.`,
                                                sample: i, field: "additional_element_ids" });
          return id;
        });
        const sample = {
          sample_name: (s.sample_name || "").trim(),
          processing_time: intOrNull(s.processing_time),
          requested_time: timeLimited(s) ? s.requested_time || null : null,
          additional_notes: (s.additional_notes || "").trim(),
          analysis_ids: [...s.analyses],
          additional_element_ids: elementIds.filter((id) => id !== undefined),
        };
        if (requestType === 1) sample.chemical_id = intOrNull(s.chemical_id);
        if (requestType === 3) {
          sample.wafer_size = intOrNull(s.wafer_size);
          sample.reporting_unit = intOrNull(s.reporting_unit);
        }
        return sample;
      }),
    };
    if (isStaff) body.customer_id = intOrNull($("customer_id").value);
    return { body, problems };
  }

  const FIELD_LABELS = {
    customer_id: "Customer", request_type: "Request type", location: "Site", customer_contact: "Contact name",
    customer_phone: "Phone", payment_method: "Payment", po_number: "PO number", results_to: "Results to",
    results_cc: "Results cc", invoice_to: "Invoice to", invoice_cc: "Invoice cc",
    expected_arrival_date: "Expected arrival", sample_name: "Sample ID", chemical_id: "Chemical",
    processing_time: "Processing time", requested_time: "Report-by time", analysis_ids: "Analyses",
    additional_element_ids: "Extra elements", wafer_size: "Wafer size", reporting_unit: "Units",
    additional_notes: "Notes", samples: "Samples",
  };

  // Plain-language versions of the validator's most common messages.
  function friendly(msg) {
    const m = msg.replace(/^Value error, /, "");
    if (/^Field required$/.test(m) || /valid integer/.test(m) || /at least 1 character/.test(m)) return "is required";
    if (/at least 1 item/.test(m)) return "needs at least one entry";
    if (/valid email address/.test(m)) return "contains an address that isn't a valid email";
    return m;
  }

  function describe(loc) {
    const path = loc[0] === "body" ? loc.slice(1) : loc;
    if (path[0] === "samples" && Number.isInteger(path[1])) {
      const field = path[2] !== undefined ? ` – ${FIELD_LABELS[path[2]] || path[2]}` : "";
      return { text: `Sample ${path[1] + 1}${field}`, sample: path[1], field: path[2] };
    }
    return { text: path.length ? FIELD_LABELS[path[0]] || path[0] : "Request", field: path[0] };
  }

  function showErrors(messages) {
    form.querySelectorAll(".has-error").forEach((n) => n.classList.remove("has-error"));
    errorBox.replaceChildren(el("strong", {}, "Please fix the following:"));
    const list = el("ul");
    messages.forEach(({ text, sample, field }) => {
      list.append(el("li", {}, text));
      let target = null;
      if (sample !== undefined) {
        const row = tbody.children[sample];
        target = row && (field ? row.querySelector(`td[data-f="${field}"]`) : row);
      } else if (field) {
        target = form.querySelector(`[data-path="${field}"]`);
      }
      if (target) (target.closest(".field") || target).classList.add("has-error");
    });
    errorBox.append(list);
    errorBox.classList.remove("hidden");
    errorBox.focus();
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const { body, problems } = collect();
    if (problems.length) { showErrors(problems); return; }
    const button = $("submit-button");
    button.disabled = true;
    try {
      const response = await fetch("/api/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 201) {
        window.location.assign(`/requests/${encodeURIComponent(data.tr_number)}`);
        return;
      }
      if (Array.isArray(data.detail)) {
        showErrors(data.detail.map((d) => {
          const where = describe(d.loc || []);
          return { ...where, text: `${where.text}: ${friendly(d.msg)}` };
        }));
      } else {
        showErrors([{ text: data.detail || `The request could not be submitted (HTTP ${response.status}).` }]);
      }
    } catch (err) {
      showErrors([{ text: "Could not reach the server. Check your connection and try again." }]);
    } finally {
      button.disabled = false;
    }
  });

  // ------------------------------------------------------------ start

  (async () => {
    try {
      const response = await fetch("/api/reference", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      ref = await response.json();
    } catch (err) {
      showErrors([{ text: "The lab's analysis list could not be loaded. Please reload the page." }]);
      return;
    }
    $("form-loading").remove();
    radioRow($("request-types"), "request_type", ref.request_types, setRequestType);
    radioRow($("payment-methods"), "payment_method", ref.payment_methods, setPayment);
    $("payment_method-1").checked = true;
    setPayment(1);
    const today = new Date();
    $("expected_arrival_date").min = new Date(today.getTime() - today.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 10);
    if (isStaff) {
      const select = $("customer_id");
      ref.customers.forEach((c) => select.append(option(c.id, c.name)));
      select.addEventListener("change", () => {
        const customer = ref.customers.find((c) => String(c.id) === select.value);
        setLocations(customer ? customer.locations : []);
      });
      setLocations([]);
    } else {
      setLocations(ref.locations);
      await prefillFromLastRequest();
    }
  })();
})();
