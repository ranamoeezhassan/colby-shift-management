const OutputsAPI = {
    baseUrl: '/outputs/api',

    async listSchedules(filters = {}) {
        const params = new URLSearchParams();
        if (filters.term_id) params.append('term_id', filters.term_id);
        if (filters.user_id) params.append('user_id', filters.user_id);
        if (filters.start_date) params.append('start_date', filters.start_date);
        if (filters.end_date) params.append('end_date', filters.end_date);

        const url = params.toString() 
            ? `${this.baseUrl}/schedules?${params}` 
            : `${this.baseUrl}/schedules`;
        
        const response = await fetch(url);
        return response.json();
    },

    async getSchedulePreview(options = {}) {
        const params = new URLSearchParams();
        if (options.term_id) params.append('term_id', options.term_id);
        if (options.week !== undefined) params.append('week', options.week);

        const url = params.toString() 
            ? `${this.baseUrl}/schedules/preview?${params}` 
            : `${this.baseUrl}/schedules/preview`;
        
        const response = await fetch(url);
        return response.json();
    },

    async listStudents(options = {}) {
        const params = new URLSearchParams();
        if (options.search) params.append('search', options.search);
        if (options.term_id) params.append('term_id', options.term_id);

        const url = params.toString() 
            ? `${this.baseUrl}/students?${params}` 
            : `${this.baseUrl}/students`;
        
        const response = await fetch(url);
        return response.json();
    },

    async getStudentSchedule(userId, options = {}) {
        const params = new URLSearchParams();
        if (options.term_id) params.append('term_id', options.term_id);
        if (options.week !== undefined) params.append('week', options.week);

        const url = params.toString() 
            ? `${this.baseUrl}/students/${userId}/schedule?${params}` 
            : `${this.baseUrl}/students/${userId}/schedule`;
        
        const response = await fetch(url);
        return response.json();
    }
};

function formatDuration(hours) {
    if (hours < 1) {
        return `${Math.round(hours * 60)} min`;
    }
    return `${hours.toFixed(1)} hrs`;
}

function formatDate(dateStr) {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', { 
        weekday: 'short', 
        month: 'short', 
        day: 'numeric' 
    });
}

function formatTime(timeStr) {
    const [hours, minutes] = timeStr.split(':').map(Number);
    const period = hours >= 12 ? 'PM' : 'AM';
    const hour12 = hours % 12 || 12;
    return `${hour12}:${minutes.toString().padStart(2, '0')} ${period}`;
}

function renderShiftCard(shift) {
    const card = document.createElement('div');
    card.className = 'shift-card';
    
    if (!shift.constraint_passed) {
        card.classList.add('violation');
    } else if (shift.warnings && shift.warnings.length > 0) {
        card.classList.add('warning');
    }
    
    card.innerHTML = `
        <div class="shift-student">${shift.user_name}</div>
        <div class="shift-time">${formatTime(shift.start_time)} - ${formatTime(shift.end_time)}</div>
        <div class="shift-duration">${formatDuration(shift.duration_hours)}</div>
        ${shift.warnings && shift.warnings.length > 0 
            ? `<div class="shift-warnings">${shift.warnings.join(', ')}</div>` 
            : ''}
    `;
    
    return card;
}

function renderWeekNav(currentIndex, totalWeeks, onNavigate) {
    const nav = document.createElement('div');
    nav.className = 'week-nav';
    
    const prevBtn = document.createElement('button');
    prevBtn.textContent = '← Previous';
    prevBtn.disabled = currentIndex === 0;
    prevBtn.onclick = () => onNavigate(currentIndex - 1);
    
    const indicator = document.createElement('span');
    indicator.textContent = `Week ${currentIndex + 1} of ${totalWeeks}`;
    
    const nextBtn = document.createElement('button');
    nextBtn.textContent = 'Next →';
    nextBtn.disabled = currentIndex >= totalWeeks - 1;
    nextBtn.onclick = () => onNavigate(currentIndex + 1);
    
    nav.appendChild(prevBtn);
    nav.appendChild(indicator);
    nav.appendChild(nextBtn);
    
    return nav;
}

