'use strict';
// Folder Picker Modal logic
// Single-pane tree view with lazy loading, hidden-folder filtering, and clear selection indicator.
// Public API: window.openFolderPicker(inputId)
(function(){
  // The input element ID to write the selected path into when confirming the modal
  let currentTargetInputId = null;
  // The currently selected path in the tree
  let currentPath = '';
  // Cached Bootstrap Modal instance
  let modalInstance = null;
  // Whether the tree layout and root were initialized
  let treeInitialized = false;

  // Ensure and (lazily) create the Bootstrap modal instance
  function ensureModal() {
    if (modalInstance) return modalInstance;
    const modalEl = document.getElementById('folderPickerModal');
    if (!modalEl) {
      console.error('folderPickerModal not found in DOM.');
      return null;
    }
    if (window.bootstrap && bootstrap.Modal) {
      modalInstance = new bootstrap.Modal(modalEl);
    } else {
      modalInstance = { show: () => modalEl.classList.add('show'), hide: () => modalEl.classList.remove('show') };
    }
    return modalInstance;
  }

  // Call backend to list directories under `path` (or default if omitted)
  async function fetchList(path, { includeHidden = false } = {}) {
    const url = new URL('/api/fs/list', window.location.origin);
    if (path) url.searchParams.set('path', path);
    if (includeHidden) url.searchParams.set('include_hidden', 'true');
    const res = await fetch(url.toString());
    if (!res.ok) {
      let msg = 'Error fetching directory list';
      try { const t = await res.text(); if (t) msg = t; } catch(e){}
      throw new Error(msg);
    }
    const data = await res.json();
    return data;
  }

  // Tree view initialization (single pane)
  function initTree() {
    if (treeInitialized) return;
    const treeEl = document.getElementById('fp-tree');
    if (!treeEl) return;
    treeEl.innerHTML = '';
    // Root node representing filesystem root
    const root = createTreeItem({ name: '/', path: '/', hasChildren: true });
    const ul = document.createElement('ul');
    ul.className = 'list-unstyled mb-0';
    ul.appendChild(root);
    treeEl.appendChild(ul);
    // Expand root initially
    expandTreeItem(root, '/').then(() => {
      // Ensure root is visibly expanded (no user click required)
      const childrenUl = root.querySelector(':scope > ul');
      if (childrenUl) childrenUl.style.display = '';
      const caretEl = root.querySelector(':scope > .d-flex button.btn-link i');
      if (caretEl) caretEl.className = 'fas fa-caret-down';
      const iconEl = root.querySelector(':scope > .d-flex .fas.fa-regular');
      if (iconEl) iconEl.textContent = '\uf07c'; // open folder glyph
    });
    treeInitialized = true;
  }

  // Create a single tree item <li> for a directory entry
  // Structure:
  // <li data-path="..." class="fp-tree-item">
  //   <div class="d-flex align-items-center gap-1">
  //     <button class="toggle">(caret)</button>
  //     <i class="fas fa-folder me-1"></i>
  //     <button class="label">(folder name)</button>
  //   </div>
  //   <ul class="children" style="display:none"></ul>
  // </li>
  function createTreeItem(entry) {
    const li = document.createElement('li');
    li.dataset.path = entry.path;
    li.className = 'fp-tree-item';

    const row = document.createElement('div');
    // Ensure consistent row height to avoid layout jump when selecting
    row.className = 'd-flex align-items-center gap-1 py-1';

    // caret toggle for expand/collapse (Font Awesome for consistency)
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'btn btn-sm btn-link p-0 text-decoration-none';
    toggle.style.width = '1.2rem';
    const caret = document.createElement('i');
    if (entry.hasChildren) {
      caret.className = 'fas fa-caret-right';
    } else {
      // No children: visually hide the toggle to avoid implying expandability
      toggle.disabled = true;
      toggle.style.visibility = 'hidden';
    }
    toggle.appendChild(caret);

    // Folder icon: use the exact Font Awesome unicode escapes as on the documents page.
    // Closed: \uf07b, Open: \uf07c
    const icon = document.createElement('span');
    // Match documents page neutral color
    icon.className = 'fas fa-regular me-1 text-secondary';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '\uf07b'; // closed folder

    // label acts as the selection target
    const label = document.createElement('button');
    label.type = 'button';
    label.className = 'btn btn-link p-0 text-decoration-none text-start';
    label.textContent = entry.name;

    row.appendChild(toggle);
    row.appendChild(icon);
    row.appendChild(label);
    li.appendChild(row);

    const children = document.createElement('ul');
    children.className = 'list-unstyled ms-3 mb-0';
    children.style.display = 'none';
    li.appendChild(children);

    // Events
    toggle.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!entry.hasChildren) return;
      if (children.style.display === 'none') {
        // If not fully loaded yet (including 'partial'), load fully now
        if (children.dataset.loaded !== 'true') {
          await expandTreeItem(li, entry.path, false, null);
        }
        children.style.display = '';
        // switch caret icon to down
        caret.className = 'fas fa-caret-down';
        // switch folder to open when expanded
        icon.textContent = '\uf07c'; // open folder
      } else {
        children.style.display = 'none';
        // switch caret icon to right
        caret.className = 'fas fa-caret-right';
        // switch folder to closed when collapsed
        icon.textContent = '\uf07b';
      }
    });

    label.addEventListener('click', async (e) => {
      e.preventDefault();
      // select this node (no right pane)
      await selectPath(entry.path);
    });

    return li;
  }

  // Expand a given tree item's children (lazy-load once)
  async function expandTreeItem(li, path, includeHidden = false, onlyName = null) {
    const children = li.querySelector('ul');
    if (!children) return;
    // If already fully loaded with hidden included, nothing to do
    if (children.dataset.loaded === 'true_hidden') return;
    // If already loaded without hidden and we don't need hidden now, nothing to do
    if (children.dataset.loaded === 'true' && !includeHidden) return;
    // If already loaded without hidden, but we need a hidden child specifically,
    // try to append just that child if missing, without rebuilding the list.
    if (children.dataset.loaded === 'true' && includeHidden && onlyName) {
      const exists = Array.from(children.children).some(li => li.dataset.path && li.dataset.path.split('/').filter(Boolean).pop() === onlyName);
      if (exists) return; // already present
      try {
        const dataHidden = await fetchList(path, { includeHidden: true });
        const match = (dataHidden.entries || []).find(ch => ch.name === onlyName);
        if (match) {
          const childLi = createTreeItem(match);
          children.appendChild(childLi);
        }
        return;
      } catch (_) {
        return;
      }
    }
    const data = await fetchList(path, { includeHidden });
    children.innerHTML = '';
    (data.entries || []).forEach(ch => {
      if (onlyName && ch.name !== onlyName) return; // only create the target child when specified
      const childLi = createTreeItem(ch);
      children.appendChild(childLi);
    });
    // Mark as partial or fully loaded (track whether hidden items included)
    children.dataset.loaded = (onlyName ? 'partial' : (includeHidden ? 'true_hidden' : 'true'));
    // If this was a FULL load and there are no visible children, mark as leaf (hide caret)
    if (!onlyName && children.children.length === 0) {
      children.style.display = 'none';
      const toggleBtn = li.querySelector(':scope > .d-flex > button.btn-link');
      const caretIcon = toggleBtn ? toggleBtn.querySelector('i') : null;
      if (toggleBtn) {
        toggleBtn.disabled = true;
        toggleBtn.style.visibility = 'hidden';
      }
      if (caretIcon) caretIcon.className = '';
      const iconEl = li.querySelector(':scope > .d-flex .fas.fa-regular');
      if (iconEl) iconEl.textContent = '\uf07b';
    }
  }

  // Select a path in the tree (update highlight only)
  async function selectPath(path) {
    // set and highlight
    currentPath = path;
    highlightTreeSelection(path);
    // No right-pane: nothing else to render here
  }

  // Smoothly center the given element within the tree scroll container
  function centerScrollIntoView(el) {
    if (!el) return;
    const container = document.getElementById('fp-tree');
    if (!container) { try { el.scrollIntoView({ block: 'center' }); } catch(_){} return; }
    // Prefer the visible row div for precise positioning
    const target = el.querySelector(':scope > .d-flex') || el;
    const cRect = container.getBoundingClientRect();
    const eRect = target.getBoundingClientRect();
    const offset = (eRect.top - cRect.top) - (cRect.height / 2 - eRect.height / 2);
    container.scrollTop += offset;
  }

  function highlightTreeSelection(path) {
    const treeEl = document.getElementById('fp-tree');
    if (!treeEl) return;
    // clear previous selection styling
    treeEl.querySelectorAll('li.fp-tree-item .btn-link.p-0').forEach(btn => {
      btn.classList.remove('fw-semibold', 'text-primary');
    });
    treeEl.querySelectorAll('li.fp-tree-item > .d-flex').forEach(row => {
      row.classList.remove('bg-secondary-subtle', 'bg-light', 'shadow-sm', 'rounded');
    });
    // Try to find matching item by data-path and mark as selected
    const match = Array.from(treeEl.querySelectorAll('li.fp-tree-item')).find(li => li.dataset.path === path);
    if (match) {
      const labelBtn = match.querySelector('.btn-link.p-0');
      if (labelBtn) {
        labelBtn.classList.add('fw-semibold', 'text-primary');
      }
      const row = match.querySelector(':scope > .d-flex');
      if (row) {
        // Subtle but clear selection indicator using Bootstrap subtle background
        // Use bg-secondary-subtle if available (BS 5.3), fallback to bg-light. Add slight shadow for emphasis.
        row.classList.add('rounded', 'shadow-sm');
        row.classList.add('bg-secondary-subtle');
        if (!('CSS' in window) || !getComputedStyle(row).backgroundColor) {
          // Fallback when class is unavailable
          row.classList.add('bg-light');
        }
      }
      // Ensure the selected item is visible in the modal on preselection.
      // Wait a frame so layout (and any expand animations) can settle.
      try {
        requestAnimationFrame(() => {
          centerScrollIntoView(match);
          // Fallback after paint
          setTimeout(() => centerScrollIntoView(match), 0);
        });
      } catch (_) {
        centerScrollIntoView(match);
      }
    }
  }

  async function openFolderPicker(targetInputId) {
    currentTargetInputId = targetInputId;
    const modal = ensureModal();
    if (!modal) return;
    const modalEl = document.getElementById('folderPickerModal');
    // Defer preselection until after the modal is fully shown, so scrolling works reliably
    const runPreselect = async () => {
      initTree();
      const current = document.getElementById(targetInputId)?.value || '';
      if (current && current !== '/') {
        await expandAndSelectPath(current);
      } else {
        await selectPath('/');
      }
    };
    if (modalEl && window.bootstrap && typeof bootstrap !== 'undefined') {
      const handler = async () => {
        modalEl.removeEventListener('shown.bs.modal', handler);
        await runPreselect();
      };
      modalEl.addEventListener('shown.bs.modal', handler, { once: true });
      modal.show();
    } else {
      modal.show();
      // Fallback if Bootstrap events are unavailable
      setTimeout(runPreselect, 0);
    }
  }

  // Confirm selection: write currentPath into target input and close modal
  function selectCurrent() {
    if (!currentTargetInputId || !currentPath) return;
    const inp = document.getElementById(currentTargetInputId);
    if (inp) {
      inp.value = currentPath;
      if (typeof window.checkPathInput === 'function') {
        try { window.checkPathInput(); } catch(e){}
      }
    }
    const modal = ensureModal();
    if (modal) modal.hide();
  }

  function wireControls() {
    // Wire modal footer "Select this folder" button
    const selectBtn = document.getElementById('fp-select-btn');
    if (selectBtn) selectBtn.addEventListener('click', selectCurrent);

    // iCloud Drive shortcut: show only if path exists; bind click once
    const icloudPath = '~/Library/Mobile Documents/com~apple~CloudDocs';
    const ensureIcloudButton = async () => {
      const btn = document.getElementById('fp-icloud-btn');
      if (!btn) return;
      // One-time existence check/show
      if (!btn.dataset.icloudChecked) {
        try {
          console.log("Checking for iCloud Drive");
          const url = new URL('/api/fs/list', window.location.origin);
          url.searchParams.set('path', icloudPath);
          const res = await fetch(url.toString());
          if (res.ok) btn.classList.remove('d-none');
        } catch (_) {
          // keep hidden on error
        } finally {
          btn.dataset.icloudChecked = '1';
        }
      }
      // Definitive click bind (overwrite any previous)
      btn.onclick = async () => {
        try {
          await openFolderPickerWithPath(icloudPath);
        } catch (_) {}
      };
    };
    // Initial ensure
    ensureIcloudButton();
    // Ensure on each modal show (handles cases where HTML is re-rendered)
    const modalEl = document.getElementById('folderPickerModal');
    if (modalEl && window.bootstrap) {
      modalEl.addEventListener('shown.bs.modal', ensureIcloudButton);
    }
  }

  // Public helper: open picker pointing to a specific path
  async function openFolderPickerWithPath(path) {
    const modal = ensureModal();
    console.log("Opening folder picker with path: ", path);
    if (!modal) return;
    const modalEl = document.getElementById('folderPickerModal');
    const run = async () => {
      initTree();
      await expandAndSelectPath(path);
    };
    if (modalEl && window.bootstrap && typeof bootstrap !== 'undefined') {
      // If already shown, run immediately; otherwise wait for shown event
      const alreadyShown = modalEl.classList.contains('show');
      if (alreadyShown) {
        await run();
      } else {
        const handler = async () => {
          modalEl.removeEventListener('shown.bs.modal', handler);
          await run();
        };
        modalEl.addEventListener('shown.bs.modal', handler, { once: true });
        modal.show();
      }
    } else {
      modal.show();
      setTimeout(run, 0);
    }
  }

  async function expandAndSelectPath(path) {
    // Ensure tree ready
    initTree();
    // Normalize path first (expand ~, resolve symlinks on server)
    let normalized = path;
    try {
      const data = await fetchList(path, { includeHidden: true });
      if (data && data.path) normalized = data.path;
    } catch(_) {}
    const parts = normalized.split('/').filter(Boolean);
    let accum = '/';
    // Start from root LI
    const treeEl = document.getElementById('fp-tree');
    if (!treeEl) return;
    let currentLi = treeEl.querySelector('li.fp-tree-item[data-path="/"]');
    for (const part of parts) {
      // expand currentLi children; allow hidden but render only the needed child
      await expandTreeItem(currentLi, accum, true, part);
      // If this parent is already visible and only partially loaded, now load full visible siblings
      const parentUl = currentLi.querySelector(':scope > ul');
      if (parentUl && parentUl.style.display !== 'none' && parentUl.dataset.loaded === 'partial') {
        await expandTreeItem(currentLi, accum, false, null);
        parentUl.style.display = '';
      }
      const children = currentLi.querySelectorAll(':scope > ul > li.fp-tree-item');
      let nextLi = null;
      for (const li of children) {
        if (li.dataset.path && li.dataset.path.split('/').filter(Boolean).pop() === part) {
          nextLi = li; break;
        }
      }
      if (!nextLi) break;
      // open its children container visually
      const toggle = nextLi.querySelector('div > button.btn-link');
      const childrenUl = nextLi.querySelector(':scope > ul');
      if (childrenUl && childrenUl.style.display === 'none') {
        childrenUl.style.display = '';
        // switch caret icon to down if toggle exists
        const caret = toggle ? toggle.querySelector('i') : null;
        if (caret) caret.className = 'fas fa-caret-down';
        // also set folder icon to open for preselected path
        const iconEl = nextLi.querySelector(':scope > .d-flex .fas.fa-regular');
        if (iconEl) iconEl.textContent = '\uf07c';
      }
      accum = (accum === '/' ? '' : accum) + '/' + part;
      currentLi = nextLi;
    }
    await selectPath(normalized);
  }

  // Public API
  window.openFolderPicker = openFolderPicker;
  window.openFolderPickerWithPath = openFolderPickerWithPath;

  // Init on DOM ready (in case this file is loaded before modal exists)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireControls);
  } else {
    wireControls();
  }
})();
