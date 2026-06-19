// ── Company registry — logos via Clearbit CDN (free, no auth) ────────
const COMPANY_REGISTRY = {
  // ── Active (local images) ──────────────────────────────────────────
  'Trinity Life Sciences':  { abbr: 'TL', color: '#1B4FD8', image: 'assets/images/companies/trinity.jpg' },
  'Jupiter Medical':        { abbr: 'JM', color: '#0891B2', image: 'assets/images/companies/jupitermedicals.jpg' },

  // ── Technology & Software ──────────────────────────────────────────
  'Workday':                { abbr: 'WD', color: '#F97316', image: 'https://logo.clearbit.com/workday.com' },
  'Salesforce':             { abbr: 'SF', color: '#00A1E0', image: 'https://logo.clearbit.com/salesforce.com' },
  'NVIDIA':                 { abbr: 'NV', color: '#76B900', image: 'https://logo.clearbit.com/nvidia.com' },
  'Motorola Solutions':     { abbr: 'MS', color: '#005A9B', image: 'https://logo.clearbit.com/motorolasolutions.com' },
  'Mastercard':             { abbr: 'MC', color: '#EB001B', image: 'https://logo.clearbit.com/mastercard.com' },
  'Gen (Norton / Avast)':   { abbr: 'GN', color: '#FFB300', image: 'https://logo.clearbit.com/gendigital.com' },
  'Concentrix':             { abbr: 'CX', color: '#7C3AED', image: 'https://logo.clearbit.com/concentrix.com' },

  // ── Financial Services ─────────────────────────────────────────────
  'BlackRock':              { abbr: 'BR', color: '#000000', image: 'https://logo.clearbit.com/blackrock.com' },
  'Morgan Stanley':         { abbr: 'MO', color: '#003087', image: 'https://logo.clearbit.com/morganstanley.com' },
  'Fidelity Investments':   { abbr: 'FI', color: '#007A33', image: 'https://logo.clearbit.com/fidelity.com' },
  'DWS Group':              { abbr: 'DW', color: '#0033A0', image: 'https://logo.clearbit.com/dws.com' },

  // ── Pharma, Biotech & Healthcare ───────────────────────────────────
  'Pfizer':                 { abbr: 'PF', color: '#003B7E', image: 'https://logo.clearbit.com/pfizer.com' },
  'Abbott':                 { abbr: 'AB', color: '#0079C1', image: 'https://logo.clearbit.com/abbott.com' },
  'Merck (MSD)':            { abbr: 'MK', color: '#009B77', image: 'https://logo.clearbit.com/merck.com' },
  'Sanofi':                 { abbr: 'SN', color: '#7A2082', image: 'https://logo.clearbit.com/sanofi.com' },

  // ── Retail & Consumer ──────────────────────────────────────────────
  'Walmart':                { abbr: 'WM', color: '#0071CE', image: 'https://logo.clearbit.com/walmart.com' },
  'Target':                 { abbr: 'TG', color: '#CC0000', image: 'https://logo.clearbit.com/target.com' },
  'Nordstrom':              { abbr: 'NO', color: '#1A1A1A', image: 'https://logo.clearbit.com/nordstrom.com' },

  // ── Aerospace, Defense & Engineering ──────────────────────────────
  'GE Aerospace':           { abbr: 'GE', color: '#004B87', image: 'https://logo.clearbit.com/geaerospace.com' },
  'CAE':                    { abbr: 'CA', color: '#003C71', image: 'https://logo.clearbit.com/cae.com' },
  'Austal USA':             { abbr: 'AU', color: '#002855', image: 'https://logo.clearbit.com/austal.com' },

  // ── Telecom ────────────────────────────────────────────────────────
  'AT&T':                   { abbr: 'AT', color: '#00A8E0', image: 'https://logo.clearbit.com/att.com' },

  // ── Professional Services & Other ─────────────────────────────────
  'Thomson Reuters':        { abbr: 'TR', color: '#FF6200', image: 'https://logo.clearbit.com/thomsonreuters.com' },
  'Wolters Kluwer':         { abbr: 'WK', color: '#007AC9', image: 'https://logo.clearbit.com/wolterskluwer.com' },
  'ASM Global':             { abbr: 'AG', color: '#C8102E', image: 'https://logo.clearbit.com/asmglobal.com' },
  'Acciona':                { abbr: 'AC', color: '#00A650', image: 'https://logo.clearbit.com/acciona.com' },
  'World Economic Forum':   { abbr: 'WE', color: '#003C71', image: 'https://logo.clearbit.com/weforum.org' },
  'Jotun':                  { abbr: 'JO', color: '#E4002B', image: 'https://logo.clearbit.com/jotun.com' },
};

const CATEGORIES = [
  'Engineering', 'Data Science', 'Analytics', 'Cloud',
  'AI / ML', 'Cybersecurity', 'Product', 'Consulting',
  'DevOps', 'Architecture', 'Data Engineering', 'QA',
];

const JOBS_PER_PAGE = 30;
const EXPIRY_DAYS   = 30;   // default if company provides no end date
const WARN_DAYS     = 7;    // show "X days left" badge within this window
const URGENT_DAYS   = 3;    // switch badge to red

let allJobs       = [];
let freshJobs     = [];   // not yet expired
let archivedJobs  = [];   // expired
let filteredJobs  = [];   // fresh after filters
let filteredPast  = [];   // archived after filters
let currentPage     = 1;
let currentPagePast = 1;
let activeChip    = null;
let pastExpanded  = false;

// ── Expiry helpers ────────────────────────────────────────────────────
function getExpiryDate(job) {
  // 1. Company-provided end date (most accurate)
  if (job.end_date) {
    try { return new Date(job.end_date + 'T23:59:59'); } catch {}
  }
  // 2. start_date + EXPIRY_DAYS
  if (job.start_date) {
    try {
      const d = new Date(job.start_date + 'T00:00:00');
      d.setDate(d.getDate() + EXPIRY_DAYS);
      return d;
    } catch {}
  }
  // 3. Parse relative posted_date string
  const raw = (job.posted_date || '').toLowerCase();
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let daysAgo = 0;
  if (raw.includes('today'))     daysAgo = 0;
  else if (raw.includes('yesterday')) daysAgo = 1;
  else {
    const dm = raw.match(/(\d+)\+?\s*day/);   if (dm) daysAgo = +dm[1];
    const wm = raw.match(/(\d+)\+?\s*week/);  if (wm) daysAgo = +wm[1] * 7;
    const mm = raw.match(/(\d+)\+?\s*month/); if (mm) daysAgo = +mm[1] * 30;
  }
  const posted = new Date(today);
  posted.setDate(posted.getDate() - daysAgo);
  posted.setDate(posted.getDate() + EXPIRY_DAYS);
  return posted;
}

function daysLeft(job) {
  return Math.ceil((getExpiryDate(job) - Date.now()) / 86400000);
}

function isExpired(job) { return daysLeft(job) <= 0; }

// ── Boot ──────────────────────────────────────────────────────────────
(async () => {
  try {
    const res = await fetch('data/jobs.json');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    allJobs = await res.json();
    setup();
  } catch {
    document.getElementById('jobsGrid').innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">⚠️</div>
        <h3>Could not load job data</h3>
        <p>Run <code>python scrapers/scraper.py</code> to generate data/jobs.json,<br>then refresh this page.</p>
      </div>`;
  }
})();

function setup() {
  freshJobs    = allJobs.filter(j => !isExpired(j));
  archivedJobs = allJobs.filter(j =>  isExpired(j));
  updateStats(freshJobs);
  populateFilters();
  buildChips();
  applyFilters();
}

// ── Animated stat counters ────────────────────────────────────────────
function updateStats(jobs) {
  const companies = new Set(jobs.map(j => j.company));
  const locations = new Set(jobs.map(j => j.location).filter(Boolean));
  countUp('sJobs',      allJobs.length);
  countUp('sCompanies', companies.size);
  countUp('sLocations', locations.size, '+');
}

function countUp(id, target, suffix = '') {
  const el   = document.getElementById(id);
  let n      = 0;
  const step = Math.max(1, Math.ceil(target / 28));
  const t    = setInterval(() => {
    n = Math.min(n + step, target);
    el.textContent = n + suffix;
    if (n >= target) clearInterval(t);
  }, 28);
}

// ── Filter dropdowns ──────────────────────────────────────────────────
function populateFilters() {
  fill('fCompany',  [...new Set(allJobs.map(j => j.company).filter(Boolean))].sort());
  fill('fDept',     [...new Set(allJobs.map(j => j.department).filter(Boolean))].sort());
  fill('fLocation', [...new Set(allJobs.map(j => j.location).filter(Boolean))].sort());
  fill('fType',     [...new Set(allJobs.map(j => j.employment_type).filter(Boolean))].sort());
}

function fill(id, vals) {
  const sel = document.getElementById(id);
  vals.forEach(v => {
    const o = document.createElement('option');
    o.value = o.textContent = v;
    sel.appendChild(o);
  });
}

// ── Category chips ────────────────────────────────────────────────────
function buildChips() {
  const container = document.getElementById('chipsContainer');
  CATEGORIES.forEach(cat => {
    const btn = document.createElement('button');
    btn.className   = 'chip';
    btn.textContent = cat;
    btn.onclick     = () => toggleChip(cat, btn);
    container.appendChild(btn);
  });
}

function toggleChip(cat, btn) {
  if (activeChip === cat) {
    activeChip = null;
    btn.classList.remove('active');
  } else {
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    activeChip = cat;
    btn.classList.add('active');
  }
  applyFilters();
}

// ── Search + filter ───────────────────────────────────────────────────
let debounce;
document.getElementById('searchInput').addEventListener('input', () => {
  clearTimeout(debounce);
  debounce = setTimeout(applyFilters, 220);
});
document.getElementById('searchInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') applyFilters();
});

function _matchJob(job, q, co, dep, loc, typ) {
  if (co  && job.company         !== co)  return false;
  if (dep && job.department      !== dep) return false;
  if (loc && job.location        !== loc) return false;
  if (typ && job.employment_type !== typ) return false;
  if (activeChip) {
    const hay = `${job.title} ${job.department} ${job.job_description}`.toLowerCase();
    if (!hay.includes(activeChip.toLowerCase())) return false;
  }
  if (q) {
    const hay = `${job.title} ${job.location} ${job.department} ${job.job_description}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

function applyFilters() {
  const q   = document.getElementById('searchInput').value.toLowerCase().trim();
  const co  = document.getElementById('fCompany').value;
  const dep = document.getElementById('fDept').value;
  const loc = document.getElementById('fLocation').value;
  const typ = document.getElementById('fType').value;

  renderCards(freshJobs.filter(j => _matchJob(j, q, co, dep, loc, typ)));
  renderPastCards(archivedJobs.filter(j => _matchJob(j, q, co, dep, loc, typ)));
}

function clearAll() {
  document.getElementById('searchInput').value = '';
  ['fCompany', 'fDept', 'fLocation', 'fType'].forEach(id => {
    document.getElementById(id).value = '';
  });
  activeChip = null;
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  applyFilters();
}

// ── Shared card builder ───────────────────────────────────────────────
function jobCardHTML(job, i, archived = false) {
  const info     = companyInfo(job.company);
  const posted   = niceDate(job);
  const dl       = daysLeft(job);
  const cardCls  = archived ? 'job-card past-card' : 'job-card';

  // Days-left badge (only for fresh jobs nearing expiry)
  let expiryBadge = '';
  if (!archived && dl <= WARN_DAYS && dl > 0) {
    const cls = dl <= URGENT_DAYS ? 'urgent' : 'warning';
    expiryBadge = `<span class="expiry-badge ${cls}">${dl}d left</span>`;
  }

  // Action column
  const endLabel = job.end_date
    ? `<span class="end-date-label">Ended ${niceISODate(job.end_date)}</span>`
    : '';

  const actionCol = archived
    ? `<div class="job-action">
         <span class="posted">${posted}</span>
         ${endLabel}
         ${job.external_url
           ? `<a href="${esc(job.external_url)}" target="_blank" rel="noopener noreferrer" class="view-btn expired-btn">
                View Job &rarr;
              </a>
              <span class="expired-note">Expired &middot; Link may not work</span>`
           : `<span class="archived-badge">Archived</span>`}
       </div>`
    : `<div class="job-action">
         ${expiryBadge}
         <span class="posted">${posted}</span>
         <a href="${esc(job.external_url)}" target="_blank" rel="noopener noreferrer" class="view-btn">
           View Job &rarr;
         </a>
       </div>`;

  return `
  <article class="${cardCls}" style="--c-color:${archived ? '#94A3B8' : info.color}; animation-delay:${i * 0.02}s">

    <div class="co-logo" style="background:${info.color}">
      ${info.image
        ? `<img src="${esc(info.image)}" alt="${esc(job.company)}"
             onerror="this.remove();this.parentElement&&(this.parentElement.querySelector('.co-abbr').style.display='flex')">`
        : ''}
      <span class="co-abbr" style="display:${info.image ? 'none' : 'flex'}">${info.abbr}</span>
    </div>

    <div class="job-info">
      <h3 class="job-title">${esc(job.title)}</h3>
      <div class="job-meta">
        <span class="meta">🏢 ${esc(job.company)}</span>
        ${job.location        ? `<span class="meta-sep">·</span><span class="meta">📍 ${esc(job.location)}</span>`          : ''}
        ${job.department      ? `<span class="meta-sep">·</span><span class="dept-tag">${esc(job.department)}</span>`        : ''}
        ${job.employment_type ? `<span class="meta-sep">·</span><span class="type-pill">${esc(job.employment_type)}</span>`  : ''}
        ${job.remote_type     ? `<span class="meta-sep">·</span><span class="remote-pill">${esc(job.remote_type)}</span>`   : ''}
        ${job.experience      ? `<span class="meta-sep">·</span><span class="exp-tag">${esc(job.experience)}</span>`        : ''}
        ${job.job_id          ? `<span class="meta-sep">·</span><span class="req-id">${esc(job.job_id)}</span>`             : ''}
      </div>
    </div>

    ${actionCol}

  </article>`;
}

// ── Fresh jobs section ────────────────────────────────────────────────
function renderCards(jobs) {
  filteredJobs = jobs;
  currentPage  = 1;
  renderPage();
}

function renderPage() {
  const grid       = document.getElementById('jobsGrid');
  const totalPages = Math.ceil(filteredJobs.length / JOBS_PER_PAGE);
  const start      = (currentPage - 1) * JOBS_PER_PAGE;
  const slice      = filteredJobs.slice(start, start + JOBS_PER_PAGE);

  document.getElementById('resultCount').textContent =
    `${filteredJobs.length} result${filteredJobs.length !== 1 ? 's' : ''}`;

  if (!filteredJobs.length) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <h3>No matching jobs</h3>
        <p>Try clearing some filters or searching a different keyword.</p>
      </div>`;
    document.getElementById('pagination').innerHTML = '';
    return;
  }

  grid.innerHTML = slice.map((job, i) => jobCardHTML(job, i, false)).join('');
  renderPagination(totalPages);
  if (currentPage > 1) grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Past / archived section ───────────────────────────────────────────
function renderPastCards(jobs) {
  filteredPast  = jobs;
  currentPagePast = 1;
  const section = document.getElementById('pastSection');
  section.style.display = jobs.length ? 'block' : 'none';
  document.getElementById('pastSubtitle').textContent =
    `${jobs.length} archived role${jobs.length !== 1 ? 's' : ''} · links no longer active`;
  renderPastPage();
}

function renderPastPage() {
  const grid       = document.getElementById('pastGrid');
  const totalPages = Math.ceil(filteredPast.length / JOBS_PER_PAGE);
  const start      = (currentPagePast - 1) * JOBS_PER_PAGE;
  const slice      = filteredPast.slice(start, start + JOBS_PER_PAGE);

  grid.innerHTML = slice.map((job, i) => jobCardHTML(job, i, true)).join('');
  renderPastPagination(totalPages);
  if (currentPagePast > 1) grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function togglePast() {
  pastExpanded = !pastExpanded;
  document.getElementById('pastBody').style.display   = pastExpanded ? 'block' : 'none';
  document.getElementById('pastToggleBtn').textContent = pastExpanded ? 'Hide ▴' : 'Show ▾';
}

function _paginationHTML(cur, total, jobCount, onClickFn) {
  if (total <= 1) return '';
  const W = 2;
  const pages = [1];
  if (cur - W > 2) pages.push('…');
  for (let p = Math.max(2, cur - W); p <= Math.min(total - 1, cur + W); p++) pages.push(p);
  if (cur + W < total - 1) pages.push('…');
  if (total > 1) pages.push(total);

  return `
    <button class="pg-btn" ${cur === 1 ? 'disabled' : ''}
      onclick="${onClickFn}(${cur - 1})">&#8592; Prev</button>
    <div class="pg-numbers">
      ${pages.map(p =>
        p === '…'
          ? `<span class="pg-ellipsis">…</span>`
          : `<button class="pg-num ${p === cur ? 'active' : ''}" onclick="${onClickFn}(${p})">${p}</button>`
      ).join('')}
    </div>
    <button class="pg-btn" ${cur === total ? 'disabled' : ''}
      onclick="${onClickFn}(${cur + 1})">Next &#8594;</button>
    <span class="pg-info">Page ${cur} of ${total} &nbsp;·&nbsp; ${jobCount} jobs</span>`;
}

function renderPagination(total) {
  document.getElementById('pagination').innerHTML =
    _paginationHTML(currentPage, total, filteredJobs.length, 'goPage');
}
function renderPastPagination(total) {
  document.getElementById('paginationPast').innerHTML =
    _paginationHTML(currentPagePast, total, filteredPast.length, 'goPagePast');
}

function goPage(p)     { currentPage     = p; renderPage();     }
function goPagePast(p) { currentPagePast = p; renderPastPage(); }

// ── Helpers ───────────────────────────────────────────────────────────
function companyInfo(name) {
  if (COMPANY_REGISTRY[name]) return COMPANY_REGISTRY[name];
  const hue = [...(name || '')].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
  return { abbr: (name || '?').slice(0, 2).toUpperCase(), color: `hsl(${hue},58%,38%)` };
}

function truncate(str, max) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max).trimEnd() + '…' : str;
}

function niceDate(job) {
  const sd = job.start_date;
  if (sd) {
    try {
      const d = new Date(sd + 'T00:00:00');
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {}
  }
  const raw = job.posted_date || '';
  return raw.replace(/^Posted\s+/i, 'Posted ');
}

function niceISODate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso + 'T00:00:00').toLocaleDateString('en-US',
      { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return iso; }
}

function esc(s) {
  return (s || '')
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;');
}
