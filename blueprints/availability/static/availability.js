const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
let currentTermId = null;

// ---------- Alerts ----------
function showAlert(message, type = 'info') {
  const container = document.getElementById('alert-container');
  if (!container) return;

  const div = document.createElement('div');
  div.className = 'alert ' + type; // uses .alert.success / .alert.error / .alert.info in CSS
  div.textContent = message;
  container.appendChild(div);

  setTimeout(() => {
    if (container.contains(div)) {
      container.removeChild(div);
    }
  }, 5000);
}

// ---------- CSV Guide toggle ----------
function toggleGuide() {
  const guide = document.getElementById('csvGuide');
  const button = document.querySelector('.guide-toggle');
  if (!guide || !button) return;

  const isHidden = guide.style.display === 'none';
  guide.style.display = isHidden ? 'block' : 'none';
  button.textContent = isHidden ? '📘 Hide CSV Guide' : '📘 View CSV Format Guide';
}

// ---------- Load terms and availability ----------
async function loadTerms() {
  try {
    const res = await fetch('/availability/api/v1/terms');
    if (!res.ok) {
      showAlert('Failed to load terms...', 'error');
      return;
    }
    const terms = await res.json();
    const select = document.getElementById('term_select');
    if (!select) return;

    select.innerHTML = '';
    if (terms.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '-- No terms defined --';
      select.appendChild(opt);
      return;
    }

    terms.forEach((t, index) => {
      const opt = document.createElement('option');
      opt.value = t.term_id;
      opt.textContent = `${t.name} (${t.start_date.slice(5)} - ${t.end_date.slice(5)})`;
      select.appendChild(opt);
      if (index === 0) currentTermId = t.term_id;
    });

    select.value = currentTermId;
    await loadAvailability();
  } catch (err) {
    showAlert('Error loading terms.', 'error');
    console.error(err);
  }
}

async function loadAvailability() {
  if (!currentTermId) return;

  try {
    const res = await fetch(`/availability/api/v1/availability?term_id=${currentTermId}`);
    if (!res.ok) {
      showAlert('Failed to load availability...', 'error');
      return;
    }
    const data = await res.json();
    renderAvailabilityTable(data.availability || {});
  } catch (err) {
    showAlert('Error loading availability.', 'error');
    console.error(err);
  }
}

function renderAvailabilityTable(availability) {
  const tbody = document.getElementById('availabilityBody');
  if (!tbody) return;

  tbody.innerHTML = '';

  // Existing rows
  Object.entries(availability).forEach(([studentName, dayMap]) => {
    const tr = document.createElement('tr');

    const nameTd = document.createElement('td');
    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.value = studentName;
    nameInput.readOnly = true;
    nameInput.className = 'student-name-input';
    nameTd.appendChild(nameInput);
    tr.appendChild(nameTd);

    DAYS.forEach(day => {
      const td = document.createElement('td');
      const input = document.createElement('input');
      input.type = 'text';
      const blocks = dayMap[day] || [];
      input.value = blocks.join(', ');
      input.placeholder = 'e.g. 09:00-17:00';
      input.setAttribute('data-day', day);
      td.appendChild(input);
      tr.appendChild(td);
    });

    // Actions (Clear)
    const actionTd = document.createElement('td');
    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.textContent = '🗑 Clear';
    clearBtn.className = 'row-clear-btn';
    clearBtn.addEventListener('click', () => clearRow(studentName));
    actionTd.appendChild(clearBtn);
    tr.appendChild(actionTd);

    tbody.appendChild(tr);
  });

  // New row
  const newTr = document.createElement('tr');
  newTr.style.background = '#f8f9fb';

  const newNameTd = document.createElement('td');
  const newNameInput = document.createElement('input');
  newNameInput.type = 'text';
  newNameInput.placeholder = '➕ Add new student...';
  newNameInput.className = 'student-name-input';
  newNameTd.appendChild(newNameInput);
  newTr.appendChild(newNameTd);

  DAYS.forEach(day => {
    const td = document.createElement('td');
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = '09:00-17:00';
    input.setAttribute('data-day', day);
    td.appendChild(input);
    newTr.appendChild(td);
  });

  const newActionTd = document.createElement('td');
  newTr.appendChild(newActionTd);

  tbody.appendChild(newTr);
}

// ---------- Collect table data and save ----------
function collectRows() {
  const rows = [];
  const tbody = document.getElementById('availabilityBody');
  if (!tbody) return rows;

  const trList = Array.from(tbody.querySelectorAll('tr'));

  trList.forEach(tr => {
    const nameInput = tr.querySelector('.student-name-input');
    const studentName = nameInput?.value.trim();
    if (!studentName) return;

    const rowObj = { student_name: studentName };
    DAYS.forEach(day => {
      const input = tr.querySelector(`input[data-day="${day}"]`);
      rowObj[day] = input ? input.value.trim() : "";
    });
    rows.push(rowObj);
  });

  return rows;
}

async function saveAvailability() {
  if (!currentTermId) {
    showAlert('Please select a term first.', 'error');
    return;
  }

  const rows = collectRows();
  try {
    const res = await fetch('/availability/api/v1/availability', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ term_id: currentTermId, rows })
    });

    const json = await res.json();
    if (res.ok) {
      showAlert(
        json.message || 'Availability updated!',
        json.errors && json.errors.length ? 'error' : 'success'
      );
      await loadAvailability();
    } else {
      showAlert(json.error || 'Failed to update availability...', 'error');
    }
  } catch (err) {
    showAlert('Error updating availability.', 'error');
    console.error(err);
  }
}

// ---------- Clear a row ----------
async function clearRow(studentName) {
  if (!currentTermId) return;
  if (!confirm(`Clear all availability for ${studentName} in this term?`)) return;

  try {
    const res = await fetch('/availability/api/v1/availability/clear-row', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ term_id: currentTermId, student_name: studentName })
    });

    const json = await res.json();
    if (res.ok) {
      showAlert(json.message || 'Row cleared!', 'success');
      await loadAvailability();
    } else {
      showAlert(json.error || 'Failed to clear row...', 'error');
    }
  } catch (err) {
    showAlert('Error clearing row.', 'error');
    console.error(err);
  }
}

// ---------- CSV upload ----------
async function handleCsvUpload(event) {
  event.preventDefault();
  if (!currentTermId) {
    showAlert('Please select a term first for CSV upload.', 'error');
    return;
  }

  const form = document.getElementById('csvForm');
  if (!form) return;

  const formData = new FormData(form);
  formData.append('term_id', currentTermId);

  try {
    const res = await fetch('/availability/api/v1/availability/upload', {
      method: 'POST',
      body: formData
    });

    const json = await res.json();
    if (res.ok) {
      showAlert(
        json.message || 'CSV processed!',
        json.errors && json.errors.length ? 'error' : 'success'
      );
      await loadAvailability();
    } else {
      showAlert(json.error || 'CSV upload failed...', 'error');
    }
  } catch (err) {
    showAlert('Error uploading CSV.', 'error');
    console.error(err);
  }

  // Reset file input + label text after upload
  const fileInput = document.getElementById('csvFile');
  const label = document.querySelector('.file-input-label');
  if (fileInput) {
    fileInput.value = '';
  }
  if (label) {
    label.textContent = 'Choose File';
    label.style.background = '';
  }
}

// ---------- DOM Ready ----------
document.addEventListener('DOMContentLoaded', () => {
  loadTerms();

  const termSelect = document.getElementById('term_select');
  if (termSelect) {
    termSelect.addEventListener('change', async (e) => {
      currentTermId = e.target.value;
      await loadAvailability();
    });
  }

  const saveButton = document.getElementById('saveButton');
  if (saveButton) {
    saveButton.addEventListener('click', saveAvailability);
  }

  const csvForm = document.getElementById('csvForm');
  if (csvForm) {
    csvForm.addEventListener('submit', handleCsvUpload);
  }

  const csvFileInput = document.getElementById('csvFile');
  if (csvFileInput) {
    csvFileInput.addEventListener('change', function (e) {
      const fileName = e.target.files[0]?.name;
      if (fileName) {
        const label = document.querySelector('.file-input-label');
        if (label) {
          label.textContent = fileName;
        }
      }
    });
  }
});
