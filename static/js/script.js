let sampleCounter = 0;
let pendingFormData = null;

function showFormError(message) {
  const el = document.getElementById("form-error");
  if (!el) return;
  if (!message) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  el.textContent = message;
  el.classList.remove("hidden");
  el.scrollIntoView({ behavior: "smooth", block: "center" });
}

// Adds a new row of sample fields to the form.
async function addSample(initialSampleType) {
  const sampleContainer = document.getElementById("samples");
  const index = sampleCounter++;

  const row = document.createElement("div");
  row.className = "sample-row";

  // Sample ID input
  const sampleId = document.createElement("input");
  sampleId.name = "sample_id[]";
  sampleId.placeholder = "Sample ID";
  sampleId.required = true;

  // Chemical matrix input
  const matrix = document.createElement("input");
  matrix.name = "chemical_matrix[]";
  matrix.placeholder = "Chemical Matrix";
  matrix.required = true;

  // Sample type dropdown
  const sampleTypeSelect = document.createElement("select");
  sampleTypeSelect.name = "sample_type[]";
  sampleTypeSelect.className = "sample-type-select";
  const types = ["chemical", "water", "wafer"];
  types.forEach(type => {
    const option = document.createElement("option");
    option.value = type;
    option.textContent = type.charAt(0).toUpperCase() + type.slice(1);
    sampleTypeSelect.appendChild(option);
  });
  if (initialSampleType && types.includes(initialSampleType)) {
    sampleTypeSelect.value = initialSampleType;
  }

  // Processing time dropdown
  const processingTime = document.createElement("select");
  processingTime.name = "processing_time[]";
  processingTime.required = true;
  ["Standard", "Next Day", "Rush"].forEach(t => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    processingTime.appendChild(opt);
  });

  // Analysis dropdown (async, filtered by sample type)
  let analysisSelect = await createAnalysisDropdown(index, sampleTypeSelect.value);

  // Copy button — duplicates this row into a new row
  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "btn btn--secondary btn--icon";
  copyBtn.textContent = "Copy";
  copyBtn.title = "Copy this sample";

  // Remove button — deletes this row
  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "btn btn--secondary btn--icon";
  removeBtn.textContent = "Remove";
  removeBtn.title = "Remove this sample";

  row.appendChild(sampleId);
  row.appendChild(matrix);
  row.appendChild(sampleTypeSelect);
  row.appendChild(analysisSelect);
  row.appendChild(processingTime);
  row.appendChild(copyBtn);
  row.appendChild(removeBtn);

  // Update analysis dropdown when sample type changes
  sampleTypeSelect.addEventListener("change", async function () {
    const newAnalysisSelect = await createAnalysisDropdown(index, this.value);
    if (typeof $ !== "undefined") $(analysisSelect).select2("destroy");
    analysisSelect.replaceWith(newAnalysisSelect);
    if (typeof $ !== "undefined") {
      $(newAnalysisSelect).select2({ placeholder: "Select analyses", width: "100%", allowClear: true });
    }
    analysisSelect = newAnalysisSelect;
  });

  removeBtn.addEventListener("click", function () {
    if (typeof $ !== "undefined" && analysisSelect) {
      $(analysisSelect).select2("destroy");
    }
    row.remove();
  });

  copyBtn.addEventListener("click", async function () {
    const newRow = await addSample(sampleTypeSelect.value);

    const newSampleId = newRow.querySelector('input[name="sample_id[]"]');
    if (newSampleId) newSampleId.value = sampleId.value;

    const newMatrix = newRow.querySelector('input[name="chemical_matrix[]"]');
    if (newMatrix) newMatrix.value = matrix.value;

    const newProcessingTime = newRow.querySelector('select[name="processing_time[]"]');
    if (newProcessingTime) newProcessingTime.value = processingTime.value;

    const selectedValues = Array.from(analysisSelect.querySelectorAll("option:checked")).map(opt => opt.value);
    const newAnalysisSelect = newRow.querySelector(".analysis-select");
    if (newAnalysisSelect && selectedValues.length > 0) {
      Array.from(newAnalysisSelect.options).forEach(opt => {
        opt.selected = selectedValues.includes(opt.value);
      });
      if (typeof $ !== "undefined") {
        $(newAnalysisSelect).trigger("change");
      }
    }
  });

  sampleContainer.appendChild(row);

  if (typeof $ !== "undefined") {
    $(analysisSelect).select2({ placeholder: "Select analyses", width: "100%", allowClear: true });
  }

  return row;
}

function filterAnalysesByType(data, sampleType) {
  return data
    .map(group => {
      const filteredOptions = group.options.filter(opt =>
        opt.sample_types.includes(sampleType)
      );
      if (filteredOptions.length > 0) {
        return { group: group.group, options: filteredOptions };
      }
      return null;
    })
    .filter(Boolean);
}

async function createAnalysisDropdown(index, sampleType) {
  try {
    const response = await fetch("/static/data/analyses.json");
    if (!response.ok) throw new Error("Failed to load analyses");
    const allData = await response.json();

    const filteredGroups = filterAnalysesByType(allData, sampleType);

    const select = document.createElement("select");
    select.name = `analysis[${index}][]`;
    select.className = "analysis-select";
    select.multiple = true;

    filteredGroups.forEach(group => {
      const optgroup = document.createElement("optgroup");
      optgroup.label = group.group;
      group.options.forEach(opt => {
        const option = document.createElement("option");
        option.value = opt.id;
        option.textContent = opt.label;
        if (opt.long_description) option.title = opt.long_description;
        optgroup.appendChild(option);
      });
      select.appendChild(optgroup);
    });

    return select;
  } catch (err) {
    console.error("Error loading analyses:", err);
    const errSelect = document.createElement("select");
    errSelect.disabled = true;
    errSelect.className = "analysis-select";
    errSelect.innerHTML = "<option>Error loading analyses — reload page</option>";
    return errSelect;
  }
}

// Create the first sample row on page load and wire up the add button
document.addEventListener("DOMContentLoaded", async function () {
  document.getElementById("addSampleBtn").addEventListener("click", () => addSample());
  await addSample();
});

// Initialise Tagify on email inputs, pre-filling from PROFILE if available
document.addEventListener("DOMContentLoaded", function () {
  if (typeof Tagify === "undefined") return;

  const emailFieldMap = {
    "results-list":     "results_list",
    "results-cc-list":  "results_cc_list",
    "invoice-list":     "invoice_list",
    "invoice-cc-list":  "invoice_cc_list",
  };

  Object.entries(emailFieldMap).forEach(([inputId, profileKey]) => {
    const input = document.getElementById(inputId);
    if (!input) return;
    const profileEmails = (typeof PROFILE !== "undefined" && PROFILE[profileKey]) || [];
    new Tagify(input, {
      pattern: /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/,
      duplicates: false,
      dropdown: { enabled: 0 },
      ...(profileEmails.length ? { value: profileEmails.map(e => ({ value: e })) } : {})
    });
  });
});

// Pre-fill plain Customer Information inputs from saved profile
document.addEventListener("DOMContentLoaded", function () {
  if (typeof PROFILE === "undefined") return;

  const fieldMap = {
    "customer-name":    "customer_name",
    "street-address":   "street_address",
    "city":             "city",
    "state":            "state",
    "country":          "country",
    "customer-contact": "customer_contact",
    "customer-phone":   "customer_phone",
  };

  Object.entries(fieldMap).forEach(([inputId, profileKey]) => {
    const el = document.getElementById(inputId);
    if (el && PROFILE[profileKey]) el.value = PROFILE[profileKey];
  });

  // Set payment method radio (default is "po", only need to change if "cc")
  if (PROFILE.payment_method) {
    const radio = document.querySelector(`input[name="payment_method"][value="${PROFILE.payment_method}"]`);
    if (radio && !radio.checked) {
      radio.checked = true;
      radio.dispatchEvent(new Event("change"));
    }
  }

  // Pre-fill po-number after the change event (which clears it)
  if (PROFILE.po_number) {
    const poInput = document.getElementById("po-number");
    if (poInput) poInput.value = PROFILE.po_number;
  }
});

// Payment method visibility toggle
const poInfo = document.getElementById("po-info");
const ccInfo = document.getElementById("cc-info");

document.querySelectorAll('input[name="payment_method"]').forEach(radio => {
  radio.addEventListener("change", function () {
    if (this.value === "po") {
      poInfo.classList.remove("hidden");
      ccInfo.classList.add("hidden");
      document.getElementById("po-number").required = true;
      document.getElementById("po-number").value = "";
    } else {
      poInfo.classList.add("hidden");
      ccInfo.classList.remove("hidden");
      document.getElementById("po-number").required = false;
      document.getElementById("po-number").value = "";
    }
  });
});

// ESC key closes the modal
document.addEventListener("keydown", function (e) {
  if (e.key === "Escape") {
    const modal = document.getElementById("confirmationModal");
    if (!modal.classList.contains("hidden")) {
      modal.classList.add("hidden");
      pendingFormData = null;
    }
  }
});

// Clicking the backdrop also closes the modal
document.getElementById("confirmationModal").addEventListener("click", function (e) {
  if (e.target === this) {
    this.classList.add("hidden");
    pendingFormData = null;
  }
});

// Intercept form submission — validate, build JSON, show confirmation modal
document.getElementById("sampleForm").addEventListener("submit", function (e) {
  e.preventDefault();
  showFormError("");

  const formData = new FormData(e.target);

  const sampleIds = formData.getAll("sample_id[]");
  if (sampleIds.length === 0) {
    showFormError("Please add at least one sample before submitting.");
    return;
  }

  const matrices  = formData.getAll("chemical_matrix[]");
  const types     = formData.getAll("sample_type[]");
  const times     = formData.getAll("processing_time[]");

  const sampleRows = document.querySelectorAll("#samples .sample-row");
  const analyses = Array.from(sampleRows).map(row => {
    const select = row.querySelector(".analysis-select");
    return select ? Array.from(select.selectedOptions).map(opt => opt.value) : [];
  });

  const samples = sampleIds.map((id, idx) => ({
    sample_id: id,
    chemical_matrix: matrices[idx],
    sample_type: types[idx],
    processing_time: times[idx],
    analyses: analyses[idx] || []
  }));

  pendingFormData = {
    customer_name:    formData.get("customer-name"),
    street_address:   formData.get("street-address"),
    city:             formData.get("city"),
    state:            formData.get("state"),
    country:          formData.get("country"),
    customer_contact: formData.get("customer-contact"),
    customer_phone:   formData.get("customer-phone"),
    results_list:     formData.get("results-list"),
    results_cc_list:  formData.get("results-cc-list"),
    payment_method:   formData.get("payment_method"),
    po_number:        formData.get("po-number"),
    invoice_list:     formData.get("invoice-list"),
    invoice_cc_list:  formData.get("invoice-cc-list"),
    samples:          samples
  };

  document.getElementById("jsonSummary").textContent = JSON.stringify(pendingFormData, null, 2);
  document.getElementById("confirmationModal").classList.remove("hidden");
});

// Confirm button — submit to server with loading state
document.getElementById("confirmBtn").onclick = async function () {
  const confirmBtn = document.getElementById("confirmBtn");
  const submitBtn  = document.getElementById("submitBtn");

  document.getElementById("confirmationModal").classList.add("hidden");
  confirmBtn.disabled = true;
  submitBtn.disabled  = true;
  submitBtn.textContent = "Submitting…";

  try {
    const res = await fetch("/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pendingFormData)
    });

    const result = await res.json();

    if (res.ok) {
      showFormError("");
      alert(`Submission received!\nYour submission ID is: ${result.submission_id}`);
      location.reload();
    } else {
      const messages = result.errors
        ? result.errors.join("\n")
        : (result.error || "Unknown server error.");
      showFormError("Submission failed:\n" + messages);
    }
  } catch (networkErr) {
    showFormError("Network error — check your connection and try again.");
  } finally {
    confirmBtn.disabled = false;
    submitBtn.disabled  = false;
    submitBtn.textContent = "Submit";
  }

  pendingFormData = null;
};

// Cancel button hides modal
document.getElementById("cancelBtn").onclick = function () {
  document.getElementById("confirmationModal").classList.add("hidden");
  pendingFormData = null;
};
