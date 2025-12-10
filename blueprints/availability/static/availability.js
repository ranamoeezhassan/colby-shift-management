const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
let currentTermId = null;

// Helpers
function createDayCell(day, blocksArray) {
  const td = document.createElement('td');

  const wrapper = document.createElement('div');
  wrapper.className = 'day-cell';
  wrapper.dataset.day = day;

  const blocksContainer = document.createElement('div');
  blocksContainer.className = 'blocks-container';

  (blocksArray || []).forEach(block => {
    const pill = document.createElement('span');
    pill.className = 'block-pill';
    pill.dataset.range = block;
    pill.textContent = block.replace('-', '–'); // nicer dash

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'block-pill-remove';
    remove.textContent = '×';

    pill.appendChild(remove);
    blocksContainer.appendChild(pill);
  });

  const addBtn = document.createElement('button');
  addBtn.type = 'button';
  addBtn.className = 'add-block-btn';
  addBtn.textContent = '+ Add';
  addBtn.dataset.day = day;

  wrapper.appendChild(blocksContainer);
  wrapper.appendChild(addBtn);
  td.appendChild(wrapper);

  return td;
}

let autoSaveTimeout = null;

function scheduleAutoSave() {
  // If no term selected yet, don't bother
  if (!currentTermId) return;

  // Debounce so we don't spam the server if user clicks fast
  if (autoSaveTimeout) {
    clearTimeout(autoSaveTimeout);
  }

  autoSaveTimeout = setTimeout(() => {
    saveAvailability();
  }, 400);
}


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
    nameTd.className = 'name-cell';
    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.value = studentName;
    nameInput.readOnly = true;
    nameInput.className = 'student-name-input';
    nameTd.appendChild(nameInput);
    tr.appendChild(nameTd);

    DAYS.forEach(day => {
      const blocks = dayMap[day] || [];
      const td = createDayCell(day, blocks);
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
  newNameTd.className = 'name-cell';
  const newNameInput = document.createElement('input');
  newNameInput.type = 'text';
  newNameInput.placeholder = '➕ Add new student...';
  newNameInput.className = 'student-name-input';
  newNameTd.appendChild(newNameInput);
  newTr.appendChild(newNameTd);

  DAYS.forEach(day => {
    const td = createDayCell(day, []); // empty blocks
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
    if (!studentName) return; // skip the empty "new row"

    const rowObj = { student_name: studentName };

    DAYS.forEach(day => {
      const cell = tr.querySelector(`.day-cell[data-day="${day}"]`);
      if (!cell) {
        rowObj[day] = '';
        return;
      }

      const pills = Array.from(cell.querySelectorAll('.block-pill'));
      const ranges = pills.map(p => p.dataset.range || p.textContent.trim());
      rowObj[day] = ranges.join(', ');
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

async function clearAllAvailability() {
  if (!currentTermId) {
    showAlert('Please select a term first.', 'error');
    return;
  }

  if (!confirm('Are you sure you want to clear ALL availability for this term? This cannot be undone.')) {
    return;
  }

  const res = await fetch('/availability/api/v1/availability/clear-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ term_id: currentTermId })
  });

  const json = await res.json();

  if (res.ok) {
    showAlert(json.message || 'All availability cleared for this term.', 'success');

    // Clear any previous CSV error details as they’re no longer relevant
    if (typeof renderCsvErrors === 'function') {
      renderCsvErrors([]);
    }

    await loadAvailability();
  } else {
    showAlert(json.error || 'Failed to clear all availability...', 'error');
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

  const res = await fetch('/availability/api/v1/availability/upload', {
    method: 'POST',
    body: formData
  });

  const json = await res.json();

  if (res.ok) {
    const summary = json.summary || {};
    const errors = json.errors || [];
    const partial = summary.partial_success;

    let alertType = 'success';
    if (partial) {
      alertType = 'warning';  // some rows failed, some succeeded
    }

    showAlert(json.message || 'CSV processed!', alertType);
    renderCsvErrors(errors);  // 🔹 show row-level issues, if any

    await loadAvailability();
  } else {
    // Hard failure: still try to show details if present
    const errors = json.errors || (json.error ? [json.error] : []);
    showAlert(json.error || 'CSV upload failed...', 'error');
    renderCsvErrors(errors);
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

function renderCsvErrors(errors) {
  const panel = document.getElementById('csvErrorPanel');
  const list = document.getElementById('csvErrorList');
  if (!panel || !list) return;

  list.innerHTML = '';

  if (!errors || errors.length === 0) {
    panel.style.display = 'none';
    return;
  }

  errors.forEach(msg => {
    const li = document.createElement('li');
    li.textContent = msg;
    list.appendChild(li);
  });

  panel.style.display = 'block';
}

async function exportCsv() {
  if (!currentTermId) {
    showAlert('Please select a term first.', 'error');
    return;
  }

  try {
    const res = await fetch(`/availability/api/v1/availability/export?term_id=${currentTermId}`);

    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      showAlert(json.error || 'Failed to export CSV...', 'error');
      return;
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `availability_term_${currentTermId}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);

    showAlert('CSV exported successfully.', 'success');
  } catch (err) {
    console.error(err);
    showAlert('An error occurred while exporting CSV.', 'error');
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

  const clearAllBtn = document.getElementById('clearAllButton');
  if (clearAllBtn) {
    clearAllBtn.addEventListener('click', clearAllAvailability);
  }

  const exportBtn = document.getElementById('exportCsvButton');
  if (exportBtn) {
    exportBtn.addEventListener('click', exportCsv);
  }

  const availabilityBody = document.getElementById('availabilityBody');
  if (availabilityBody) {
    availabilityBody.addEventListener('click', (e) => {
      const addBtn = e.target.closest('.add-block-btn');
      const removeBtn = e.target.closest('.block-pill-remove');

      // Add new block
      if (addBtn) {
        const day = addBtn.dataset.day;
        const cell = addBtn.closest('.day-cell');
        if (!cell) return;

        const input = window.prompt(`Enter time block for ${day} (HH:MM-HH:MM)`, '09:00-11:00');
        if (!input) return;

        const trimmed = input.trim();
        if (!/^\d{2}:\d{2}\s*-\s*\d{2}:\d{2}$/.test(trimmed)) {
          showAlert('Please use format HH:MM-HH:MM, e.g. 09:00-11:00', 'error');
          return;
        }

        const blocksContainer = cell.querySelector('.blocks-container');
        if (!blocksContainer) return;

        const pill = document.createElement('span');
        pill.className = 'block-pill';
        pill.dataset.range = trimmed;
        pill.textContent = trimmed.replace('-', '–');

        const rm = document.createElement('button');
        rm.type = 'button';
        rm.className = 'block-pill-remove';
        rm.textContent = '×';
        pill.appendChild(rm);

        blocksContainer.appendChild(pill);
        scheduleAutoSave();
      }

      // Remove existing block
      if (removeBtn) {
        const pill = removeBtn.closest('.block-pill');
        if (pill) {
          pill.remove();

          scheduleAutoSave();
        }
      }
    });
  }
  
});
