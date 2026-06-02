/**
 * JobHunt - Main Application Logic
 * Vanilla JavaScript application for the job search dashboard
 */

// ==================== APPLICATION STATE ====================
const state = {
    // Jobs data
    jobs: [],
    selectedJob: null,
    filteredJobs: [],

    // Applications
    applications: [],
    currentApplication: null,

    // Filters
    filters: {
        status: 'all',
        category: 'all',
        search: ''
    },

    // Stats
    stats: {
        total_jobs: 0,
        applications: 0,
        interviews: 0,
        response_rate: 0,
        new_count: 0,
        interested_count: 0,
        applied_count: 0,
        interviewing_count: 0
    },

    // UI State
    isLoading: false,
    error: null,

    // Application draft
    applicationDraft: {
        coverLetter: '',
        selectedContact: null,
        lastSaved: null
    },

    // Settings
    settings: {
        theme: localStorage.getItem('theme') || 'dark',
        notifications: true
    }
};

// Make state globally accessible
window.state = state;

// ==================== API CONFIGURATION ====================
// Relative base works for local dev and behind any reverse proxy.
// To use an absolute URL, set window.JOBHUNT_API_BASE before this script loads.
const API_BASE = window.JOBHUNT_API_BASE || '/api';

// Make API_BASE globally accessible for inline scripts
window.API_BASE = API_BASE;

// ==================== API CALLS ====================

/**
 * Make an API request
 * @param {string} endpoint - API endpoint
 * @param {Object} options - Fetch options
 * @returns {Promise<Object>} - Response data
 */
async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;

    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
    };

    const mergedOptions = { ...defaultOptions, ...options };

    try {
        const response = await fetch(url, mergedOptions);

        if (!response.ok) {
            const error = await response.json().catch(() => ({ message: 'Request failed' }));
            throw new Error(error.message || `HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error(`API Error [${endpoint}]:`, error);
        throw error;
    }
}

/**
 * Fetch jobs with optional filters
 * @param {Object} filters - Filter options
 * @returns {Promise<Array>} - Array of jobs
 */
async function fetchJobs(filters = {}) {
    const params = new URLSearchParams();

    if (filters.status && filters.status !== 'all') {
        params.append('status', filters.status);
    }
    if (filters.search) {
        params.append('search', filters.search);
    }

    const queryString = params.toString();
    const endpoint = `/jobs/${queryString ? `?${queryString}` : ''}`;

    return await apiRequest(endpoint);
}

/**
 * Fetch a single job's details
 * @param {string} jobId - Job ID
 * @returns {Promise<Object>} - Job details
 */
async function fetchJobDetail(jobId) {
    return await apiRequest(`/jobs/${jobId}`);
}

/**
 * Mark a job as interested
 * @param {string} jobId - Job ID
 * @returns {Promise<Object>} - Updated job
 */
async function markInterested(jobId) {
    const response = await apiRequest(`/jobs/${jobId}/interested`, {
        method: 'POST'
    });

    showToast('success', 'Job Marked', 'Added to your interested list');
    await refreshJobs();

    return response;
}

/**
 * Start an application for a job
 * @param {string} jobId - Job ID
 * @returns {Promise<Object>} - Application draft
 */
async function startApplication(jobId) {
    try {
        const response = await apiRequest(`/workflows/apply/${jobId}`, {
            method: 'POST'
        });

        state.currentApplication = response;
        state.applicationDraft = {
            coverLetter: response.cover_letter || '',
            selectedContact: response.contacts?.[0]?.id || null,
            lastSaved: new Date()
        };

        renderApplicationPanel();
        showToast('success', 'Application Started', 'Complete your cover letter and send');

        return response;
    } catch (error) {
        showToast('error', 'Error', 'Failed to start application');
        throw error;
    }
}

/**
 * Approve and send an application
 * @param {string} jobId - Job ID
 * @param {Object} edits - Application edits
 * @returns {Promise<Object>} - Sent application
 */
async function approveApplication(jobId, edits = {}) {
    try {
        const response = await apiRequest(`/workflows/apply/${jobId}/approve`, {
            method: 'POST',
            body: JSON.stringify({
                cover_letter: state.applicationDraft.coverLetter,
                contact_id: state.applicationDraft.selectedContact,
                ...edits
            })
        });

        showToast('success', 'Application Sent!', 'Your application has been submitted');
        await refreshJobs();

        // Clear application draft
        state.currentApplication = null;
        state.applicationDraft = {
            coverLetter: '',
            selectedContact: null,
            lastSaved: null
        };

        renderApplicationPanel();

        return response;
    } catch (error) {
        showToast('error', 'Error', 'Failed to send application');
        throw error;
    }
}

/**
 * Run job discovery using uploaded resume
 * @returns {Promise<Object>} - Discovery result
 */
async function runDiscovery() {
    try {
        setLoadingState(true);
        showToast('info', 'Discovery Started', 'Analyzing resume and searching for matching jobs...');

        // Use resume-driven discovery - analyzes your resume to find matching jobs
        const response = await apiRequest('/workflows/discover-from-resume', {
            method: 'POST'
        });

        // Show the workflow message (includes resume name)
        showToast('success', 'Discovery Started', response.message || 'Finding jobs based on your resume...');

        // Poll for jobs since workflow runs async
        setTimeout(async () => {
            await refreshJobs();
        }, 3000);

        return response;
    } catch (error) {
        showToast('error', 'Discovery Failed', error.message);
        throw error;
    } finally {
        setLoadingState(false);
    }
}

/**
 * Fetch dashboard stats
 * @returns {Promise<Object>} - Stats object
 */
async function fetchStats() {
    try {
        const response = await apiRequest('/dashboard/stats');
        state.stats = { ...state.stats, ...response };
        renderStats();
        return response;
    } catch (error) {
        console.error('Failed to fetch stats:', error);
        // Use mock data for development
        state.stats = {
            total_jobs: state.jobs.length,
            applications: state.jobs.filter(j => j.status === 'applied').length,
            interviews: state.jobs.filter(j => j.status === 'interviewing').length,
            response_rate: 0,
            new_count: state.jobs.filter(j => j.status === 'new').length,
            interested_count: state.jobs.filter(j => j.status === 'interested').length,
            applied_count: state.jobs.filter(j => j.status === 'applied').length,
            interviewing_count: state.jobs.filter(j => j.status === 'interviewing').length
        };
        renderStats();
        return state.stats;
    }
}

/**
 * Toggle star status for a job
 * @param {string} jobId - Job ID
 */
async function toggleStar(jobId) {
    try {
        const job = state.jobs.find(j => j.id === jobId);
        if (!job) return;

        await apiRequest(`/jobs/${jobId}/star`, {
            method: 'POST',
            body: JSON.stringify({ starred: !job.is_starred })
        });

        job.is_starred = !job.is_starred;
        renderJobList();
    } catch (error) {
        // Toggle locally even if API fails
        const job = state.jobs.find(j => j.id === jobId);
        if (job) {
            job.is_starred = !job.is_starred;
            renderJobList();
        }
    }
}

/**
 * Dismiss a job
 * @param {string} jobId - Job ID
 */
async function dismissJob(jobId) {
    try {
        await apiRequest(`/jobs/${jobId}/dismiss`, {
            method: 'POST'
        });

        // Remove from local state
        state.jobs = state.jobs.filter(j => j.id !== jobId);
        state.filteredJobs = state.filteredJobs.filter(j => j.id !== jobId);

        if (state.selectedJob?.id === jobId) {
            state.selectedJob = state.filteredJobs[0] || null;
        }

        renderJobList();
        renderJobDetail();
        fetchStats();

        showToast('info', 'Job Dismissed', 'Removed from your list');
    } catch (error) {
        showToast('error', 'Error', 'Failed to dismiss job');
    }
}

/**
 * Generate a cover letter with AI
 */
async function generateCoverLetter() {
    if (!state.selectedJob) {
        showToast('error', 'Error', 'Please select a job first');
        return;
    }

    try {
        showToast('info', 'Generating...', 'Creating your personalized cover letter');

        const response = await apiRequest(`/jobs/${state.selectedJob.id}/generate-cover-letter`, {
            method: 'POST'
        });

        state.applicationDraft.coverLetter = response.cover_letter;
        state.applicationDraft.lastSaved = new Date();

        const textarea = document.getElementById('cover-letter-textarea');
        if (textarea) {
            textarea.value = response.cover_letter;
        }

        renderApplicationPanel();
        showToast('success', 'Generated!', 'Cover letter created successfully');
    } catch (error) {
        showToast('error', 'Error', 'Failed to generate cover letter');
    }
}

// ==================== UI RENDERING ====================

/**
 * Render the stats bar
 */
function renderStats() {
    const statsContainer = document.getElementById('stats-bar');
    if (!statsContainer) return;

    statsContainer.innerHTML = Components.StatsBar(state.stats);
}

/**
 * Render the job list
 */
function renderJobList() {
    const container = document.getElementById('job-list');
    if (!container) return;

    // Apply filters
    applyFilters();

    if (state.isLoading) {
        container.innerHTML = Components.JobListSkeleton(5);
        return;
    }

    if (state.filteredJobs.length === 0) {
        container.innerHTML = Components.EmptyState(
            'briefcase',
            'No Jobs Found',
            state.filters.search
                ? 'Try adjusting your search terms'
                : 'Run discovery to find new opportunities',
            `<button class="btn btn-primary" onclick="runDiscovery()">
                ${Components.Icons.play} Run Discovery
            </button>`
        );
        return;
    }

    container.innerHTML = `
        <div class="job-list">
            ${state.filteredJobs.map(job => Components.JobCard(job)).join('')}
        </div>
    `;

    // Update job count
    const countEl = document.getElementById('job-count');
    if (countEl) {
        countEl.textContent = state.filteredJobs.length;
    }
}

/**
 * Render the job detail panel
 * @param {Object} job - Optional job to render
 */
function renderJobDetail(job = null) {
    const container = document.getElementById('job-detail');
    if (!container) return;

    const jobToRender = job || state.selectedJob;

    if (!jobToRender) {
        container.innerHTML = `
            <div class="job-detail-empty">
                ${Components.Icons.briefcase}
                <h3>Select a Job</h3>
                <p>Choose a job from the list to view details and apply</p>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        ${Components.JobDetailHeader(jobToRender)}
        <div class="job-detail-body">
            ${Components.JobKeyInfo(jobToRender)}
            ${Components.FitAnalysis(jobToRender)}
            ${Components.CompanyInfoCard(jobToRender)}
            ${Components.JobDescription(jobToRender)}
        </div>
    `;
}

/**
 * Render the application panel
 */
function renderApplicationPanel() {
    const container = document.getElementById('application-panel');
    if (!container) return;

    if (!state.selectedJob) {
        container.innerHTML = `
            <div class="application-empty">
                ${Components.Icons.send}
                <h3>Ready to Apply?</h3>
                <p>Select a job to start your application</p>
            </div>
        `;
        return;
    }

    const job = state.selectedJob;
    const hasApplied = job.status === 'applied' || job.status === 'interviewing';

    if (hasApplied) {
        // Show application timeline
        const application = state.currentApplication || {
            events: [
                {
                    title: 'Application Submitted',
                    date: job.applied_at || new Date(),
                    completed: true,
                    description: 'Your application was successfully sent'
                },
                ...(job.status === 'interviewing' ? [{
                    title: 'Interview Scheduled',
                    date: job.interview_date || new Date(),
                    completed: false,
                    description: 'Upcoming interview'
                }] : [])
            ]
        };

        container.innerHTML = `
            <div class="panel-header">
                <span class="panel-title">Application Status</span>
            </div>
            <div class="panel-body">
                <div class="form-section">
                    <div class="form-section-title">
                        ${Components.Icons.clock}
                        Timeline
                    </div>
                    ${Components.ApplicationTimeline(application)}
                </div>
            </div>
        `;
    } else {
        // Show application form
        const contacts = state.currentApplication?.contacts || [];
        const emailPreview = state.applicationDraft.selectedContact && state.applicationDraft.coverLetter ? {
            to: contacts.find(c => c.id === state.applicationDraft.selectedContact)?.email || '',
            subject: `Application for ${job.title} at ${job.company_name}`,
            body: state.applicationDraft.coverLetter
        } : null;

        container.innerHTML = `
            <div class="panel-header">
                <span class="panel-title">Apply to ${Utils.truncateText(job.company_name, 20)}</span>
            </div>
            <div class="panel-body">
                <div class="application-form">
                    <div class="form-section">
                        <div class="form-section-title">
                            ${Components.Icons.fileText}
                            Cover Letter
                        </div>
                        ${Components.CoverLetterEditor({
                            content: state.applicationDraft.coverLetter,
                            lastSaved: state.applicationDraft.lastSaved
                        })}
                    </div>

                    ${contacts.length > 0 ? `
                        <div class="form-section">
                            <div class="form-section-title">
                                ${Components.Icons.user}
                                Select Contact
                            </div>
                            ${Components.ContactSelection(contacts, state.applicationDraft.selectedContact)}
                        </div>
                    ` : ''}

                    ${emailPreview ? `
                        <div class="form-section">
                            <div class="form-section-title">
                                ${Components.Icons.mail}
                                Email Preview
                            </div>
                            ${Components.EmailPreview(emailPreview)}
                        </div>
                    ` : ''}

                    <div class="form-section" style="padding-top: 16px; border-top: 1px solid var(--border-color);">
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-success" style="flex: 1;"
                                    onclick="approveApplication('${job.id}')"
                                    ${!state.applicationDraft.coverLetter ? 'disabled' : ''}>
                                ${Components.Icons.send} Send Application
                            </button>
                            <button class="btn btn-secondary"
                                    onclick="cancelApplication()">
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
}

/**
 * Render filter tabs (status + category)
 */
function renderFilterTabs() {
    const container = document.getElementById('filter-tabs');
    if (!container) return;

    // Status tabs
    const statusTabs = [
        { id: 'all', label: 'All', count: state.jobs.length },
        { id: 'new', label: 'New', count: state.stats.new_count },
        { id: 'interested', label: 'Interested', count: state.stats.interested_count },
        { id: 'applied', label: 'Applied', count: state.stats.applied_count },
        { id: 'interviewing', label: 'Interviewing', count: state.stats.interviewing_count }
    ];

    // Category counts from jobs
    const categoryCounts = {};
    state.jobs.forEach(job => {
        const cat = job.category || 'other';
        categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
    });

    // Category tabs (only show categories that have jobs)
    const categoryLabels = {
        'all': 'All Types',
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

    const categoryTabs = [{ id: 'all', label: 'All Types', count: state.jobs.length }];
    Object.entries(categoryCounts).forEach(([cat, count]) => {
        if (count > 0 && categoryLabels[cat]) {
            categoryTabs.push({ id: cat, label: categoryLabels[cat], count });
        }
    });

    container.innerHTML = `
        <div class="filter-section">
            ${Components.FilterTabs(statusTabs, state.filters.status)}
        </div>
        <div class="filter-section category-tabs" style="margin-top: 8px;">
            ${Components.FilterTabs(categoryTabs, state.filters.category, 'category')}
        </div>
    `;
}

// ==================== EVENT HANDLERS ====================

/**
 * Handle job selection
 * @param {string} jobId - Job ID
 */
async function onJobSelect(jobId) {
    // Update selection in list
    document.querySelectorAll('.job-card').forEach(card => {
        card.classList.remove('selected');
    });

    const selectedCard = document.querySelector(`[data-job-id="${jobId}"]`);
    if (selectedCard) {
        selectedCard.classList.add('selected');
    }

    // Find job in state or fetch details
    let job = state.jobs.find(j => j.id === jobId);

    if (job) {
        // If we have basic info, fetch full details
        try {
            const details = await fetchJobDetail(jobId);
            job = { ...job, ...details };

            // Update in state
            const index = state.jobs.findIndex(j => j.id === jobId);
            if (index >= 0) {
                state.jobs[index] = job;
            }
        } catch (error) {
            console.warn('Failed to fetch job details, using cached data');
        }
    }

    state.selectedJob = job;

    // Reset application draft if different job
    if (state.currentApplication?.job_id !== jobId) {
        state.currentApplication = null;
        state.applicationDraft = {
            coverLetter: '',
            selectedContact: null,
            lastSaved: null
        };
    }

    renderJobDetail(job);
    renderApplicationPanel();

    // On mobile, show detail panel
    if (window.innerWidth <= 768) {
        document.querySelector('.job-detail-panel')?.classList.add('mobile-visible');
    }
}

/**
 * Handle filter change
 * @param {string} filterType - Filter type
 * @param {string} value - Filter value
 */
function onFilterChange(filterType, value) {
    state.filters[filterType] = value;
    renderFilterTabs();
    renderJobList();
}

/**
 * Handle search input
 * @param {string} value - Search query
 */
function onSearchChange(value) {
    state.filters.search = value;

    // Debounce search
    clearTimeout(window.searchTimeout);
    window.searchTimeout = setTimeout(() => {
        renderJobList();
    }, 300);
}

/**
 * Update cover letter draft
 * @param {string} value - Cover letter content
 */
function updateCoverLetterDraft(value) {
    state.applicationDraft.coverLetter = value;
    state.applicationDraft.lastSaved = new Date();
}

/**
 * Select a contact for application
 * @param {string} contactId - Contact ID
 */
function selectContact(contactId) {
    state.applicationDraft.selectedContact = contactId;
    renderApplicationPanel();
}

/**
 * Cancel current application
 */
function cancelApplication() {
    state.currentApplication = null;
    state.applicationDraft = {
        coverLetter: '',
        selectedContact: null,
        lastSaved: null
    };
    renderApplicationPanel();
}

/**
 * Copy cover letter to clipboard
 */
function copyCoverLetter() {
    const text = state.applicationDraft.coverLetter;
    navigator.clipboard.writeText(text).then(() => {
        showToast('success', 'Copied!', 'Cover letter copied to clipboard');
    });
}

/**
 * Open cover letter modal for full-screen editing
 */
function openCoverLetterModal() {
    const modalHtml = Components.Modal(
        'cover-letter-modal',
        'Edit Cover Letter',
        `
            <textarea class="cover-letter-textarea" style="min-height: 400px;"
                      oninput="updateCoverLetterDraft(this.value)">${Utils.escapeHtml(state.applicationDraft.coverLetter)}</textarea>
        `,
        `
            <button class="btn btn-secondary" onclick="closeModal('cover-letter-modal')">Cancel</button>
            <button class="btn btn-primary" onclick="saveCoverLetterModal()">Save</button>
        `,
        true
    );

    // Add modal to DOM
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    openModal('cover-letter-modal');
}

/**
 * Save and close cover letter modal
 */
function saveCoverLetterModal() {
    const textarea = document.querySelector('#cover-letter-modal textarea');
    if (textarea) {
        state.applicationDraft.coverLetter = textarea.value;
        state.applicationDraft.lastSaved = new Date();
    }
    closeModal('cover-letter-modal');
    renderApplicationPanel();
}

// ==================== MODAL HELPERS ====================

/**
 * Open a modal
 * @param {string} modalId - Modal ID
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
    }
}

/**
 * Close a modal
 * @param {string} modalId - Modal ID
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('open');
        document.body.style.overflow = '';

        // Remove dynamically created modals
        if (modal.dataset.dynamic) {
            setTimeout(() => modal.remove(), 300);
        }
    }
}

// ==================== TOAST NOTIFICATIONS ====================

/**
 * Show a toast notification
 * @param {string} type - Toast type
 * @param {string} title - Toast title
 * @param {string} message - Toast message
 * @param {number} duration - Duration in ms
 */
function showToast(type, title, message, duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toastHtml = Components.Toast(type, title, message);

    // Create toast element
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = toastHtml;
    const toast = tempDiv.firstElementChild;

    container.appendChild(toast);

    // Auto-remove after duration
    setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ==================== UTILITY FUNCTIONS ====================

/**
 * Apply current filters to jobs
 */
function applyFilters() {
    let filtered = [...state.jobs];

    // Filter by status
    if (state.filters.status && state.filters.status !== 'all') {
        filtered = filtered.filter(job => job.status === state.filters.status);
    }

    // Filter by category
    if (state.filters.category && state.filters.category !== 'all') {
        filtered = filtered.filter(job => {
            const jobCategory = job.category || 'other';
            return jobCategory === state.filters.category;
        });
    }

    // Filter by search
    if (state.filters.search) {
        const search = state.filters.search.toLowerCase();
        filtered = filtered.filter(job =>
            job.title?.toLowerCase().includes(search) ||
            job.company_name?.toLowerCase().includes(search) ||
            job.location?.toLowerCase().includes(search)
        );
    }

    state.filteredJobs = filtered;
}

/**
 * Refresh jobs from API
 */
async function refreshJobs() {
    try {
        const response = await fetchJobs();
        state.jobs = response.jobs || [];
        applyFilters();
        renderJobList();
        await fetchStats();
    } catch (error) {
        console.error('Failed to refresh jobs:', error);
    }
}

/**
 * Set loading state
 * @param {boolean} isLoading - Loading state
 */
function setLoadingState(isLoading) {
    state.isLoading = isLoading;
    renderJobList();
}

/**
 * Toggle theme
 */
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    state.settings.theme = newTheme;
}

/**
 * Open settings modal
 */
function openSettings() {
    const modalHtml = Components.Modal(
        'settings-modal',
        'Settings',
        `
            <div class="form-group">
                <label class="form-label">Theme</label>
                <select class="form-select" onchange="toggleTheme()">
                    <option value="dark" ${state.settings.theme === 'dark' ? 'selected' : ''}>Dark</option>
                    <option value="light" ${state.settings.theme === 'light' ? 'selected' : ''}>Light</option>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">Search Configurations</label>
                <p class="text-secondary" style="font-size: 0.875rem;">
                    Configure your job search criteria, keywords, and preferred companies.
                </p>
                <button class="btn btn-secondary mt-sm" onclick="openSearchConfig()">
                    ${Components.Icons.settings} Manage Search Config
                </button>
            </div>
        `,
        `
            <button class="btn btn-primary" onclick="closeModal('settings-modal')">Done</button>
        `
    );

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    document.getElementById('settings-modal').dataset.dynamic = 'true';
    openModal('settings-modal');
}

/**
 * Open search configuration
 */
function openSearchConfig() {
    closeModal('settings-modal');
    showToast('info', 'Coming Soon', 'Search configuration will be available in a future update');
}

/**
 * Go back on mobile
 */
function goBack() {
    document.querySelector('.job-detail-panel')?.classList.remove('mobile-visible');
    document.querySelector('.application-panel')?.classList.remove('mobile-visible');
}

// ==================== INITIALIZATION ====================

/**
 * Initialize the application
 */
async function init() {
    console.log('JobHunt initializing...');

    // Set initial theme
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    state.settings.theme = savedTheme;

    // Set up event listeners
    setupEventListeners();

    // Show loading state
    setLoadingState(true);

    try {
        // Fetch initial data
        const response = await fetchJobs();
        state.jobs = response.jobs || [];
        applyFilters();

        // Fetch stats
        await fetchStats();

        // Render UI
        renderFilterTabs();
        renderJobList();
        renderJobDetail();
        renderApplicationPanel();

        // Select first job if available
        if (state.filteredJobs.length > 0 && window.innerWidth > 768) {
            onJobSelect(state.filteredJobs[0].id);
        }

        console.log('JobHunt initialized successfully');
    } catch (error) {
        console.error('Failed to initialize:', error);
        showToast('error', 'Connection Error', 'Unable to connect to server. Using demo mode.');

        // Load mock data for demo
        loadMockData();
    } finally {
        setLoadingState(false);
    }
}

/**
 * Set up event listeners
 */
function setupEventListeners() {
    // Search input
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => onSearchChange(e.target.value));
    }

    // Search clear button
    const searchClear = document.getElementById('search-clear');
    if (searchClear) {
        searchClear.addEventListener('click', () => {
            const input = document.getElementById('search-input');
            if (input) {
                input.value = '';
                onSearchChange('');
            }
        });
    }

    // Close modals on backdrop click
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal-overlay')) {
            const modalId = e.target.id;
            closeModal(modalId);
        }
    });

    // Close modals on escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const openModal = document.querySelector('.modal-overlay.open');
            if (openModal) {
                closeModal(openModal.id);
            }
        }
    });

    // Handle resize
    window.addEventListener('resize', () => {
        if (window.innerWidth > 768) {
            document.querySelector('.job-detail-panel')?.classList.remove('mobile-visible');
            document.querySelector('.application-panel')?.classList.remove('mobile-visible');
        }
    });
}

/**
 * Load mock data for demo/development
 */
function loadMockData() {
    state.jobs = [
        {
            id: 'job-1',
            title: 'Senior Software Engineer',
            company_name: 'TechCorp',
            location: 'San Francisco, CA',
            salary_min: 180000,
            salary_max: 220000,
            fit_score: 0.92,
            status: 'new',
            source: 'LinkedIn',
            posted_at: new Date(Date.now() - 86400000).toISOString(),
            description: '<h3>About the Role</h3><p>We are looking for a Senior Software Engineer to join our growing team.</p><h3>Requirements</h3><ul><li>5+ years of experience</li><li>Strong TypeScript skills</li><li>Experience with React</li></ul>',
            matched_skills: ['TypeScript', 'React', 'Node.js', 'PostgreSQL'],
            missing_skills: ['Kubernetes'],
            requirements: [
                { text: '5+ years of software engineering experience', met: true },
                { text: 'Strong TypeScript/JavaScript skills', met: true },
                { text: 'Experience with React or Vue', met: true },
                { text: 'Kubernetes experience preferred', met: false, partial: true }
            ]
        },
        {
            id: 'job-2',
            title: 'Full Stack Developer',
            company_name: 'StartupXYZ',
            location: 'Remote',
            salary_min: 140000,
            salary_max: 170000,
            fit_score: 0.85,
            status: 'interested',
            source: 'Indeed',
            posted_at: new Date(Date.now() - 172800000).toISOString(),
            description: '<p>Join our fast-paced startup as a Full Stack Developer.</p>',
            matched_skills: ['JavaScript', 'Python', 'React'],
            missing_skills: ['Go', 'AWS'],
            requirements: [
                { text: '3+ years of full stack development', met: true },
                { text: 'Experience with Python backend', met: true },
                { text: 'AWS or GCP experience', met: false }
            ]
        },
        {
            id: 'job-3',
            title: 'Frontend Engineer',
            company_name: 'DesignCo',
            location: 'New York, NY',
            salary_min: 150000,
            salary_max: 180000,
            fit_score: 0.78,
            status: 'applied',
            source: 'LinkedIn',
            posted_at: new Date(Date.now() - 604800000).toISOString(),
            applied_at: new Date(Date.now() - 86400000).toISOString(),
            description: '<p>We need a creative Frontend Engineer to build beautiful interfaces.</p>',
            matched_skills: ['React', 'CSS', 'TypeScript'],
            missing_skills: ['Figma', 'Animation'],
            requirements: [
                { text: 'Strong React experience', met: true },
                { text: 'Eye for design and UX', met: true, partial: true }
            ]
        },
        {
            id: 'job-4',
            title: 'Backend Engineer',
            company_name: 'DataFlow Inc',
            location: 'Austin, TX',
            salary_min: 160000,
            salary_max: 200000,
            fit_score: 0.65,
            status: 'new',
            source: 'Hired',
            posted_at: new Date(Date.now() - 259200000).toISOString(),
            description: '<p>Build scalable backend systems for our data platform.</p>',
            matched_skills: ['Python', 'PostgreSQL'],
            missing_skills: ['Kafka', 'Spark', 'Scala'],
            requirements: [
                { text: 'Experience with distributed systems', met: false, partial: true },
                { text: 'Strong SQL skills', met: true },
                { text: 'Apache Kafka experience', met: false }
            ]
        },
        {
            id: 'job-5',
            title: 'Platform Engineer',
            company_name: 'CloudNative Co',
            location: 'Seattle, WA',
            salary_max: 250000,
            fit_score: 0.45,
            status: 'new',
            source: 'AngelList',
            posted_at: new Date(Date.now() - 432000000).toISOString(),
            description: '<p>Help us build our cloud infrastructure platform.</p>',
            matched_skills: ['Docker'],
            missing_skills: ['Kubernetes', 'Terraform', 'AWS', 'GCP'],
            requirements: [
                { text: 'Deep Kubernetes expertise', met: false },
                { text: 'Infrastructure as Code (Terraform)', met: false },
                { text: 'Cloud platform experience (AWS/GCP)', met: false }
            ]
        }
    ];

    applyFilters();
    renderFilterTabs();
    renderJobList();

    // Update stats based on mock data
    state.stats = {
        total_jobs: state.jobs.length,
        applications: state.jobs.filter(j => j.status === 'applied').length,
        interviews: state.jobs.filter(j => j.status === 'interviewing').length,
        response_rate: 33,
        new_count: state.jobs.filter(j => j.status === 'new').length,
        interested_count: state.jobs.filter(j => j.status === 'interested').length,
        applied_count: state.jobs.filter(j => j.status === 'applied').length,
        interviewing_count: state.jobs.filter(j => j.status === 'interviewing').length
    };
    renderStats();
}

// Make functions globally accessible
window.onJobSelect = onJobSelect;
window.onFilterChange = onFilterChange;
window.onSearchChange = onSearchChange;
window.toggleStar = toggleStar;
window.dismissJob = dismissJob;
window.markInterested = markInterested;
window.startApplication = startApplication;
window.approveApplication = approveApplication;
window.runDiscovery = runDiscovery;
window.generateCoverLetter = generateCoverLetter;
window.updateCoverLetterDraft = updateCoverLetterDraft;
window.selectContact = selectContact;
window.cancelApplication = cancelApplication;
window.copyCoverLetter = copyCoverLetter;
window.openCoverLetterModal = openCoverLetterModal;
window.saveCoverLetterModal = saveCoverLetterModal;
window.openModal = openModal;
window.closeModal = closeModal;
window.showToast = showToast;
window.toggleTheme = toggleTheme;
window.openSettings = openSettings;
window.goBack = goBack;

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
