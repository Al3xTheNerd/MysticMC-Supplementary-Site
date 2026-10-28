(() => {
  const form = document.getElementById('art-editor');
  if (!form) return;
  const fileInput = document.getElementById('art-files');
  const grid = document.getElementById('art-grid');
  const tray = document.getElementById('art-tray');
  const error = document.getElementById('art-error');
  const output = document.getElementById('art-layout-data');
  const artId = form.dataset.artId;
  const staticRoot = form.dataset.staticRoot;
  let rows = JSON.parse(form.dataset.layout).map(row => row.map(value => value === null ? null : `e:${value}`));
  const existing = JSON.parse(form.dataset.existing).map(value => `e:${value}`);
  let selected = null;
  let urls = [];
  let newTiles = [];

  function showError(message) {
    error.textContent = message;
    error.classList.remove('d-none');
    error.scrollIntoView({block: 'nearest'});
  }
  function clearError() { error.textContent = ''; error.classList.add('d-none'); }
  function rejectFiles(message) {
    urls.forEach(url => URL.revokeObjectURL(url));
    urls = []; newTiles = []; fileInput.value = '';
    render(); showError(message);
  }
  function tileUrl(id) {
    if (id.startsWith('n:')) return newTiles[Number(id.slice(2))]?.url;
    return `${staticRoot}/${artId}/${Number(id.slice(2))}.png`;
  }
  function findTile(id) {
    for (let r = 0; r < rows.length; r++) {
      const c = rows[r].indexOf(id);
      if (c !== -1) return [r, c];
    }
    return null;
  }
  function place(id, r, c) {
    if (id === null) { rows[r][c] = null; selected = null; render(); return; }
    const source = findTile(id);
    if (source && source[0] === r && source[1] === c) return;
    const displaced = rows[r][c];
    if (source) rows[source[0]][source[1]] = displaced;
    rows[r][c] = id;
    selected = null;
    render();
  }
  function tileButton(id, inSlot = false) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = inSlot ? 'art-slot' : 'art-tray-tile';
    button.setAttribute('aria-label', `Tile ${id}`);
    if (selected === id) button.classList.add('is-selected');
    const image = document.createElement('img');
    image.src = tileUrl(id);
    image.alt = '';
    button.append(image);
    button.draggable = true;
    button.addEventListener('dragstart', event => { event.dataTransfer.setData('text/plain', id); event.dataTransfer.effectAllowed = 'move'; });
    button.addEventListener('click', () => { selected = selected === id ? null : id; render(); });
    return button;
  }
  function render() {
    clearError();
    document.getElementById('place-blank').classList.toggle('active', selected === '__blank__');
    grid.replaceChildren();
    tray.replaceChildren();
    const used = new Set(rows.flat().filter(Boolean));
    const allTiles = existing.concat(newTiles.map((_, index) => `n:${index}`));
    const unused = allTiles.filter(id => !used.has(id));
    if (!unused.length) {
      const hint = document.createElement('span');
      hint.className = 'text-white-50'; hint.textContent = 'All tiles are placed.'; tray.append(hint);
    } else unused.forEach(id => tray.append(tileButton(id)));

    rows.forEach((row, r) => {
      const wrapper = document.createElement('div'); wrapper.className = 'art-editor-row';
      const cells = document.createElement('div'); cells.className = 'art-editor-cells';
      row.forEach((id, c) => {
        const slot = id ? tileButton(id, true) : document.createElement('button');
        if (!id) {
          slot.type = 'button'; slot.className = 'art-slot is-blank';
          slot.textContent = 'Blank'; slot.setAttribute('aria-label', `Blank space, row ${r + 1}, column ${c + 1}`);
        }
        slot.addEventListener('click', event => {
          if (selected === null) return;
          event.stopImmediatePropagation();
          place(selected === '__blank__' ? null : selected, r, c);
        }, true);
        slot.addEventListener('dragover', event => { event.preventDefault(); slot.classList.add('drag-over'); });
        slot.addEventListener('dragleave', () => slot.classList.remove('drag-over'));
        slot.addEventListener('drop', event => {
          event.preventDefault();
          const moving = event.dataTransfer.getData('text/plain');
          if (allTiles.includes(moving)) place(moving, r, c);
        });
        cells.append(slot);
      });
      wrapper.append(cells);
      const actions = document.createElement('div'); actions.className = 'art-row-actions';
      const add = document.createElement('button'); add.type = 'button'; add.className = 'btn btn-sm btn-outline-light'; add.textContent = '+ Column';
      add.addEventListener('click', () => { row.push(null); render(); }); actions.append(add);
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn btn-sm btn-outline-danger'; remove.textContent = row.length === 1 ? 'Remove row' : '− Column';
      remove.addEventListener('click', () => {
        if (row.length > 1) row.pop(); else if (rows.length > 1) rows.splice(r, 1);
        else { showError('Keep at least one row.'); return; }
        render();
      }); actions.append(remove);
      if (row.length > 1) {
        const removeRow = document.createElement('button'); removeRow.type = 'button'; removeRow.className = 'btn btn-sm btn-outline-danger'; removeRow.textContent = 'Remove row';
        removeRow.addEventListener('click', () => { if (rows.length > 1) { rows.splice(r, 1); render(); } else showError('Keep at least one row.'); }); actions.append(removeRow);
      }
      wrapper.append(actions); grid.append(wrapper);
    });
  }
  fileInput.addEventListener('change', async () => {
    urls.forEach(url => URL.revokeObjectURL(url)); urls = []; newTiles = [];
    rows = rows.map(row => row.map(id => id?.startsWith('n:') ? null : id));
    selected = null;
    const files = Array.from(fileInput.files);
    if (files.reduce((total, file) => total + file.size, 0) > 50 * 1024 * 1024) {
      rejectFiles('The upload is too large (50 MB maximum per art piece).'); return;
    }
    for (const file of files) {
      if (!file.name.toLowerCase().endsWith('.png') || file.type !== 'image/png' || file.size > 2 * 1024 * 1024) {
        rejectFiles('Only PNG files up to 2 MB each are allowed.'); return;
      }
      const url = URL.createObjectURL(file); urls.push(url);
      try {
        const image = new Image(); image.src = url;
        await image.decode();
        if (image.naturalWidth !== 128 || image.naturalHeight !== 128) throw new Error('size');
      } catch {
        rejectFiles('Every tile must be a valid 128×128 PNG.'); return;
      }
      newTiles.push({url});
    }
    render();
  });
  document.getElementById('add-row').addEventListener('click', () => { rows.push([null]); render(); });
  document.getElementById('place-blank').addEventListener('click', () => {
    selected = selected === '__blank__' ? null : '__blank__';
    render();
  });
  document.getElementById('clear-selection').addEventListener('click', () => { selected = null; render(); });
  form.addEventListener('submit', event => {
    const placed = new Set(rows.flat().filter(Boolean));
    const missing = newTiles.some((_, index) => !placed.has(`n:${index}`));
    if (missing || placed.size === 0) {
      event.preventDefault(); showError(missing ? 'Place every newly uploaded tile before saving.' : 'Place at least one image tile before saving.'); return;
    }
    output.value = JSON.stringify(rows);
  });
  render();
})();
