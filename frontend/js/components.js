/**
 * JobHunt - Reusable UI Components
 * Vanilla JavaScript components for the job search dashboard
 */

// ==================== ICONS ====================
const Icons = {
    search: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`,

    briefcase: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="14" x="2" y="7" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>`,

    building: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="20" x="4" y="2" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/></svg>`,

    mapPin: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>`,

    dollarSign: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" x2="12" y1="2" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>`,

    clock: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,

    star: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,

    starFilled: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,

    x: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>`,

    check: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,

    checkCircle: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,

    xCircle: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>`,

    alertCircle: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>`,

    info: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>`,

    send: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>`,

    mail: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>`,

    edit: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>`,

    trash: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>`,

    externalLink: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>`,

    refresh: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg>`,

    settings: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>`,

    play: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,

    calendar: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>`,

    user: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,

    users: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,

    target: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,

    zap: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,

    sun: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>`,

    moon: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>`,

    chevronDown: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>`,

    chevronUp: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 15-6-6-6 6"/></svg>`,

    chevronRight: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>`,

    chevronLeft: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>`,

    moreVertical: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg>`,

    filter: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>`,

    linkedin: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>`,

    fileText: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><line x1="10" x2="8" y1="9" y2="9"/></svg>`,

    copy: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`,

    sparkles: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>`,

    globe: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" x2="22" y1="12" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,

    award: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg>`
};

// ==================== UTILITY FUNCTIONS ====================

/**
 * Get fit score level based on percentage
 * @param {number} score - Fit score (0-1 or 0-100)
 * @returns {string} - Fit level: 'great', 'good', 'okay', 'poor'
 */
function getFitLevel(score) {
    // Normalize score to 0-100 range
    const normalizedScore = score <= 1 ? score * 100 : score;

    if (normalizedScore >= 80) return 'great';
    if (normalizedScore >= 60) return 'good';
    if (normalizedScore >= 40) return 'okay';
    return 'poor';
}

/**
 * Format salary for display
 * @param {number} salary - Salary amount
 * @returns {string} - Formatted salary (e.g., "120K")
 */
function formatSalary(salary) {
    if (!salary) return '';
    if (salary >= 1000) {
        return `${Math.round(salary / 1000)}K`;
    }
    return salary.toLocaleString();
}

/**
 * Format date for display
 * @param {string|Date} date - Date to format
 * @returns {string} - Relative or formatted date
 */
function formatDate(date) {
    if (!date) return '';

    const d = new Date(date);
    const now = new Date();
    const diffMs = now - d;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`;

    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Format datetime for display
 * @param {string|Date} date - Date to format
 * @returns {string} - Formatted datetime
 */
function formatDateTime(date) {
    if (!date) return '';

    const d = new Date(date);
    return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
    });
}

/**
 * Escape HTML to prevent XSS
 * @param {string} str - String to escape
 * @returns {string} - Escaped string
 */
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Truncate text with ellipsis
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Maximum length
 * @returns {string} - Truncated text
 */
function truncateText(text, maxLength = 100) {
    if (!text || text.length <= maxLength) return text || '';
    return text.substring(0, maxLength).trim() + '...';
}

/**
 * Get initials from a name
 * @param {string} name - Full name
 * @returns {string} - Initials (max 2 characters)
 */
function getInitials(name) {
    if (!name) return '?';
    return name
        .split(' ')
        .map(n => n[0])
        .join('')
        .toUpperCase()
        .substring(0, 2);
}

// ==================== UI COMPONENTS ====================

/**
 * Job Card Component
 * @param {Object} job - Job object
 * @returns {string} - HTML string
 */
function JobCard(job) {
    const fitLevel = getFitLevel(job.fit_score);
    const fitScore = Math.round((job.fit_score <= 1 ? job.fit_score * 100 : job.fit_score));
    const isSelected = window.state?.selectedJob?.id === job.id;
    const isStarred = job.is_starred || false;

    let salaryHtml = '';
    if (job.salary_min || job.salary_max) {
        if (job.salary_min && job.salary_max) {
            salaryHtml = `<div class="job-card-salary">$${formatSalary(job.salary_min)} - $${formatSalary(job.salary_max)}</div>`;
        } else if (job.salary_max) {
            salaryHtml = `<div class="job-card-salary">Up to $${formatSalary(job.salary_max)}</div>`;
        } else if (job.salary_min) {
            salaryHtml = `<div class="job-card-salary">$${formatSalary(job.salary_min)}+</div>`;
        }
    }

    let statusBadge = '';
    if (job.status && job.status !== 'new') {
        statusBadge = `<span class="status-badge ${job.status}">${job.status}</span>`;
    }

    // Category labels for display
    const categoryLabels = {
        'ai_ml': 'AI/ML',
        'full_stack': 'Full Stack',
        'backend': 'Backend',
        'frontend': 'Frontend',
        'devops': 'DevOps',
        'data': 'Data',
        'mobile': 'Mobile',
        'security': 'Security',
        'management': 'Management',
        'other': 'Other'
    };
    const categoryLabel = categoryLabels[job.category] || '';
    const categoryBadge = categoryLabel ?
        `<span class="category-badge">${categoryLabel}</span>` : '';

    return `
        <div class="job-card fit-${fitLevel} ${isSelected ? 'selected' : ''}"
             data-job-id="${job.id}"
             onclick="onJobSelect('${job.id}')">
            <div class="job-card-header">
                <h3 class="job-card-title">${escapeHtml(job.title)}</h3>
                <span class="fit-badge fit-${fitLevel}">${fitScore}%</span>
            </div>
            <div class="job-card-company">
                ${Icons.building}
                ${escapeHtml(job.company_name)}
            </div>
            <div class="job-card-location">
                ${Icons.mapPin}
                ${escapeHtml(job.location || 'Remote')}
            </div>
            ${salaryHtml}
            <div class="job-card-footer">
                <div style="display: flex; align-items: center; gap: 8px;">
                    ${categoryBadge}
                    ${statusBadge}
                </div>
                <span class="job-card-posted">${formatDate(job.created_at || job.posted_at)}</span>
            </div>
            <div class="job-card-actions">
                <button class="job-card-action ${isStarred ? 'starred' : ''}"
                        onclick="event.stopPropagation(); toggleStar('${job.id}')"
                        title="${isStarred ? 'Remove star' : 'Star job'}">
                    ${isStarred ? Icons.starFilled : Icons.star}
                </button>
                <button class="job-card-action"
                        onclick="event.stopPropagation(); dismissJob('${job.id}')"
                        title="Dismiss">
                    ${Icons.x}
                </button>
            </div>
        </div>
    `;
}

/**
 * Fit Analysis Component
 * @param {Object} job - Job object with fit analysis
 * @returns {string} - HTML string
 */
function FitAnalysis(job) {
    const fitLevel = getFitLevel(job.fit_score);
    const fitScore = Math.round((job.fit_score <= 1 ? job.fit_score * 100 : job.fit_score));

    // Get LLM analysis from raw_data
    const llmAnalysis = job.raw_data?.llm_analysis || {};
    const reasoning = llmAnalysis.reasoning || '';
    const strengths = llmAnalysis.strengths || [];
    const concerns = llmAnalysis.concerns || [];
    const experienceMatch = llmAnalysis.experience_match || '';
    const titleAlignment = llmAnalysis.title_alignment || '';

    const matchedSkills = job.skills_matched || [];
    const missingSkills = job.skills_missing || [];

    // Build reasoning section
    let reasoningHtml = '';
    if (reasoning) {
        reasoningHtml = `
            <div class="fit-reasoning">
                <p>${escapeHtml(reasoning)}</p>
            </div>
        `;
    }

    // Build match indicators
    let matchIndicatorsHtml = '';
    if (experienceMatch || titleAlignment) {
        const getMatchClass = (match) => {
            if (match === 'strong') return 'matched';
            if (match === 'moderate') return 'partial';
            return 'missing';
        };
        const getMatchIcon = (match) => {
            if (match === 'strong') return Icons.check;
            if (match === 'moderate') return Icons.alertCircle;
            return Icons.x;
        };
        matchIndicatorsHtml = `
            <div class="fit-indicators">
                ${experienceMatch ? `
                    <div class="fit-indicator ${getMatchClass(experienceMatch)}">
                        ${getMatchIcon(experienceMatch)}
                        <span>Experience: ${experienceMatch}</span>
                    </div>
                ` : ''}
                ${titleAlignment ? `
                    <div class="fit-indicator ${getMatchClass(titleAlignment)}">
                        ${getMatchIcon(titleAlignment)}
                        <span>Title Fit: ${titleAlignment}</span>
                    </div>
                ` : ''}
            </div>
        `;
    }

    // Build strengths section
    let strengthsHtml = '';
    if (strengths.length > 0) {
        strengthsHtml = `
            <div class="fit-section">
                <div class="fit-section-title matched">
                    ${Icons.check}
                    Why You're a Good Fit
                </div>
                <ul class="fit-list strengths">
                    ${strengths.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    // Build concerns section
    let concernsHtml = '';
    if (concerns.length > 0) {
        concernsHtml = `
            <div class="fit-section">
                <div class="fit-section-title missing">
                    ${Icons.alertCircle}
                    Potential Gaps
                </div>
                <ul class="fit-list concerns">
                    ${concerns.map(c => `<li>${escapeHtml(c)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    // Build skills section (collapsible)
    let skillsHtml = '';
    if (matchedSkills.length > 0 || missingSkills.length > 0) {
        skillsHtml = `
            <div class="fit-skills-section">
                <div class="fit-section-title" onclick="this.parentElement.classList.toggle('expanded')" style="cursor: pointer;">
                    ${Icons.briefcase}
                    Skills Breakdown
                    <span class="chevron">${Icons.chevronDown}</span>
                </div>
                <div class="fit-skills-content">
                    ${matchedSkills.length > 0 ? `
                        <div class="skill-tags">
                            ${matchedSkills.map(skill => `
                                <span class="skill-tag matched">${escapeHtml(skill)}</span>
                            `).join('')}
                        </div>
                    ` : ''}
                    ${missingSkills.length > 0 ? `
                        <div class="skill-tags" style="margin-top: 8px;">
                            ${missingSkills.map(skill => `
                                <span class="skill-tag missing">${escapeHtml(skill)}</span>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    const hasAnalysis = reasoning || strengths.length || concerns.length || matchedSkills.length || missingSkills.length;

    return `
        <div class="fit-analysis-card">
            <div class="fit-analysis-header">
                <div class="fit-analysis-title">
                    ${Icons.target}
                    Fit Analysis
                </div>
                <div class="fit-analysis-score">
                    <span class="fit-score-large fit-${fitLevel}">${fitScore}%</span>
                    <span class="badge badge-${fitLevel === 'great' ? 'success' : fitLevel === 'good' ? 'info' : fitLevel === 'okay' ? 'warning' : 'default'}">
                        ${fitLevel === 'great' ? 'Great Match' : fitLevel === 'good' ? 'Good Match' : fitLevel === 'okay' ? 'Fair Match' : 'Low Match'}
                    </span>
                </div>
            </div>
            <div class="fit-analysis-body">
                ${reasoningHtml}
                ${matchIndicatorsHtml}
                ${strengthsHtml}
                ${concernsHtml}
                ${skillsHtml}
                ${!hasAnalysis ? `
                    <p class="text-tertiary text-center p-md">
                        No analysis available yet
                    </p>
                ` : ''}
            </div>
        </div>
    `;
}

/**
 * Requirements Checklist Component
 * @param {Object} job - Job object with requirements
 * @returns {string} - HTML string
 */
function RequirementsChecklist(job) {
    const requirements = job.requirements || [];

    if (requirements.length === 0) {
        return '';
    }

    const met = requirements.filter(r => r.met).length;
    const total = requirements.length;

    return `
        <div class="requirements-card">
            <div class="requirements-header">
                <span class="requirements-title">Requirements</span>
                <span class="requirements-progress">
                    <strong>${met}</strong> of ${total} met
                </span>
            </div>
            <div class="requirements-list">
                ${requirements.map(req => `
                    <div class="requirement-item">
                        <div class="requirement-check ${req.met ? 'met' : req.partial ? 'partial' : 'unmet'}">
                            ${req.met ? Icons.check : req.partial ? Icons.alertCircle : Icons.x}
                        </div>
                        <span class="requirement-text">${escapeHtml(req.text)}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

/**
 * Application Timeline Component
 * @param {Object} application - Application object
 * @returns {string} - HTML string
 */
function ApplicationTimeline(application) {
    const events = application?.events || [];

    if (events.length === 0) {
        return `
            <div class="empty-state">
                <div class="empty-state-icon">${Icons.clock}</div>
                <h3 class="empty-state-title">No Activity Yet</h3>
                <p class="empty-state-description">Timeline will appear once you start your application</p>
            </div>
        `;
    }

    return `
        <div class="timeline">
            ${events.map((event, index) => `
                <div class="timeline-item ${event.completed ? 'completed' : index === 0 ? 'current' : ''}">
                    <div class="timeline-dot"></div>
                    <div class="timeline-content">
                        <div class="timeline-title">${escapeHtml(event.title)}</div>
                        <div class="timeline-date">${formatDateTime(event.date)}</div>
                        ${event.description ? `
                            <div class="timeline-description">${escapeHtml(event.description)}</div>
                        ` : ''}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

/**
 * Cover Letter Editor Component
 * @param {Object} draft - Cover letter draft
 * @returns {string} - HTML string
 */
function CoverLetterEditor(draft) {
    const content = draft?.content || '';
    const charCount = content.length;

    return `
        <div class="cover-letter-editor">
            <div class="cover-letter-header">
                <span class="cover-letter-header-title">Cover Letter</span>
                <div class="cover-letter-actions">
                    <button class="btn btn-sm btn-ghost" onclick="generateCoverLetter()" title="Generate with AI">
                        ${Icons.sparkles}
                    </button>
                    <button class="btn btn-sm btn-ghost" onclick="copyCoverLetter()" title="Copy">
                        ${Icons.copy}
                    </button>
                    <button class="btn btn-sm btn-ghost" onclick="openCoverLetterModal()" title="Expand">
                        ${Icons.externalLink}
                    </button>
                </div>
            </div>
            <textarea class="cover-letter-textarea"
                      id="cover-letter-textarea"
                      placeholder="Write your cover letter here or click the sparkle icon to generate one with AI..."
                      oninput="updateCoverLetterDraft(this.value)">${escapeHtml(content)}</textarea>
            <div class="cover-letter-footer">
                <span>${charCount} characters</span>
                <span>Last saved: ${draft?.lastSaved ? formatDateTime(draft.lastSaved) : 'Not saved'}</span>
            </div>
        </div>
    `;
}

/**
 * Contact Selection Component
 * @param {Array} contacts - Array of contact objects
 * @param {string} selectedId - Selected contact ID
 * @returns {string} - HTML string
 */
function ContactSelection(contacts, selectedId) {
    if (!contacts || contacts.length === 0) {
        return `
            <div class="empty-state">
                <div class="empty-state-icon">${Icons.users}</div>
                <h3 class="empty-state-title">No Contacts Found</h3>
                <p class="empty-state-description">No contacts available for this company</p>
            </div>
        `;
    }

    return `
        <div class="contact-selection">
            ${contacts.map(contact => `
                <label class="contact-card ${contact.id === selectedId ? 'selected' : ''}"
                       onclick="selectContact('${contact.id}')">
                    <input type="radio" name="contact" value="${contact.id}"
                           ${contact.id === selectedId ? 'checked' : ''}>
                    <div class="contact-avatar">${getInitials(contact.name)}</div>
                    <div class="contact-info">
                        <div class="contact-name">${escapeHtml(contact.name)}</div>
                        <div class="contact-title">${escapeHtml(contact.title)}</div>
                        <div class="contact-email">${escapeHtml(contact.email)}</div>
                    </div>
                    ${contact.match_score ? `
                        <span class="contact-match">${Math.round(contact.match_score * 100)}% match</span>
                    ` : ''}
                </label>
            `).join('')}
        </div>
    `;
}

/**
 * Email Preview Component
 * @param {Object} email - Email object
 * @returns {string} - HTML string
 */
function EmailPreview(email) {
    if (!email) {
        return `
            <div class="empty-state">
                <div class="empty-state-icon">${Icons.mail}</div>
                <h3 class="empty-state-title">No Email Preview</h3>
                <p class="empty-state-description">Complete the steps above to preview your email</p>
            </div>
        `;
    }

    return `
        <div class="email-preview">
            <div class="email-preview-header">
                <div class="email-preview-field">
                    <span class="email-preview-label">To:</span>
                    <span class="email-preview-value">${escapeHtml(email.to)}</span>
                </div>
                <div class="email-preview-field">
                    <span class="email-preview-label">Subject:</span>
                    <span class="email-preview-value">${escapeHtml(email.subject)}</span>
                </div>
            </div>
            <div class="email-preview-body">${escapeHtml(email.body)}</div>
        </div>
    `;
}

/**
 * Stats Bar Component
 * @param {Object} stats - Stats object
 * @returns {string} - HTML string
 */
function StatsBar(stats) {
    return `
        <div class="stats-bar">
            <div class="stat-item">
                <span class="stat-value">${stats.total_jobs || 0}</span>
                <span class="stat-label">Jobs Found</span>
            </div>
            <div class="stat-divider"></div>
            <div class="stat-item">
                <span class="stat-value highlight">${stats.applications || 0}</span>
                <span class="stat-label">Applications</span>
            </div>
            <div class="stat-divider"></div>
            <div class="stat-item">
                <span class="stat-value success">${stats.interviews || 0}</span>
                <span class="stat-label">Interviews</span>
            </div>
            <div class="stat-divider"></div>
            <div class="stat-item">
                <span class="stat-value">${stats.response_rate || 0}%</span>
                <span class="stat-label">Response Rate</span>
            </div>
        </div>
    `;
}

/**
 * Job Detail Header Component
 * @param {Object} job - Job object
 * @returns {string} - HTML string
 */
function JobDetailHeader(job) {
    const fitLevel = getFitLevel(job.fit_score);

    let salaryText = '';
    if (job.salary_min || job.salary_max) {
        if (job.salary_min && job.salary_max) {
            salaryText = `$${formatSalary(job.salary_min)} - $${formatSalary(job.salary_max)}`;
        } else if (job.salary_max) {
            salaryText = `Up to $${formatSalary(job.salary_max)}`;
        } else if (job.salary_min) {
            salaryText = `$${formatSalary(job.salary_min)}+`;
        }
    }

    // Get various link sources
    const jobEmail = getJobEmail(job);
    const jobUrl = job.url;
    const company = job.company || {};
    const companyUrl = company.website || company.domain || job.company_url;
    const companyLinkedIn = company.linkedin_url;
    const googleSearchUrl = `https://www.google.com/search?q=${encodeURIComponent(job.title + ' ' + job.company_name + ' jobs')}`;

    return `
        <div class="job-detail-header">
            <h1 class="job-detail-title">${escapeHtml(job.title)}</h1>
            <div class="job-detail-meta">
                <div class="job-detail-meta-item">
                    ${Icons.building}
                    ${escapeHtml(job.company_name)}
                </div>
                <div class="job-detail-meta-item">
                    ${Icons.mapPin}
                    ${escapeHtml(job.location || 'Remote')}
                </div>
                ${salaryText ? `
                    <div class="job-detail-meta-item salary">
                        ${Icons.dollarSign}
                        ${salaryText}
                    </div>
                ` : ''}
                <div class="job-detail-meta-item">
                    ${Icons.clock}
                    Found ${formatDate(job.created_at || job.posted_at)}
                </div>
            </div>

            <div class="job-quick-links">
                ${jobUrl ? `
                    <a href="${escapeHtml(jobUrl)}" target="_blank" class="quick-link primary">
                        ${Icons.externalLink} View Job Posting
                    </a>
                ` : `
                    <a href="${googleSearchUrl}" target="_blank" class="quick-link">
                        ${Icons.search} Search Job on Google
                    </a>
                `}
                ${jobEmail ? `
                    <a href="mailto:${escapeHtml(jobEmail)}?subject=${encodeURIComponent('Application: ' + job.title)}&body=${encodeURIComponent('Hi,\\n\\nI am interested in the ' + job.title + ' position at ' + job.company_name + '.\\n\\nPlease find my resume attached.\\n\\nBest regards')}" class="quick-link accent">
                        ${Icons.mail} ${escapeHtml(jobEmail)}
                    </a>
                ` : ''}
                ${companyUrl ? `
                    <a href="${companyUrl.startsWith('http') ? escapeHtml(companyUrl) : 'https://' + escapeHtml(companyUrl)}" target="_blank" class="quick-link">
                        ${Icons.globe} Company Website
                    </a>
                ` : ''}
                ${companyLinkedIn ? `
                    <a href="${escapeHtml(companyLinkedIn)}" target="_blank" class="quick-link">
                        ${Icons.linkedin} Company LinkedIn
                    </a>
                ` : ''}
            </div>

            <div class="job-detail-actions">
                ${job.status === 'applied' || job.status === 'interviewing' ? `
                    <button class="btn btn-success" disabled>
                        ${Icons.check} Applied
                    </button>
                ` : job.status === 'interested' ? `
                    <button class="btn btn-primary" onclick="startApplication('${job.id}')">
                        ${Icons.send} Start Application
                    </button>
                ` : `
                    <button class="btn btn-secondary" onclick="markInterested('${job.id}')">
                        ${Icons.star} Mark Interested
                    </button>
                    <button class="btn btn-primary" onclick="startApplication('${job.id}')">
                        ${Icons.send} Quick Apply
                    </button>
                `}
                <button class="btn btn-ghost" onclick="dismissJob('${job.id}')">
                    ${Icons.x} Dismiss
                </button>
            </div>
        </div>
    `;
}

/**
 * Get the best email for a job (from raw_data)
 */
function getJobEmail(job) {
    const rawData = job.raw_data || {};
    return rawData.apply_email || rawData.recruiter_email || rawData.careers_email || null;
}

/**
 * Company Info Card Component
 * @param {Object} job - Job object with company info
 * @returns {string} - HTML string
 */
function CompanyInfoCard(job) {
    const company = job.company || {};

    return `
        <div class="company-info-card">
            <div class="company-logo">
                ${company.logo_url ? `
                    <img src="${escapeHtml(company.logo_url)}" alt="${escapeHtml(job.company_name)}">
                ` : getInitials(job.company_name)}
            </div>
            <div class="company-info">
                <div class="company-name">${escapeHtml(job.company_name)}</div>
                <div class="company-details">
                    ${company.industry ? `
                        <span class="company-detail-item">
                            ${Icons.briefcase}
                            ${escapeHtml(company.industry)}
                        </span>
                    ` : ''}
                    ${company.size ? `
                        <span class="company-detail-item">
                            ${Icons.users}
                            ${escapeHtml(company.size)}
                        </span>
                    ` : ''}
                    ${company.website ? `
                        <a href="${escapeHtml(company.website)}" target="_blank" class="company-detail-item">
                            ${Icons.globe}
                            Website
                        </a>
                    ` : ''}
                    ${company.linkedin_url ? `
                        <a href="${escapeHtml(company.linkedin_url)}" target="_blank" class="company-detail-item">
                            ${Icons.linkedin}
                            LinkedIn
                        </a>
                    ` : ''}
                </div>
            </div>
        </div>
    `;
}

/**
 * Format plain text job description to HTML
 * Handles inline bullets (• item1 • item2), section headers, and paragraphs
 * @param {string} text - Plain text description
 * @returns {string} - Formatted HTML
 */
function formatDescription(text) {
    if (!text) return '<p>No description available</p>';

    // Escape HTML entities first
    let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Section header patterns to detect
    const headerKeywords = [
        'about the role', 'about this role', 'about us', 'the role',
        'responsibilities', 'what you will do', 'what you\'ll do',
        'requirements', 'qualifications', 'what we\'re looking for',
        'what you need', 'who you are', 'your background',
        'benefits', 'what we offer', 'perks', 'compensation',
        'preferred qualifications', 'nice to have', 'bonus points',
        'a day in the life', 'here\'s what we offer', 'why join us'
    ];

    // Step 1: Normalize - convert inline bullets to line-based bullets
    // Pattern: "Some text • bullet1 • bullet2" → "Some text\n• bullet1\n• bullet2"
    html = html.replace(/\s*[•●○■]\s*/g, '\n• ');

    // Also handle patterns like "Header: item1, item2" or numbered O items
    html = html.replace(/\s*○\s*/g, '\n• ');

    // Step 2: Split into lines and process
    const lines = html.split('\n');
    const result = [];
    let inList = false;

    for (let line of lines) {
        line = line.trim();
        if (!line) continue;

        // Check if line starts with bullet
        if (line.startsWith('•')) {
            const content = line.substring(1).trim();
            if (content) {
                if (!inList) {
                    result.push('<ul>');
                    inList = true;
                }
                result.push(`<li>${content}</li>`);
            }
            continue;
        }

        // Check if it's a section header
        const lowerLine = line.toLowerCase();
        const isHeader = headerKeywords.some(kw => lowerLine.includes(kw)) ||
            (line.endsWith(':') && line.length < 60) ||
            (line.length < 50 && line === line.toUpperCase() && /[A-Z]{3,}/.test(line));

        if (isHeader) {
            if (inList) {
                result.push('</ul>');
                inList = false;
            }
            result.push(`<h4>${line}</h4>`);
            continue;
        }

        // Regular paragraph - close list if open
        if (inList) {
            result.push('</ul>');
            inList = false;
        }
        result.push(`<p>${line}</p>`);
    }

    // Close any open list
    if (inList) {
        result.push('</ul>');
    }

    return result.join('\n');
}

/**
 * Job Key Info Card - Shows salary, remote type, posted date in a clean grid
 * @param {Object} job - Job object
 * @returns {string} - HTML string
 */
function JobKeyInfo(job) {
    const items = [];

    // Salary
    if (job.salary_min || job.salary_max) {
        let salaryText = '';
        if (job.salary_min && job.salary_max) {
            salaryText = `$${formatSalary(job.salary_min)} - $${formatSalary(job.salary_max)}`;
        } else if (job.salary_max) {
            salaryText = `Up to $${formatSalary(job.salary_max)}`;
        } else {
            salaryText = `$${formatSalary(job.salary_min)}+`;
        }
        items.push({ icon: Icons.dollarSign, label: 'Salary', value: salaryText, type: 'salary' });
    }

    // Remote type
    if (job.remote_type && job.remote_type !== 'unknown') {
        const remoteLabels = { remote: 'Fully Remote', hybrid: 'Hybrid', onsite: 'On-site' };
        items.push({ icon: Icons.globe, label: 'Work Type', value: remoteLabels[job.remote_type] || job.remote_type });
    }

    // Location
    if (job.location) {
        items.push({ icon: Icons.mapPin, label: 'Location', value: job.location });
    }

    // Posted date
    if (job.posted_at) {
        items.push({ icon: Icons.calendar, label: 'Posted', value: formatDate(job.posted_at) });
    }

    // Source
    if (job.source) {
        const sourceLabels = {
            'linkedin': 'LinkedIn', 'indeed': 'Indeed', 'glassdoor': 'Glassdoor',
            'google_jobs': 'Google Jobs', 'grok_search': 'Web Search'
        };
        items.push({ icon: Icons.briefcase, label: 'Source', value: sourceLabels[job.source] || job.source });
    }

    if (items.length === 0) return '';

    return `
        <div class="key-info-card">
            <div class="key-info-grid">
                ${items.map(item => `
                    <div class="key-info-item ${item.type || ''}">
                        <div class="key-info-icon">${item.icon}</div>
                        <div class="key-info-content">
                            <div class="key-info-label">${item.label}</div>
                            <div class="key-info-value">${escapeHtml(item.value)}</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

/**
 * Job Description Component - Collapsible with toggle
 * @param {Object} job - Job object with description
 * @returns {string} - HTML string
 */
function JobDescription(job) {
    const description = job.description || '';
    const jobId = job.id || 'default';

    return `
        <div class="job-description-card">
            <div class="job-description-header" onclick="toggleDescription('desc-${jobId}')">
                <span class="job-description-title">${Icons.fileText} Full Job Description</span>
                <span class="job-description-toggle" id="toggle-desc-${jobId}">${Icons.chevronDown}</span>
            </div>
            <div class="job-description-content collapsed" id="desc-${jobId}">
                ${formatDescription(description)}
            </div>
        </div>
    `;
}

/**
 * Toast Notification Component
 * @param {string} type - Toast type: 'success', 'error', 'warning', 'info'
 * @param {string} title - Toast title
 * @param {string} message - Toast message
 * @returns {string} - HTML string
 */
function Toast(type, title, message) {
    const icons = {
        success: Icons.checkCircle,
        error: Icons.xCircle,
        warning: Icons.alertCircle,
        info: Icons.info
    };

    return `
        <div class="toast ${type}">
            <div class="toast-icon">${icons[type] || icons.info}</div>
            <div class="toast-content">
                <div class="toast-title">${escapeHtml(title)}</div>
                <div class="toast-message">${escapeHtml(message)}</div>
            </div>
            <button class="toast-close" onclick="this.parentElement.remove()">
                ${Icons.x}
            </button>
        </div>
    `;
}

/**
 * Loading Skeleton for Job List
 * @param {number} count - Number of skeletons to render
 * @returns {string} - HTML string
 */
function JobListSkeleton(count = 5) {
    return Array(count).fill(0).map(() => `
        <div class="job-card" style="pointer-events: none;">
            <div class="job-card-header">
                <div class="skeleton skeleton-text" style="width: 70%; height: 18px;"></div>
                <div class="skeleton" style="width: 42px; height: 24px; border-radius: 9999px;"></div>
            </div>
            <div class="skeleton skeleton-text" style="width: 50%;"></div>
            <div class="skeleton skeleton-text" style="width: 40%;"></div>
            <div class="skeleton skeleton-text" style="width: 30%; margin-top: 8px;"></div>
            <div class="job-card-footer" style="margin-top: 12px;">
                <div class="skeleton" style="width: 60px; height: 20px;"></div>
                <div class="skeleton" style="width: 50px; height: 14px;"></div>
            </div>
        </div>
    `).join('');
}

/**
 * Empty State Component
 * @param {string} icon - Icon name
 * @param {string} title - Title text
 * @param {string} description - Description text
 * @param {string} actionHtml - Optional action button HTML
 * @returns {string} - HTML string
 */
function EmptyState(icon, title, description, actionHtml = '') {
    const iconSvg = Icons[icon] || Icons.briefcase;

    return `
        <div class="empty-state">
            <div class="empty-state-icon">${iconSvg}</div>
            <h3 class="empty-state-title">${escapeHtml(title)}</h3>
            <p class="empty-state-description">${escapeHtml(description)}</p>
            ${actionHtml}
        </div>
    `;
}

/**
 * Filter Tabs Component
 * @param {Array} tabs - Array of tab objects
 * @param {string} activeTab - Active tab ID
 * @param {string} filterType - Filter type ('status' or 'category')
 * @returns {string} - HTML string
 */
function FilterTabs(tabs, activeTab, filterType = 'status') {
    return `
        <div class="filter-tabs">
            ${tabs.map(tab => `
                <button class="filter-tab ${tab.id === activeTab ? 'active' : ''}"
                        onclick="onFilterChange('${filterType}', '${tab.id}')">
                    ${escapeHtml(tab.label)}
                    ${tab.count !== undefined ? `<span class="tab-count">${tab.count}</span>` : ''}
                </button>
            `).join('')}
        </div>
    `;
}

/**
 * Modal Component
 * @param {string} id - Modal ID
 * @param {string} title - Modal title
 * @param {string} bodyHtml - Modal body HTML
 * @param {string} footerHtml - Modal footer HTML
 * @param {boolean} fullscreen - Whether modal is fullscreen
 * @returns {string} - HTML string
 */
function Modal(id, title, bodyHtml, footerHtml = '', fullscreen = false) {
    return `
        <div class="modal-overlay" id="${id}">
            <div class="modal ${fullscreen ? 'modal-fullscreen' : ''}">
                <div class="modal-header">
                    <h2 class="modal-title">${escapeHtml(title)}</h2>
                    <button class="modal-close" onclick="closeModal('${id}')">
                        ${Icons.x}
                    </button>
                </div>
                <div class="modal-body">
                    ${bodyHtml}
                </div>
                ${footerHtml ? `
                    <div class="modal-footer">
                        ${footerHtml}
                    </div>
                ` : ''}
            </div>
        </div>
    `;
}

// Export components for use in other files
if (typeof window !== 'undefined') {
    window.Components = {
        Icons,
        JobCard,
        FitAnalysis,
        RequirementsChecklist,
        ApplicationTimeline,
        CoverLetterEditor,
        ContactSelection,
        EmailPreview,
        StatsBar,
        JobDetailHeader,
        CompanyInfoCard,
        JobKeyInfo,
        JobDescription,
        Toast,
        JobListSkeleton,
        EmptyState,
        FilterTabs,
        Modal
    };

    // Toggle function for collapsible description
    window.toggleDescription = function(id) {
        const content = document.getElementById(id);
        const toggle = document.getElementById('toggle-' + id);
        if (content) {
            content.classList.toggle('collapsed');
            if (toggle) {
                toggle.innerHTML = content.classList.contains('collapsed') ? Icons.chevronDown : Icons.chevronUp;
            }
        }
    };

    window.Utils = {
        getFitLevel,
        formatSalary,
        formatDate,
        formatDateTime,
        escapeHtml,
        truncateText,
        getInitials
    };
}
