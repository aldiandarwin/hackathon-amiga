'use strict';

// A presentation preference only: invoice data, scroll positions and unsaved edits stay in place.
(() => {
  const workspace = document.querySelector('#workspace');
  const sidebar = document.querySelector('#workspace-sidebar');
  const toggle = document.querySelector('#toggle-sidebar');
  if (!workspace || !sidebar || !toggle) return;
  const storageKey = 'amiga.sidebar.collapsed';
  const apply = collapsed => {
    sidebar.hidden = collapsed;
    workspace.classList.toggle('sidebar-collapsed', collapsed);
    toggle.setAttribute('aria-expanded', String(!collapsed));
    const label = collapsed ? 'Tampilkan sidebar' : 'Sembunyikan sidebar';
    toggle.setAttribute('aria-label', label);
    toggle.title = label;
  };
  try { apply(localStorage.getItem(storageKey) === 'true'); } catch { apply(false); }
  toggle.addEventListener('click', () => {
    const collapsed = !sidebar.hidden;
    apply(collapsed);
    try { localStorage.setItem(storageKey, String(collapsed)); } catch { /* Still usable without storage. */ }
  });
})();
