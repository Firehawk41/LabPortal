// New testing request form. Choices come from GET /api/reference (the SLIM reference cache);
// the form posts JSON to POST /api/submissions and shows the server's field errors.
// No inline scripts (CSP): this file is loaded with <script src> and wires everything up.
(() => {
  "use strict";

  const form = document.getElementById("request-form");
  if (!form) return;
  const isStaff = form.dataset.staff === "1";
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const $ = (id) => document.getElementById(id);
  const samplesBox = $("samples");
  const template = $("sample-template");
  const errorBox = $("form-error");

  let ref = null;           // /api/reference payload
  let requestType = null;   // RequestType value (1 Chemical, 2 Water, 3 Wafer)
  let sampleCounter = 0;    // monotonic, for unique input names

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
    if (placeholder) select.append(option("", placeholder));
    items.forEach(([value, label]) => select.append(option(value, label)));
  };
  const splitList = (text) => text.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
  const typeInfo = () => ref.request_types.find((rt) => rt.value === requestType);

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

  // ------------------------------------------------------------ samples

  function addSample(copyFrom) {
    sampleCounter += 1;
    const card = template.content.firstElementChild.cloneNode(true);
    card.dataset.key = String(sampleCounter);
    card.querySelectorAll("[data-f]").forEach((field) => { field.name = `${field.dataset.f}-${sampleCounter}`; });
    samplesBox.append(card);
    renderSampleForType(card);
    if (copyFrom) copySample(copyFrom, card);
    renumber();
    return card;
  }

  function copySample(from, to) {
    ["chemical_id", "wafer_size", "reporting_unit", "processing_time", "requested_time",
     "additional_element_ids", "additional_notes"].forEach((f) => {
      to.querySelector(`[data-f="${f}"]`).value = from.querySelector(`[data-f="${f}"]`).value;
    });
    const checked = new Set([...from.querySelectorAll(".analyses input:checked")].map((c) => c.value));
    to.querySelectorAll(".analyses input").forEach((c) => { c.checked = checked.has(c.value); });
    toggleRequestedTime(to);
  }

  function renumber() {
    [...samplesBox.children].forEach((card, i) => {
      card.querySelector(".sample-title").textContent = `Sample ${i + 1}`;
      card.querySelector('[data-action="remove"]').disabled = samplesBox.children.length === 1;
    });
  }

  function renderSampleForType(card) {
    const info = typeInfo();
    card.querySelectorAll("[data-only]").forEach((node) => {
      node.classList.toggle("hidden", Number(node.dataset.only) !== requestType);
    });
    fillSelect(card.querySelector('[data-f="chemical_id"]'), ref.chemicals.map((c) => [c.id, c.name]), "Choose…");
    fillSelect(card.querySelector('[data-f="wafer_size"]'), ref.wafer_sizes.map((w) => [w.value, w.label]), "Choose…");
    fillSelect(card.querySelector('[data-f="reporting_unit"]'), ref.reporting_units.map((u) => [u.value, u.label]), "Choose…");
    const pt = card.querySelector('[data-f="processing_time"]');
    fillSelect(pt, info.processing_times.map((p) => [p.value, p.label]), "Choose…");
    pt.onchange = () => toggleRequestedTime(card);
    toggleRequestedTime(card);

    const groups = card.querySelector(".analysis-groups");
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
        const id = `a-${card.dataset.key}-${a.id}`;
        const input = el("input", { type: "checkbox", id, value: String(a.id) });
        const lab = el("label", { for: id, class: "check" });
        if (a.description && a.description !== a.name) lab.title = a.description;
        lab.append(input, document.createTextNode(` ${a.name}`));
        box.append(lab);
      });
      groups.append(box);
    });
  }

  function toggleRequestedTime(card) {
    const value = Number(card.querySelector('[data-f="processing_time"]').value);
    const wrap = card.querySelector('[data-f-wrap="requested_time"]');
    const show = value === ref.processing_time_requiring_requested_time;
    wrap.classList.toggle("hidden", !show);
    if (!show) card.querySelector('[data-f="requested_time"]').value = "";
  }

  samplesBox.addEventListener("click", (event) => {
    const action = event.target.dataset.action;
    const card = event.target.closest(".sample-card");
    if (action === "remove" && samplesBox.children.length > 1) { card.remove(); renumber(); }
    if (action === "copy") addSample(card).querySelector('[data-f="sample_name"]').focus();
  });
  $("add-sample").addEventListener("click", () => addSample().querySelector('[data-f="sample_name"]').focus());

  function setRequestType(value) {
    requestType = value;
    $("samples-section").hidden = false;
    $("submit-button").disabled = false;
    if (!samplesBox.children.length) addSample();
    else [...samplesBox.children].forEach(renderSampleForType);
  }

  // ------------------------------------------------------------ customer, payment, locations

  function setLocations(locations) {
    const field = $("location-field");
    field.classList.toggle("hidden", !locations.length);
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
    const pay = document.querySelector(`input[name="payment_method"][value="${last.payment_method}"]`);
    if (pay) { pay.checked = true; setPayment(last.payment_method); }
    $("po_number").value = last.po_number;
    if (last.location) $("location").value = last.location;
  }

  // ------------------------------------------------------------ submit

  function collect() {
    const problems = [];
    const intOrNull = (v) => (v === "" ? null : Number(v));
    const symbols = new Map(ref.elements.map((e) => [e.symbol.toLowerCase(), e.id]));
    const samples = [...samplesBox.children].map((card, i) => {
      const f = (name) => card.querySelector(`[data-f="${name}"]`).value.trim();
      const elementIds = splitList(f("additional_element_ids")).map((sym) => {
        const id = symbols.get(sym.toLowerCase());
        if (id === undefined) problems.push(`Sample ${i + 1}: "${sym}" is not an element symbol.`);
        return id;
      });
      const sample = {
        sample_name: f("sample_name"),
        processing_time: intOrNull(f("processing_time")),
        requested_time: f("requested_time") || null,
        additional_notes: f("additional_notes"),
        analysis_ids: [...card.querySelectorAll(".analyses input:checked")].map((c) => Number(c.value)),
        additional_element_ids: elementIds.filter((id) => id !== undefined),
      };
      if (requestType === 1) sample.chemical_id = intOrNull(f("chemical_id"));
      if (requestType === 3) {
        sample.wafer_size = intOrNull(f("wafer_size"));
        sample.reporting_unit = intOrNull(f("reporting_unit"));
      }
      return sample;
    });
    const payment = document.querySelector('input[name="payment_method"]:checked');
    const body = {
      request_type: requestType,
      location: $("location").value,
      expected_arrival_date: $("expected_arrival_date").value || null,
      customer_contact: $("customer_contact").value.trim(),
      customer_phone: $("customer_phone").value.trim(),
      payment_method: payment ? Number(payment.value) : null,
      po_number: $("po_number").value.trim(),
      results_to: splitList($("results_to").value),
      results_cc: splitList($("results_cc").value),
      invoice_to: splitList($("invoice_to").value),
      invoice_cc: splitList($("invoice_cc").value),
      samples,
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
    additional_element_ids: "Additional elements", wafer_size: "Wafer size", reporting_unit: "Report results in",
    additional_notes: "Notes", samples: "Samples",
  };

  // Plain-language versions of the validator's most common messages.
  function friendly(msg) {
    const m = msg.replace(/^Value error, /, "");
    if (/^Field required$/.test(m) || /valid integer/.test(m) || /^Input should be .*(not|got) None/i.test(m)) return "is required";
    if (/at least 1 item/.test(m)) return "needs at least one entry";
    if (/valid email address/.test(m)) return "contains an address that isn't a valid email";
    if (/at least 1 character/.test(m)) return "is required";
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
        const card = samplesBox.children[sample];
        target = card && (field ? card.querySelector(`[data-f="${field}"]`) : card);
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
    if (problems.length) { showErrors(problems.map((text) => ({ text }))); return; }
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
