let sampleCounter = 0;
let pendingFormData = null;

function showFormError(message) {
  const el = document.getElementById("form-error");
  if (!el) return;
  if (!message) {
    el.style.display = "none";
    el.textContent = "";
    return;
  }
  el.textContent = message;
  el.style.display = "block";
  el.scrollIntoView({ behavior: "smooth", block: "center" });
}

// Adds a new row of sample fields to the form.
async function addSample() {
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

  row.appendChild(sampleId);
  row.appendChild(matrix);
  row.appendChild(sampleTypeSelect);
  row.appendChild(analysisSelect);
  row.appendChild(processingTime);

  // Update analysis dropdown when sample type changes
  sampleTypeSelect.addEventListener("change", async function () {
    const newAnalysisSelect = await createAnalysisDropdown(index, this.value);
    $(analysisSelect).select2("destroy");
    analysisSelect.replaceWith(newAnalysisSelect);
    $(newAnalysisSelect).select2({
      placeholder: "Select analyses",
      width: "100%",
      allowClear: true
    });
    analysisSelect = newAnalysisSelect;
  });

  sampleContainer.appendChild(row);

  $(analysisSelect).select2({
    placeholder: "Select analyses",
    width: "100%",
    allowClear: true
  });
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

// Create the first sample row on page load
document.addEventListener("DOMContentLoaded", async function () {
  await addSample();
});

// Initialise Tagify on email inputs
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".email-tag-input").forEach(input => {
    new Tagify(input, {
      pattern: /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/,
      duplicates: false,
      dropdown: { enabled: 0 }
    });
  });
});

// Payment method visibility toggle
const poInfo = document.getElementById("po-info");
const ccInfo = document.getElementById("cc-info");

document.querySelectorAll('input[name="payment_method"]').forEach(radio => {
  radio.addEventListener("change", function () {
    if (this.value === "po") {
      poInfo.style.display = "block";
      ccInfo.style.display = "none";
      document.getElementById("po-number").required = true;
      document.getElementById("cc-number").required = false;
      document.getElementById("cc-number").value = "";
    } else {
      poInfo.style.display = "none";
      ccInfo.style.display = "block";
      document.getElementById("po-number").required = false;
      document.getElementById("cc-number").required = true;
      document.getElementById("po-number").value = "";
    }
  });
});

// ESC key closes the modal
document.addEventListener("keydown", function (e) {
  if (e.key === "Escape") {
    const modal = document.getElementById("confirmationModal");
    if (modal.style.display !== "none") {
      modal.style.display = "none";
      pendingFormData = null;
    }
  }
});

// Clicking the backdrop also closes the modal
document.getElementById("confirmationModal").addEventListener("click", function (e) {
  if (e.target === this) {
    this.style.display = "none";
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

  const analyses = [];
  let i = 0;
  while (formData.has(`analysis[${i}][]`)) {
    analyses.push(formData.getAll(`analysis[${i}][]`));
    i++;
  }

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
    cc_number:        formData.get("cc-number"),
    invoice_list:     formData.get("invoice-list"),
    invoice_cc_list:  formData.get("invoice-cc-list"),
    samples:          samples
  };

  document.getElementById("jsonSummary").textContent = JSON.stringify(pendingFormData, null, 2);
  document.getElementById("confirmationModal").style.display = "block";
});

// Confirm button — submit to server with loading state
document.getElementById("confirmBtn").onclick = async function () {
  const confirmBtn = document.getElementById("confirmBtn");
  const submitBtn  = document.getElementById("submitBtn");

  document.getElementById("confirmationModal").style.display = "none";
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
  document.getElementById("confirmationModal").style.display = "none";
  pendingFormData = null;
};
