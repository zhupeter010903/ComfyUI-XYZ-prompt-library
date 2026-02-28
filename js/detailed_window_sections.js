// Detailed Window Sections
// This module encapsulates the UI section builders for the Grouped Prompt detailed window.
// Features:
// - Top settings row (Group Name, Weight, Random prompt #) in one line with labels
// - Shuffle options row with No Shuffle / Shuffle Active / Shuffle All in one line
// - Import prompts-from-string section (label + input on one line, controls below)
// - Add-buttons row (Add Tag + Add Subgroup) side by side

export function createTopSettingsRow(node, groupData, groupIndex) {
  const row = document.createElement('div');
  row.style.cssText = `
          display: grid;
          grid-template-columns: 1.2fr 0.6fr 0.6fr;
          gap: 8px;
          align-items: center;
          margin-bottom: 12px;
      `;

  // Group Name
  const nameCol = document.createElement('div');
  nameCol.style.cssText = `display:flex; flex-direction:column; gap:4px;`;
  const nameLabel = document.createElement('label');
  nameLabel.textContent = 'Group Name';
  nameLabel.style.cssText = `color:#999; font-size:12px; font-weight:500; text-transform:uppercase;`;
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.value = groupData.name || `Group ${groupIndex + 1}`;
  nameInput.placeholder = 'Group Name';
  nameInput.style.cssText = `
          width: 100%;
          background: #232323;
          border: 1px solid #2c2c2c;
          border-radius: 6px;
          padding: 8px;
          color: #ccc;
          font-size: 12px;
          box-sizing: border-box;
      `;
  nameInput.addEventListener('input', e => {
    this.onGroupNameChange(node, groupIndex, e.target.value);
  });
  nameCol.appendChild(nameLabel);
  nameCol.appendChild(nameInput);
  row.appendChild(nameCol);

  // Weight
  const weightCol = document.createElement('div');
  weightCol.style.cssText = `display:flex; flex-direction:column; gap:4px;`;
  const weightLabel = document.createElement('label');
  weightLabel.textContent = 'Weight';
  weightLabel.style.cssText = `color:#999; font-size:12px; font-weight:500; text-transform:uppercase;`;
  const weightInput = document.createElement('input');
  weightInput.type = 'text';
  weightInput.value = groupData.weight || '1';
  weightInput.placeholder = '1 or 0.5-1.5';
  weightInput.style.cssText = `
          width: 100%;
          background: #232323;
          border: 1px solid #2c2c2c;
          border-radius: 6px;
          padding: 8px;
          color: #ccc;
          font-size: 12px;
          box-sizing: border-box;
      `;
  weightInput.addEventListener('input', e => {
    this.onGroupWeightChange(node, groupIndex, e.target.value);
  });
  weightCol.appendChild(weightLabel);
  weightCol.appendChild(weightInput);
  row.appendChild(weightCol);

  // Random prompt #
  const randomCol = document.createElement('div');
  randomCol.style.cssText = `display:flex; flex-direction:column; gap:4px;`;
  const randomLabel = document.createElement('label');
  randomLabel.textContent = 'Random prompt #';
  randomLabel.style.cssText = `color:#999; font-size:12px; font-weight:500; text-transform:uppercase;`;
  const randomInput = document.createElement('input');
  randomInput.type = 'text';
  randomInput.value = groupData.random_count || '0';
  randomInput.placeholder = '0 or 1-3';
  randomInput.style.cssText = `
          width: 100%;
          background: #232323;
          border: 1px solid #2c2c2c;
          border-radius: 6px;
          padding: 8px;
          color: #ccc;
          font-size: 12px;
          box-sizing: border-box;
      `;
  randomInput.addEventListener('input', e => {
    this.onGroupRandomCountChange(node, groupIndex, e.target.value);
  });
  randomCol.appendChild(randomLabel);
  randomCol.appendChild(randomInput);
  row.appendChild(randomCol);

  return row;
}

export function createStatusSection(node, groupData, groupIndex) {
  const section = document.createElement('div');
  section.className = 'status-section';
  section.style.cssText = `
          margin-bottom: 12px;
          display: grid;
          grid-template-columns: auto auto auto auto auto auto auto;
          align-items: center;
          gap: 8px;
      `;

  const label = document.createElement('label');
  label.textContent = 'Shuffle options:';
  label.style.cssText = `
          color: #999;
          font-size: 12px;
          font-weight: 500;
          text-transform: uppercase;
      `;
  section.appendChild(label);

  const defaultBtn = this.createStatusButton('No Shuffle', 'default', groupData.status === 'default', () => {
    this.onGroupStatusChange(node, groupIndex, 'default');
  });
  section.appendChild(defaultBtn);

  const shuffleActiveBtn = this.createStatusButton(
    'Shuffle Active',
    'shuffle_active',
    groupData.status === 'shuffle_active',
    () => {
      this.onGroupStatusChange(node, groupIndex, 'shuffle_active');
    },
  );
  section.appendChild(shuffleActiveBtn);

  const shuffleAllBtn = this.createStatusButton(
    'Shuffle All',
    'shuffle_all',
    groupData.status === 'shuffle_all',
    () => {
      this.onGroupStatusChange(node, groupIndex, 'shuffle_all');
    },
  );
  section.appendChild(shuffleAllBtn);

  // Visual separator between shuffle controls and bulk toggles
  const separator = document.createElement('div');
  separator.style.cssText = `
          width: 1px;
          height: 22px;
          background: #3a3a3a;
          margin: 0 6px;
      `;
  section.appendChild(separator);

  // Bulk toggle: top-level enable/disable (switch state; does not touch tags inside subgroups)
  if (groupData._bulkEnableNext !== 'disable' && groupData._bulkEnableNext !== 'enable') {
    groupData._bulkEnableNext = 'enable';
  }
  const enableInitialText = groupData._bulkEnableNext === 'enable' ? 'Enable All' : 'Disable All';
  const toggleEnableBtn = this.createStatusButton(enableInitialText, 'toggle_enable_top', false, () => {
    const next = groupData._bulkEnableNext === 'enable';
    const group = node.promptGroups?.[groupIndex];
    if (group && Array.isArray(group.items)) {
      group.items.forEach(it => {
        if (it.type === 'prompt_tag' || it.type === 'prompt_subgroup') {
          it.enabled = next;
        }
      });
    }
    groupData._bulkEnableNext = next ? 'disable' : 'enable';
    styleEnableBtn();
    this.updateHiddenWidget(node);
    this.refreshItemsList(node, groupIndex);
  });
  // Fixed width and color styling for enable button
  const styleEnableBtn = () => {
    const isEnable = groupData._bulkEnableNext === 'enable';
    toggleEnableBtn.textContent = isEnable ? 'Enable All' : 'Disable All';
    toggleEnableBtn.style.width = '140px';
    toggleEnableBtn.style.minWidth = '140px';
    toggleEnableBtn.style.maxWidth = '140px';
    toggleEnableBtn.style.background = isEnable ? '#22C55E' : '#EF4444';
    toggleEnableBtn.style.color = '#fff';
    toggleEnableBtn.style.border = '1px solid #2c2c2c';
  };
  toggleEnableBtn.addEventListener('mouseenter', () => {
    const isEnable = groupData._bulkEnableNext === 'enable';
    toggleEnableBtn.style.background = isEnable ? '#16A34A' : '#DC2626';
  });
  toggleEnableBtn.addEventListener('mouseleave', styleEnableBtn);
  styleEnableBtn();
  section.appendChild(toggleEnableBtn);

  // Bulk toggle: top-level random flag (switch state; does not touch tags inside subgroups)
  if (groupData._bulkRandomNext !== 'disable' && groupData._bulkRandomNext !== 'enable') {
    groupData._bulkRandomNext = 'enable';
  }
  const randomInitialText = groupData._bulkRandomNext === 'enable' ? 'Random All' : 'Random None';
  const toggleRandomBtn = this.createStatusButton(randomInitialText, 'toggle_random_top', false, () => {
    const next = groupData._bulkRandomNext === 'enable';
    const group = node.promptGroups?.[groupIndex];
    if (group && Array.isArray(group.items)) {
      group.items.forEach(it => {
        if (it.type === 'prompt_tag' || it.type === 'prompt_subgroup') {
          it.random_candidate = next;
        }
      });
    }
    groupData._bulkRandomNext = next ? 'disable' : 'enable';
    styleRandomBtn();
    this.updateHiddenWidget(node);
    this.refreshItemsList(node, groupIndex);
  });
  // Fixed width and color styling for random button
  const styleRandomBtn = () => {
    const isEnable = groupData._bulkRandomNext === 'enable';
    toggleRandomBtn.textContent = isEnable ? 'Random All' : 'Random None';
    toggleRandomBtn.style.width = '140px';
    toggleRandomBtn.style.minWidth = '140px';
    toggleRandomBtn.style.maxWidth = '140px';
    toggleRandomBtn.style.background = isEnable ? '#8B5CF6' : '#6B7280';
    toggleRandomBtn.style.color = '#fff';
    toggleRandomBtn.style.border = '1px solid #2c2c2c';
  };
  toggleRandomBtn.addEventListener('mouseenter', () => {
    const isEnable = groupData._bulkRandomNext === 'enable';
    toggleRandomBtn.style.background = isEnable ? '#7C3AED' : '#4B5563';
  });
  toggleRandomBtn.addEventListener('mouseleave', styleRandomBtn);
  styleRandomBtn();
  section.appendChild(toggleRandomBtn);

  return section;
}

export function createAddButtonsRow(node, groupIndex) {
  const row = document.createElement('div');
  row.style.cssText = `
          display: grid;
          grid-template-columns: 1fr 1fr auto;
          gap: 8px;
          margin-bottom: 16px;
      `;
  const addTagBtn = this.createAddTagButton(node, groupIndex);
  const addSubgroupBtn = this.createAddSubgroupButton(node, groupIndex);
  const saveBtn = document.createElement('button');
  saveBtn.textContent = '💾 Save as Template';
  saveBtn.style.cssText = `
          padding: 10px 12px;
          background: #F59E0B;
          border: none;
          border-radius: 6px;
          color: white;
          font-size: 12px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
      `;
  saveBtn.addEventListener('mouseenter', () => {
    saveBtn.style.background = '#D97706';
  });
  saveBtn.addEventListener('mouseleave', () => {
    saveBtn.style.background = '#F59E0B';
  });
  saveBtn.addEventListener('click', () => {
    if (node.promptGroups && node.promptGroups[groupIndex]) {
      this.saveGroupAsTemplate(node, node.promptGroups[groupIndex], groupIndex);
    }
  });
  row.appendChild(addTagBtn);
  row.appendChild(addSubgroupBtn);
  row.appendChild(saveBtn);
  return row;
}

export function createImportSection(node, groupData, groupIndex) {
  const section = document.createElement('div');
  section.style.cssText = `
          margin-bottom: 16px;
          display: flex;
          flex-direction: column;
          gap: 8px;
      `;

  const inputRow = document.createElement('div');
  inputRow.style.cssText = `
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 8px;
          align-items: center;
      `;

  const label = document.createElement('label');
  label.textContent = 'Import prompts from string:';
  label.style.cssText = `
          color: #999;
          font-size: 12px;
          font-weight: 500;
          text-transform: uppercase;
          white-space: nowrap;
      `;
  inputRow.appendChild(label);

  const input = document.createElement('input');
  input.type = 'text';
  input.placeholder = 'tag, (tag2:1.2), (tag3, 0.8), ...';
  input.style.cssText = `
          width: 100%;
          background: #232323;
          border: 1px solid #2c2c2c;
          border-radius: 6px;
          padding: 8px;
          color: #ccc;
          font-size: 12px;
          box-sizing: border-box;
      `;
  inputRow.appendChild(input);
  section.appendChild(inputRow);

  const controlsRow = document.createElement('div');
  controlsRow.style.cssText = `
          display: flex;
          gap: 8px;
          align-items: center;
      `;

  const importToGroupBtn = document.createElement('button');
  importToGroupBtn.textContent = 'Import to Group';
  importToGroupBtn.style.cssText = `
          padding: 6px 10px;
          background: #059669;
          border: none;
          border-radius: 4px;
          color: #fff;
          font-size: 12px;
          cursor: pointer;
      `;

  const importToExistingBtn = document.createElement('button');
  importToExistingBtn.textContent = 'Import to Subgroup';
  importToExistingBtn.style.cssText = importToGroupBtn.style.cssText;

  const importToNewBtn = document.createElement('button');
  importToNewBtn.textContent = 'Import to New Subgroup';
  importToNewBtn.style.cssText = importToGroupBtn.style.cssText;

  const subgroupSelect = document.createElement('select');
  subgroupSelect.style.cssText = `
          background: #1a1a1a;
          border: 1px solid #2c2c2c;
          border-radius: 4px;
          color: #ccc;
          padding: 6px;
          font-size: 12px;
          width: 180px;
          min-width: 180px;
          max-width: 180px;
      `;
  const defaultOpt = document.createElement('option');
  defaultOpt.value = '';
  defaultOpt.textContent = node.promptGroups[groupIndex]?.items?.some(it => it.type === 'prompt_subgroup')
    ? 'Select subgroup'
    : 'No subgroups';
  subgroupSelect.appendChild(defaultOpt);
  const items = node.promptGroups[groupIndex]?.items || [];
  items.forEach((it, idx) => {
    if (it.type === 'prompt_subgroup') {
      const opt = document.createElement('option');
      opt.value = String(idx);
      opt.textContent = it.name || `Subgroup ${idx + 1}`;
      subgroupSelect.appendChild(opt);
    }
  });

  controlsRow.appendChild(importToGroupBtn);
  controlsRow.appendChild(importToExistingBtn);
  controlsRow.appendChild(subgroupSelect);
  controlsRow.appendChild(importToNewBtn);
  section.appendChild(controlsRow);

  const parse = () => this.parseImportString(input.value || '');

  importToGroupBtn.addEventListener('click', () => {
    const parsed = parse();
    if (parsed.length === 0) return;
    const grp = node.promptGroups[groupIndex];
    if (!Array.isArray(grp.items)) grp.items = [];
    parsed.forEach(({ text, weight }) => {
      grp.items.push({ type: 'prompt_tag', text, enabled: true, weight, random_candidate: false });
    });
    this.updateHiddenWidget(node);
    this.refreshItemsList(node, groupIndex);
    input.value = '';
  });

  importToExistingBtn.addEventListener('click', () => {
    const idx = subgroupSelect.value === '' ? -1 : parseInt(subgroupSelect.value);
    if (isNaN(idx) || idx < 0) return;
    const parsed = parse();
    if (parsed.length === 0) return;
    const subgroup = node.promptGroups[groupIndex]?.items?.[idx];
    if (!subgroup || subgroup.type !== 'prompt_subgroup') return;
    if (!Array.isArray(subgroup.items)) subgroup.items = [];
    parsed.forEach(({ text, weight }) => {
      subgroup.items.push({ type: 'prompt_tag', text, enabled: true, weight, random_candidate: false });
    });
    this.updateHiddenWidget(node);
    this.refreshItemsList(node, groupIndex);
    input.value = '';
  });

  importToNewBtn.addEventListener('click', () => {
    const parsed = parse();
    if (parsed.length === 0) return;
    const grp = node.promptGroups[groupIndex];
    if (!Array.isArray(grp.items)) grp.items = [];
    const newSub = {
      type: 'prompt_subgroup',
      name: `Imported subgroup ${Date.now()}`,
      enabled: true,
      weight: '1',
      random_candidate: false,
      items: [],
    };
    parsed.forEach(({ text, weight }) => {
      newSub.items.push({ type: 'prompt_tag', text, enabled: true, weight, random_candidate: false });
    });
    grp.items.push(newSub);
    this.updateHiddenWidget(node);
    this.refreshItemsList(node, groupIndex);
    input.value = '';
    // Refresh subgroup dropdown
    subgroupSelect.innerHTML = '';
    const def = document.createElement('option');
    def.value = '';
    def.textContent = 'Select subgroup';
    subgroupSelect.appendChild(def);
    grp.items.forEach((it, idx) => {
      if (it.type === 'prompt_subgroup') {
        const opt = document.createElement('option');
        opt.value = String(idx);
        opt.textContent = it.name || `Subgroup ${idx + 1}`;
        subgroupSelect.appendChild(opt);
      }
    });
  });

  return section;
}
