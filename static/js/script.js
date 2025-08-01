// Adds a new row of sample fields to the form.
// Each row includes sample ID, matrix, sample type selector, analysis selector, and processing time.
// The analysis selector updates dynamically based on the chosen sample type.
async function addSample() {
  // Get the container for sample rows
  const sampleContainer = document.getElementById("samples");
  const index = sampleContainer.children.length;

  // Create a new row for sample input fields
  const row = document.createElement("div");
  row.className = "sample-row";

  // Sample ID input
  const sampleId = document.createElement("input");
  sampleId.name = "sample_id[]";
  sampleId.placeholder = "Sample ID";
  sampleId.required = true;
  sampleId.value = "TEST_SAMPLE_ID";

  // Chemical matrix input
  const matrix = document.createElement("input");
  matrix.name = "chemical_matrix[]";
  matrix.placeholder = "Chemical Matrix";
  matrix.required = true;
  matrix.value = "TEST_MATRIX";

  // Sample type dropdown (chemical, water, wafer)
  const sampleTypeSelect = document.createElement("select");
  sampleTypeSelect.name="sample_type[]";
  sampleTypeSelect.className = "sample-type-select";
  const types = ["chemical", "water", "wafer"];
  types.forEach(type => {
    const option = document.createElement("option");
    option.value = type;
    option.textContent = type.charAt(0).toUpperCase() + type.slice(1); // Capitalize
    sampleTypeSelect.appendChild(option);
  });

  // Processing time input
  const processingTime = document.createElement("input");
  processingTime.name = "processing_time[]";
  processingTime.placeholder = "Processing Time";
  processingTime.required = true;

  // Create analysis dropdown based on sample type
  let analysisSelect = await createAnalysisDropdown(index, sampleTypeSelect.value);

  // Append all inputs to the row
  row.appendChild(sampleId);
  row.appendChild(matrix);
  row.appendChild(sampleTypeSelect);
  row.appendChild(analysisSelect);
  row.appendChild(processingTime);

  // When sample type changes, update the analysis dropdown accordingly
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



  // Add the row to the form
  sampleContainer.appendChild(row);

  // Initialize Select2 for the analysis dropdown
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
        return {
          group: group.group,
          options: filteredOptions
        };
      }
      return null;
    })
    .filter(Boolean); // remove nulls
}


async function createAnalysisDropdown(index, sampleType) {
  try {
    const response = await fetch("/static/data/analyses.json");
    if (!response.ok) throw new Error("Failed to load analyses");
    const allData = await response.json();

    // Filter based on sample type
    const filteredGroups = filterAnalysesByType(allData, sampleType);

    // Create select element
    const select = document.createElement("select");
    select.name = `analysis[${index}][]`;
    select.className = "analysis-select";
    select.multiple = true;

    // Populate with optgroups and options
    filteredGroups.forEach(group => {
      const optgroup = document.createElement("optgroup");
      optgroup.label = group.group;

      group.options.forEach(opt => {
        const option = document.createElement("option");
        option.value = opt.id;
        option.textContent = opt.label;
        option.title = opt.long_description;
        optgroup.appendChild(option);
      });

      select.appendChild(optgroup);
    });

    return select;
  } catch (err) {
    alert("Error loading analyses: " + err.message);
  }
}



// Creates first sample row when the page is first loaded
document.addEventListener("DOMContentLoaded", async function () {
  await addSample();  // create the first sample row
});

// Listener for Tagify functionality
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll('.email-tag-input').forEach(input => {
    new Tagify(input, {
      pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,  // Basic email regex
      duplicates: false,
      dropdown: {
        enabled: 0 // disable suggestions
      }
    });
  });
});

const poInfo = document.getElementById("po-info");
const ccInfo = document.getElementById("cc-info");

document.querySelectorAll('input[name="payment_method"]').forEach(radio => {
  radio.addEventListener("change", function () {
    if (this.value === "po") {
      poInfo.style.display = "block";
      ccInfo.style.display = "none";
      document.getElementById("po-number").required = true;
      document.getElementById("cc-number").required = false;
    } else {
      poInfo.style.display = "none";
      ccInfo.style.display = "block";
      document.getElementById("po-number").required = false;
      document.getElementById("cc-number").required = true;
    }
  });
});

// Store form data for confirmation
let pendingFormData = null;

// Intercept form submission
document.getElementById("sampleForm").addEventListener("submit", function(e) {
  e.preventDefault();
  console.info("Submit handler triggered");
  // Collect form data
  const formData = new FormData(e.target);

  // Gather sample arrays
  const sampleIds = formData.getAll("sample_id[]");
  const matrices = formData.getAll("chemical_matrix[]");
  const types = formData.getAll("sample_type[]");
  const times = formData.getAll("processing_time[]");
  const analyses = [];
  let i = 0;
  while (formData.has(`analysis[${i}][]`)) {
    analyses.push(formData.getAll(`analysis[${i}][]`));
    i++;
  }
  console.info("FormData keys:", Array.from(formData.keys()));
  console.info("Sample IDs:", sampleIds);
  console.info("Matrices:", matrices);
  console.info("Types:", types);
  console.info("Times:", times);
  console.info("Analyses:", analyses);
  console.log(document.getElementById("samples").innerHTML);
  console.log("Raw FormData entries:");
  for (let [key, value] of formData.entries()) {
    console.log(key, value);
  }
  // Build samples array
  const samples = sampleIds.map((id, idx) => ({
    sample_id: id,
    chemical_matrix: matrices[idx],
    sample_type: types[idx],
    processing_time: times[idx],
    analyses: analyses[idx] || []
  }));
  console.info("samples:",samples);
  // Gather other fields
  const data = {
    customer_name: formData.get("customer-name"),
    street_address: formData.get("street-address"),
    city: formData.get("city"),
    state: formData.get("state"),
    country: formData.get("country"),
    customer_contact: formData.get("customer-contact"),
    customer_phone: formData.get("customer-phone"),
    results_list: formData.get("results-list"),
    results_cc_list: formData.get("results-cc-list"),
    payment_method: formData.get("payment_method"),
    po_number: formData.get("po-number"),
    cc_number: formData.get("cc-number"),
    invoice_list: formData.get("invoice-list"),
    invoice_cc_list: formData.get("invoice-cc-list"),
    samples: samples
  };

  // Save for later submission
  pendingFormData = data;

  // Show modal with JSON summary
  document.getElementById("jsonSummary").textContent = JSON.stringify(data, null, 2);
  document.getElementById("confirmationModal").style.display = "block";
});

// Confirm button submits to server
document.getElementById("confirmBtn").onclick = async function() {
  document.getElementById("confirmationModal").style.display = "none";
  // Submit to backend
  const res = await fetch("/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(pendingFormData)
  });
  const result = await res.json();
  alert(result.message);
  pendingFormData = null;
};

// Cancel button hides modal
document.getElementById("cancelBtn").onclick = function() {
  document.getElementById("confirmationModal").style.display = "none";
  pendingFormData = null;
};