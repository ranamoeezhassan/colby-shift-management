const SchedulerAPI = {
    baseUrl: '/scheduler/api/shifts',

    async listShifts(filters = {}) {
        const params = new URLSearchParams();
        if (filters.term_id) params.append('term_id', filters.term_id);
        if (filters.user_id) params.append('user_id', filters.user_id);
        if (filters.start_date) params.append('start_date', filters.start_date);
        if (filters.end_date) params.append('end_date', filters.end_date);

        const url = params.toString() ? `${this.baseUrl}?${params}` : this.baseUrl;
        const response = await fetch(url);
        return response.json();
    },

    async getShift(shiftId) {
        const response = await fetch(`${this.baseUrl}/${shiftId}`);
        return response.json();
    },

    async createShift(shiftData) {
        const response = await fetch(this.baseUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(shiftData)
        });
        return {
            status: response.status,
            data: await response.json()
        };
    },

    async updateShift(shiftId, shiftData) {
        const response = await fetch(`${this.baseUrl}/${shiftId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(shiftData)
        });
        return {
            status: response.status,
            data: await response.json()
        };
    },

    async deleteShift(shiftId) {
        const response = await fetch(`${this.baseUrl}/${shiftId}`, {
            method: 'DELETE'
        });
        return {
            status: response.status,
            success: response.status === 204
        };
    },

    async reassignShift(shiftId, userId) {
        const response = await fetch(`${this.baseUrl}/${shiftId}/assignee`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId })
        });
        return {
            status: response.status,
            data: await response.json()
        };
    },

    async validateShift(shiftData) {
        const response = await fetch(`${this.baseUrl}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(shiftData)
        });
        return response.json();
    }
};

let currentTermId = null;
let currentPolicy = null;

function initSchedulerUI(termId, policy) {
    currentTermId = termId;
    currentPolicy = policy;
    
    ['edit', 'create'].forEach(prefix => {
        ['user_id', 'date', 'start_time', 'end_time'].forEach(field => {
            const el = document.getElementById(`${prefix}_${field}`);
            if (el) {
                el.addEventListener('change', () => validateForm(prefix));
            }
        });
    });
}

async function openEditModal(shiftId) {
    try {
        const result = await SchedulerAPI.getShift(shiftId);
        if (result.success && result.data) {
            document.getElementById('edit_shift_id').value = result.data.shift_id;
            document.getElementById('edit_user_id').value = result.data.user_id;
            document.getElementById('edit_date').value = result.data.date;
            document.getElementById('edit_start_time').value = result.data.start_time;
            document.getElementById('edit_end_time').value = result.data.end_time;
            document.getElementById('editModal').classList.add('active');
        }
    } catch (error) {
        console.error('Error loading shift:', error);
        alert('Error loading shift data');
    }
}

function closeEditModal() {
    document.getElementById('editModal').classList.remove('active');
    document.getElementById('validationFeedback').style.display = 'none';
}

async function saveShift() {
    const shiftId = document.getElementById('edit_shift_id').value;
    const shiftData = {
        user_id: document.getElementById('edit_user_id').value,
        date: document.getElementById('edit_date').value,
        start_time: document.getElementById('edit_start_time').value,
        end_time: document.getElementById('edit_end_time').value
    };
    
    try {
        const result = await SchedulerAPI.updateShift(shiftId, shiftData);
        if (result.data.success) {
            location.reload();
        } else {
            showValidation('validationFeedback', result.data.error, result.data.warning ? 'warning' : 'error');
        }
    } catch (error) {
        console.error('Error saving shift:', error);
        showValidation('validationFeedback', 'Error saving shift', 'error');
    }
}

async function deleteShift() {
    if (!confirm('Are you sure you want to delete this shift?')) return;
    
    const shiftId = document.getElementById('edit_shift_id').value;
    
    try {
        const result = await SchedulerAPI.deleteShift(shiftId);
        if (result.success) {
            location.reload();
        } else {
            alert('Error deleting shift');
        }
    } catch (error) {
        console.error('Error deleting shift:', error);
        alert('Error deleting shift: ' + error.message);
    }
}

function openCreateModal() {
    document.getElementById('createModal').classList.add('active');
}

function openCreateModalForDate(date) {
    document.getElementById('create_date').value = date;
    document.getElementById('createModal').classList.add('active');
}

function closeCreateModal() {
    document.getElementById('createModal').classList.remove('active');
    document.getElementById('createValidationFeedback').style.display = 'none';
}

async function createShift() {
    const shiftData = {
        term_id: currentTermId,
        user_id: document.getElementById('create_user_id').value,
        date: document.getElementById('create_date').value,
        start_time: document.getElementById('create_start_time').value,
        end_time: document.getElementById('create_end_time').value
    };
    
    try {
        const result = await SchedulerAPI.createShift(shiftData);
        if (result.data.success) {
            location.reload();
        } else {
            showValidation('createValidationFeedback', result.data.error, result.data.warning ? 'warning' : 'error');
        }
    } catch (error) {
        console.error('Error creating shift:', error);
        showValidation('createValidationFeedback', 'Error creating shift', 'error');
    }
}

function showValidation(elementId, message, type) {
    const el = document.getElementById(elementId);
    el.textContent = message;
    el.className = 'validation-feedback ' + type;
    el.style.display = 'block';
}

async function validateForm(prefix) {
    const shiftData = {
        term_id: currentTermId,
        user_id: document.getElementById(`${prefix}_user_id`).value,
        date: document.getElementById(`${prefix}_date`).value,
        start_time: document.getElementById(`${prefix}_start_time`).value,
        end_time: document.getElementById(`${prefix}_end_time`).value
    };
    
    if (prefix === 'edit') {
        shiftData.shift_id = document.getElementById('edit_shift_id').value;
    }
    
    try {
        const result = await SchedulerAPI.validateShift(shiftData);
        const feedbackId = prefix === 'edit' ? 'validationFeedback' : 'createValidationFeedback';
        
        if (result.success && result.data) {
            if (result.data.errors && result.data.errors.length > 0) {
                showValidation(feedbackId, result.data.errors.join(', '), 'error');
            } else if (result.data.warnings && result.data.warnings.length > 0) {
                showValidation(feedbackId, result.data.warnings.join(', '), 'warning');
            } else {
                document.getElementById(feedbackId).style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Validation error:', error);
    }
}

