// Detailed Floating Window for Prompt Groups
// This file handles the secondary floating window with detailed group information

import { api } from '../../../scripts/api.js';
import { createItemsList } from './detailed_window_items.js';
import {
  createAddButtonsRow,
  createImportSection,
  createStatusSection,
  createTopSettingsRow,
} from './detailed_window_sections.js';

export class DetailedWindow {
  /**
   * Show the detailed floating window for a prompt group
   */
  static showDetailedWindow(node, groupData, groupIndex) {
    // Create the main window container
    const window = this.createWindow();

    // Create the header
    const header = this.createHeader(node, window, groupData.name || `Group ${groupIndex + 1}`);
    window.appendChild(header);

    // Create the content
    const content = this.createContent(node, groupData, groupIndex);
    window.appendChild(content);

    // Add to document
    document.body.appendChild(window);

    // Position the window
    this.positionWindow(window);

    // Make it draggable
    this.makeWindowDraggable(window, header);

    // Store reference
    node.detailedWindow = window;

    return window;
  }

  /**
   * Create the main window container
   */
  static createWindow() {
    const window = document.createElement('div');
    window.className = 'grouped-prompt-detailed-window';
    window.style.cssText = `
            position: fixed;
            z-index: 10000;
            background: #1b1b1b;
            border: 1px solid #2c2c2c;
            border-radius: 8px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            color: #ccc;
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            width: 640px;
            max-width: 95vw;
            height: 90vh;
            max-height: 95vh;
            min-width: 380px;
            min-height: 220px;
            display: flex;
            flex-direction: column;
            overflow: auto;
            resize: both;
        `;

    return window;
  }

  /**
   * Create the window header
   */
  static createHeader(node, window, title) {
    const header = document.createElement('div');
    header.className = 'detailed-window-header';
    header.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 16px;
            background: #0f0f0f;
            border-bottom: 1px solid #2c2c2c;
            border-radius: 8px 8px 0 0;
            cursor: move;
        `;

    // Title
    const titleElement = document.createElement('div');
    titleElement.className = 'detailed-window-title';
    titleElement.style.cssText = `
            color: #fff;
            font-size: 14px;
            font-weight: 500;
            margin: 0;
            user-select: none;
        `;
    titleElement.textContent = title;
    header.appendChild(titleElement);

    // Close button
    const closeBtn = this.createCloseButton(() => {
      window.remove();
      // After closing, refresh the main node list so name and other updates reflect
      import('./prompt_group_ui.js')
        .then(mod => {
          if (mod && mod.PromptGroupUI && typeof mod.PromptGroupUI.refreshPromptGroupsList === 'function') {
            mod.PromptGroupUI.refreshPromptGroupsList(node);
          }
        })
        .catch(() => {});
    });
    header.appendChild(closeBtn);

    return header;
  }

  /**
   * Create the window content
   */
  static createContent(node, groupData, groupIndex) {
    const content = document.createElement('div');
    content.className = 'detailed-window-content';
    content.style.cssText = `
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            scrollbar-width: thin;
            scrollbar-color: #2c2c2c #1b1b1b;
        `;

    // Top settings row (name + weight + random prompt #)
    const topSettings = createTopSettingsRow.call(this, node, groupData, groupIndex);
    content.appendChild(topSettings);

    // Shuffle options row (label + 3 buttons in one line)
    const statusSection = createStatusSection.call(this, node, groupData, groupIndex);
    content.appendChild(statusSection);

    // Import prompts from string section
    const importSection = createImportSection.call(this, node, groupData, groupIndex);
    content.appendChild(importSection);

    // Add buttons row (add tag + add subgroup on one line)
    const addButtonsRow = createAddButtonsRow.call(this, node, groupIndex);
    content.appendChild(addButtonsRow);

    // Items list
    const itemsList = createItemsList.call(this, node, groupData, groupIndex);
    content.appendChild(itemsList);

    return content;
  }

  /**
   * Create the group name editing section
   */
  static createTopSettingsRow(node, groupData, groupIndex) {
    const row = document.createElement('div');
    row.style.cssText = `
            display: grid;
            grid-template-columns: 1.2fr 0.6fr 0.6fr;
            gap: 8px;
            align-items: center;
            margin-bottom: 12px;
        `;

    // Group Name (labeled)
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

    // Group Weight (labeled)
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

    // Random prompt # (labeled)
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

  /**
   * Create the group weight section
   */
  static createWeightSection(node, groupData, groupIndex) {
    const section = document.createElement('div');
    section.className = 'weight-section';
    section.style.cssText = `
            margin-bottom: 16px;
        `;

    const label = document.createElement('label');
    label.textContent = 'Group Weight:';
    label.style.cssText = `
            display: block;
            color: #999;
            font-size: 12px;
            font-weight: 500;
            margin-bottom: 4px;
            text-transform: uppercase;
        `;
    section.appendChild(label);

    const input = document.createElement('input');
    input.type = 'text';
    input.value = groupData.weight || '1';
    input.placeholder = '1 or 0.5-1.5';
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

    input.addEventListener('input', e => {
      this.onGroupWeightChange(node, groupIndex, e.target.value);
    });

    section.appendChild(input);

    return section;
  }

  /**
   * Create a compact settings row with weight and random count side by side
   */
  static createCompactSettingsRow(node, groupData, groupIndex) {
    const row = document.createElement('div');
    row.style.cssText = `
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 16px;
        `;

    const weight = this.createWeightSection(node, groupData, groupIndex);
    const random = this.createRandomCountSection(node, groupData, groupIndex);
    weight.style.marginBottom = '0px';
    random.style.marginBottom = '0px';
    row.appendChild(weight);
    row.appendChild(random);
    return row;
  }

  /**
   * Create the random count section
   */
  static createRandomCountSection(node, groupData, groupIndex) {
    const section = document.createElement('div');
    section.className = 'random-count-section';
    section.style.cssText = `
            margin-bottom: 16px;
        `;

    const label = document.createElement('label');
    label.textContent = 'Random Count:';
    label.style.cssText = `
            display: block;
            color: #999;
            font-size: 12px;
            font-weight: 500;
            margin-bottom: 4px;
            text-transform: uppercase;
        `;
    section.appendChild(label);

    const input = document.createElement('input');
    input.type = 'text';
    input.value = groupData.random_count || '0';
    input.placeholder = '0 or 1-3';
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

    input.addEventListener('input', e => {
      this.onGroupRandomCountChange(node, groupIndex, e.target.value);
    });

    section.appendChild(input);

    return section;
  }

  /**
   * Create the status/shuffle section
   */
  static createStatusSection(node, groupData, groupIndex) {
    const section = document.createElement('div');
    section.className = 'status-section';
    section.style.cssText = `
            margin-bottom: 12px;
            display: grid;
            grid-template-columns: auto auto auto auto auto auto;
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

    // Default status button
    const defaultBtn = this.createStatusButton('No Shuffle', 'default', groupData.status === 'default', () => {
      this.onGroupStatusChange(node, groupIndex, 'default');
    });
    section.appendChild(defaultBtn);

    // Shuffle active button
    const shuffleActiveBtn = this.createStatusButton(
      'Shuffle Active',
      'shuffle_active',
      groupData.status === 'shuffle_active',
      () => {
        this.onGroupStatusChange(node, groupIndex, 'shuffle_active');
      },
    );
    section.appendChild(shuffleActiveBtn);

    // Shuffle all button
    const shuffleAllBtn = this.createStatusButton(
      'Shuffle All',
      'shuffle_all',
      groupData.status === 'shuffle_all',
      () => {
        this.onGroupStatusChange(node, groupIndex, 'shuffle_all');
      },
    );
    section.appendChild(shuffleAllBtn);

    // Bulk toggle: enable/disable top-level tags and subgroups (do not touch tags inside subgroups)
    const toggleEnableBtn = this.createStatusButton('Toggle Enable (Top-Level)', 'toggle_enable_top', false, () => {
      this.toggleTopLevelEnabled(node, groupIndex);
    });
    section.appendChild(toggleEnableBtn);

    // Bulk toggle: random flag for top-level tags and subgroups only
    const toggleRandomBtn = this.createStatusButton('Toggle Random (Top-Level)', 'toggle_random_top', false, () => {
      this.toggleTopLevelRandom(node, groupIndex);
    });
    section.appendChild(toggleRandomBtn);

    return section;
  }

  /**
   * Create a status button
   */
  static createStatusButton(text, value, isActive, onClick) {
    const button = document.createElement('button');
    button.textContent = text;
    button.style.cssText = `
            padding: 6px 12px;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            background: ${isActive ? '#8B5CF6' : '#232323'};
            color: ${isActive ? 'white' : '#999'};
            font-size: 11px;
            cursor: pointer;
            transition: all 0.2s;
        `;
    button.dataset.value = value; // Add dataset for easy state update

    button.addEventListener('click', onClick);

    return button;
  }

  /**
   * Toggle enabled state for top-level items (prompt_tag and prompt_subgroup) only
   * Does not modify tags within subgroups
   */
  static toggleTopLevelEnabled(node, groupIndex) {
    const group = node.promptGroups?.[groupIndex];
    if (!group || !Array.isArray(group.items)) return;
    // Determine target state: if any top-level item disabled -> enable all; else disable all
    const anyDisabled = group.items.some(
      it => (it.type === 'prompt_tag' || it.type === 'prompt_subgroup') && !it.enabled,
    );
    const target = anyDisabled ? true : false;
    group.items.forEach(it => {
      if (it.type === 'prompt_tag' || it.type === 'prompt_subgroup') {
        it.enabled = target;
      }
    });
    this.updateHiddenWidget(node);
    this.refreshItemsList(node, groupIndex);
  }

  /**
   * Toggle random_candidate for top-level items (prompt_tag and prompt_subgroup) only
   * Does not modify tags within subgroups
   */
  static toggleTopLevelRandom(node, groupIndex) {
    const group = node.promptGroups?.[groupIndex];
    if (!group || !Array.isArray(group.items)) return;
    // Determine target state: if any top-level item not random -> set all random; else clear all
    const anyNotRandom = group.items.some(
      it => (it.type === 'prompt_tag' || it.type === 'prompt_subgroup') && !it.random_candidate,
    );
    const target = anyNotRandom ? true : false;
    group.items.forEach(it => {
      if (it.type === 'prompt_tag' || it.type === 'prompt_subgroup') {
        it.random_candidate = target;
      }
    });
    this.updateHiddenWidget(node);
    this.refreshItemsList(node, groupIndex);
  }

  /**
   * Create the add tag button
   */
  static createAddTagButton(node, groupIndex) {
    const button = document.createElement('button');
    button.textContent = '+ Add Prompt Tag';
    button.style.cssText = `
            padding: 10px;
            background: #22C55E;
            border: none;
            border-radius: 6px;
            color: white;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        `;

    button.addEventListener('mouseenter', () => {
      button.style.background = '#16A34A';
    });

    button.addEventListener('mouseleave', () => {
      button.style.background = '#22C55E';
    });

    button.addEventListener('click', () => {
      this.addPromptTagToGroup(node, groupIndex);
    });

    return button;
  }

  /**
   * Create the add subgroup button
   */
  static createAddSubgroupButton(node, groupIndex) {
    const button = document.createElement('button');
    button.textContent = '+ Add Prompt Subgroup';
    button.style.cssText = `
            padding: 10px;
            background: #3B82F6;
            border: none;
            border-radius: 6px;
            color: white;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        `;

    button.addEventListener('mouseenter', () => {
      button.style.background = '#2563EB';
    });

    button.addEventListener('mouseleave', () => {
      button.style.background = '#3B82F6';
    });

    button.addEventListener('click', () => {
      this.addPromptSubgroupToGroup(node, groupIndex);
    });

    return button;
  }

  /**
   * Create a row containing the Add Tag and Add Subgroup buttons side by side
   */
  static createAddButtonsRow(node, groupIndex) {
    const row = document.createElement('div');
    row.style.cssText = `
            display: grid;
            grid-template-columns: 1fr 1fr auto;
            gap: 8px;
            margin-bottom: 16px;
        `;

    const addTagBtn = this.createAddTagButton(node, groupIndex);
    const addSubgroupBtn = this.createAddSubgroupButton(node, groupIndex);
    // Create a lightweight save template button placed on the same row
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
      // Find current group data by groupIndex
      if (node.promptGroups && node.promptGroups[groupIndex]) {
        this.saveGroupAsTemplate(node, node.promptGroups[groupIndex], groupIndex);
      }
    });

    row.appendChild(addTagBtn);
    row.appendChild(addSubgroupBtn);
    row.appendChild(saveBtn);

    return row;
  }

  /**
   * Create the items list
   */
  static createItemsList(node, groupData, groupIndex) {
    const container = document.createElement('div');
    container.className = 'items-list';
    container.style.cssText = `
            margin-bottom: 16px;
            display: flex;
            flex-direction: column;
            height: 100%;
        `;

    const label = document.createElement('div');
    label.textContent = 'Items:';
    label.style.cssText = `
            color: #999;
            font-size: 12px;
            font-weight: 500;
            margin-bottom: 8px;
            text-transform: uppercase;
        `;
    container.appendChild(label);

    const itemsContainer = document.createElement('div');
    itemsContainer.className = 'items-container';
    itemsContainer.style.cssText = `
            flex: 1;
            overflow-y: auto;
            border: 1px solid #2c2c2c;
            border-radius: 6px;
            padding: 8px;
            background: #232323;
            display: flex;
            flex-direction: column;
        `;

    if (groupData.items && Array.isArray(groupData.items)) {
      groupData.items.forEach((item, itemIndex) => {
        if (item.type === 'prompt_tag') {
          const tagItem = this.createTagListItem(node, groupIndex, itemIndex, item);
          itemsContainer.appendChild(tagItem);
        } else if (item.type === 'prompt_subgroup') {
          const subgroupItem = this.createSubgroupListItem(node, groupIndex, itemIndex, item);
          itemsContainer.appendChild(subgroupItem);
        }
      });
    }

    container.appendChild(itemsContainer);
    return container;
  }

  /**
   * Create a tag list item
   */
  static createTagListItem(node, groupIndex, itemIndex, tagData) {
    // Card container (vertical)
    const card = document.createElement('div');
    card.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 6px;
            padding: 8px;
            background: #2a2a2a;
            border-radius: 4px;
            margin-bottom: 4px;
            border: 1px solid #363636;
        `;
    const item = document.createElement('div');
    item.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
        `;

    // Toggle button
    const toggleBtn = document.createElement('button');
    toggleBtn.textContent = tagData.enabled ? '✓' : '✗';
    toggleBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: ${tagData.enabled ? '#22C55E' : '#6B7280'};
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    toggleBtn.addEventListener('click', () => {
      tagData.enabled = !tagData.enabled;
      toggleBtn.textContent = tagData.enabled ? '✓' : '✗';
      toggleBtn.style.background = tagData.enabled ? '#22C55E' : '#6B7280';
      this.updateHiddenWidget(node);
    });
    item.appendChild(toggleBtn);

    // Up/down move buttons
    const moveUpBtn = document.createElement('button');
    moveUpBtn.textContent = '↑';
    moveUpBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: #6B7280;
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    moveUpBtn.addEventListener('click', () => {
      this.moveItemInGroup(node, groupIndex, itemIndex, 'up');
    });
    item.appendChild(moveUpBtn);

    const moveDownBtn = document.createElement('button');
    moveDownBtn.textContent = '↓';
    moveDownBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: #6B7280;
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    moveDownBtn.addEventListener('click', () => {
      this.moveItemInGroup(node, groupIndex, itemIndex, 'down');
    });
    item.appendChild(moveDownBtn);

    // Text input with collapsible multiline (textarea placed below row for full width)
    const dropdownBtn = document.createElement('button');
    dropdownBtn.textContent = '▾';
    dropdownBtn.title = 'Expand/Collapse';
    dropdownBtn.style.cssText = `
            width: 24px;
            height: 24px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: #4B5563;
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;

    const singleInput = document.createElement('input');
    singleInput.type = 'text';
    singleInput.value = tagData.text || '';
    singleInput.placeholder = 'Enter prompt text...';
    singleInput.style.cssText = `
            flex: 1;
            background: #1a1a1a;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            padding: 6px;
            color: #ccc;
            font-size: 12px;
        `;
    singleInput.addEventListener('blur', () => {
      tagData.text = singleInput.value.trim();
      this.updateHiddenWidget(node);
    });
    item.appendChild(singleInput);

    const expandContainer = document.createElement('div');
    expandContainer.style.cssText = `display:none;`;
    const multiInput = document.createElement('textarea');
    multiInput.value = tagData.text || '';
    multiInput.placeholder = 'Enter prompt text...';
    multiInput.style.cssText = `
            width: 100%;
            min-height: 100px;
            background: #1a1a1a;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            padding: 6px;
            color: #ccc;
            font-size: 12px;
            resize: vertical;
        `;
    multiInput.addEventListener('blur', () => {
      tagData.text = multiInput.value.trim();
      this.updateHiddenWidget(node);
    });
    expandContainer.appendChild(multiInput);

    // Insert dropdown toggle right before the input(s)
    item.insertBefore(dropdownBtn, singleInput);

    dropdownBtn.addEventListener('click', () => {
      const expanding = expandContainer.style.display === 'none';
      if (expanding) {
        // Decode literal \n into real newlines when expanding
        const stored = (tagData.text ?? singleInput.value ?? '').toString();
        multiInput.value = stored.replace(/\\n/g, '\n');
        expandContainer.style.display = 'block';
        singleInput.style.display = 'none';
      } else {
        // Encode real newlines into literal \n when collapsing
        const encoded = (multiInput.value || '').replace(/\r?\n/g, '\\n');
        tagData.text = encoded;
        this.updateHiddenWidget(node);
        expandContainer.style.display = 'none';
        singleInput.style.display = 'block';
        // Show the encoded string in the single-line input
        singleInput.value = encoded;
      }
    });

    // Right-aligned controls container
    const rightControls = document.createElement('div');
    rightControls.style.cssText = `
            margin-left: auto;
            display: flex;
            align-items: center;
            gap: 8px;
        `;
    // Weight input
    const weightInput = document.createElement('input');
    weightInput.type = 'text';
    weightInput.value = tagData.weight || '1';
    weightInput.placeholder = '1';
    weightInput.style.cssText = `
            width: 60px;
            background: #1a1a1a;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            padding: 6px;
            color: #ccc;
            font-size: 11px;
            text-align: center;
        `;
    weightInput.addEventListener('blur', () => {
      tagData.weight = weightInput.value.trim();
      this.updateHiddenWidget(node);
    });
    rightControls.appendChild(weightInput);

    // Random candidate toggle
    const randomToggle = document.createElement('button');
    randomToggle.textContent = tagData.random_candidate ? 'R' : 'r';
    randomToggle.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 50%;
            border: 1px solid #2c2c2c;
            background: ${tagData.random_candidate ? '#8B5CF6' : '#6B7280'};
            color: white;
            cursor: pointer;
            font-size: 10px;
        `;
    randomToggle.addEventListener('click', () => {
      tagData.random_candidate = !tagData.random_candidate;
      randomToggle.textContent = tagData.random_candidate ? 'R' : 'r';
      randomToggle.style.background = tagData.random_candidate ? '#8B5CF6' : '#6B7280';
      this.updateHiddenWidget(node);
    });
    rightControls.appendChild(randomToggle);

    // Move to subgroup dropdown
    const moveDropdown = document.createElement('select');
    moveDropdown.style.cssText = `
            width: 140px;
            min-width: 140px;
            max-width: 140px;
            background: #1a1a1a;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            padding: 4px;
            color: #ccc;
            font-size: 10px;
        `;

    // Add default option
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = 'Move to...';
    moveDropdown.appendChild(defaultOption);

    // Add current group option
    const currentGroupOption = document.createElement('option');
    currentGroupOption.value = `group_${groupIndex}`;
    currentGroupOption.textContent = 'Current Group';
    moveDropdown.appendChild(currentGroupOption);

    // Add subgroup options if they exist
    if (node.promptGroups && node.promptGroups[groupIndex] && node.promptGroups[groupIndex].items) {
      node.promptGroups[groupIndex].items.forEach((item, itemIndex) => {
        if (item.type === 'prompt_subgroup') {
          const option = document.createElement('option');
          option.value = `subgroup_${groupIndex}_${itemIndex}`;
          option.textContent = `→ ${item.name || `Subgroup ${itemIndex + 1}`}`;
          moveDropdown.appendChild(option);
        }
      });
    }

    moveDropdown.addEventListener('change', e => {
      if (e.target.value) {
        // Recompute current index to avoid stale closures after list mutations
        const items = node.promptGroups?.[groupIndex]?.items || [];
        const currentIndex = items.indexOf(tagData);
        const safeIndex = currentIndex >= 0 ? currentIndex : itemIndex;
        this.movePromptItem(node, groupIndex, safeIndex, e.target.value);
        moveDropdown.value = ''; // Reset selection
      }
    });
    rightControls.appendChild(moveDropdown);

    // Remove button
    const removeBtn = document.createElement('button');
    removeBtn.textContent = '×';
    removeBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #EF4444;
            background: #EF4444;
            color: white;
            cursor: pointer;
            font-size: 14px;
        `;
    removeBtn.addEventListener('click', () => {
      this.removeItemFromGroup(node, groupIndex, itemIndex);
    });
    rightControls.appendChild(removeBtn);

    // Mount right controls
    item.appendChild(rightControls);

    // Assemble
    card.appendChild(item);
    card.appendChild(expandContainer);
    return card;
  }

  /**
   * Create a subgroup list item
   */
  static createSubgroupListItem(node, groupIndex, itemIndex, subgroupData) {
    const item = document.createElement('div');
    item.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 8px;
            padding: 8px;
            background: #2a2a2a;
            border-radius: 4px;
            margin-bottom: 4px;
            border: 1px solid #363636;
        `;

    // Header row
    const headerRow = document.createElement('div');
    headerRow.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
        `;

    // Toggle button moved to leftmost
    const toggleBtn = document.createElement('button');
    toggleBtn.textContent = subgroupData.enabled ? '✓' : '✗';
    toggleBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: ${subgroupData.enabled ? '#22C55E' : '#6B7280'};
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    toggleBtn.addEventListener('click', () => {
      subgroupData.enabled = !subgroupData.enabled;
      toggleBtn.textContent = subgroupData.enabled ? '✓' : '✗';
      toggleBtn.style.background = subgroupData.enabled ? '#22C55E' : '#6B7280';
      this.updateHiddenWidget(node);
    });
    headerRow.appendChild(toggleBtn);

    // Move up/down buttons for subgroup
    const sgMoveUpBtn = document.createElement('button');
    sgMoveUpBtn.textContent = '↑';
    sgMoveUpBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: #6B7280;
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    sgMoveUpBtn.addEventListener('click', () => {
      this.moveItemInGroup(node, groupIndex, itemIndex, 'up');
    });
    headerRow.appendChild(sgMoveUpBtn);

    const sgMoveDownBtn = document.createElement('button');
    sgMoveDownBtn.textContent = '↓';
    sgMoveDownBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: #6B7280;
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    sgMoveDownBtn.addEventListener('click', () => {
      this.moveItemInGroup(node, groupIndex, itemIndex, 'down');
    });
    headerRow.appendChild(sgMoveDownBtn);

    // Collapse/expand toggle
    const collapseBtn = document.createElement('button');
    collapseBtn.textContent = '▸';
    collapseBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: #4B5563;
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    headerRow.appendChild(collapseBtn);

    // Name input
    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.value = subgroupData.name || '';
    nameInput.placeholder = 'Enter subgroup name...';
    nameInput.style.cssText = `
            flex: 1;
            background: #1a1a1a;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            padding: 6px;
            color: #ccc;
            font-size: 12px;
        `;
    nameInput.addEventListener('blur', () => {
      subgroupData.name = nameInput.value.trim();
      this.updateHiddenWidget(node);
    });
    headerRow.appendChild(nameInput);

    // Weight input
    const weightInput = document.createElement('input');
    weightInput.type = 'text';
    weightInput.value = subgroupData.weight || '1';
    weightInput.placeholder = '1';
    weightInput.style.cssText = `
            width: 60px;
            background: #1a1a1a;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            padding: 6px;
            color: #ccc;
            font-size: 11px;
            text-align: center;
        `;
    weightInput.addEventListener('blur', () => {
      subgroupData.weight = weightInput.value.trim();
      this.updateHiddenWidget(node);
    });
    headerRow.appendChild(weightInput);

    // Random candidate toggle
    const randomToggle = document.createElement('button');
    randomToggle.textContent = subgroupData.random_candidate ? 'R' : 'r';
    randomToggle.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 50%;
            border: 1px solid #2c2c2c;
            background: ${subgroupData.random_candidate ? '#8B5CF6' : '#6B7280'};
            color: white;
            cursor: pointer;
            font-size: 10px;
        `;
    randomToggle.addEventListener('click', () => {
      subgroupData.random_candidate = !subgroupData.random_candidate;
      randomToggle.textContent = subgroupData.random_candidate ? 'R' : 'r';
      randomToggle.style.background = subgroupData.random_candidate ? '#8B5CF6' : '#6B7280';
      this.updateHiddenWidget(node);
    });
    headerRow.appendChild(randomToggle);

    // Add tag button moved into header (one-line subgroup header)
    const addTagBtn = document.createElement('button');
    addTagBtn.textContent = '+ Tag';
    addTagBtn.style.cssText = `
            padding: 4px 8px;
            background: #059669;
            border: none;
            border-radius: 4px;
            color: white;
            font-size: 11px;
            cursor: pointer;
        `;
    addTagBtn.addEventListener('click', () => {
      this.addPromptTagToSubgroup(node, groupIndex, itemIndex);
    });
    headerRow.appendChild(addTagBtn);

    // Remove button
    const removeBtn = document.createElement('button');
    removeBtn.textContent = '×';
    removeBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #EF4444;
            background: #EF4444;
            color: white;
            cursor: pointer;
            font-size: 14px;
        `;
    removeBtn.addEventListener('click', () => {
      this.removeItemFromGroup(node, groupIndex, itemIndex);
    });
    headerRow.appendChild(removeBtn);

    item.appendChild(headerRow);

    // Dropdown container for subgroup tags
    const dropdownContainer = document.createElement('div');
    dropdownContainer.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 6px;
            border-top: 1px dashed #3a3a3a;
            padding-top: 8px;
            margin-top: 4px;
        `;

    // Render existing tags vertically
    const renderTags = () => {
      dropdownContainer.innerHTML = '';
      const tags = subgroupData.items && Array.isArray(subgroupData.items) ? subgroupData.items : [];
      tags.forEach((tag, tagIndex) => {
        const tagItem = this.createSubgroupTagItem(node, groupIndex, itemIndex, tagIndex, tag);
        dropdownContainer.appendChild(tagItem);
      });
    };

    renderTags();
    item.appendChild(dropdownContainer);

    // Persisted dropdown open/close state per subgroup object
    if (subgroupData._expanded === undefined) subgroupData._expanded = true;
    const applyExpanded = () => {
      dropdownContainer.style.display = subgroupData._expanded ? 'flex' : 'none';
      collapseBtn.textContent = subgroupData._expanded ? '▾' : '▸';
    };
    applyExpanded();

    // Toggle dropdown on button click, do not auto-collapse otherwise
    collapseBtn.addEventListener('click', () => {
      subgroupData._expanded = !subgroupData._expanded;
      applyExpanded();
    });

    return item;
  }

  /**
   * Create a tag item inside a subgroup (vertical layout)
   */
  static createSubgroupTagItem(node, groupIndex, subgroupIndex, tagIndex, tagData) {
    // Card container (vertical)
    const card = document.createElement('div');
    card.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 6px;
            padding: 6px;
            background: #1f1f1f;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
        `;
    const item = document.createElement('div');
    item.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
        `;

    // Toggle
    const toggleBtn = document.createElement('button');
    toggleBtn.textContent = tagData.enabled ? '✓' : '✗';
    toggleBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: ${tagData.enabled ? '#22C55E' : '#6B7280'};
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    toggleBtn.addEventListener('click', () => {
      tagData.enabled = !tagData.enabled;
      toggleBtn.textContent = tagData.enabled ? '✓' : '✗';
      toggleBtn.style.background = tagData.enabled ? '#22C55E' : '#6B7280';
      this.updateHiddenWidget(node);
    });
    item.appendChild(toggleBtn);

    // Up/down move
    const moveUpBtn = document.createElement('button');
    moveUpBtn.textContent = '↑';
    moveUpBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: #6B7280;
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    moveUpBtn.addEventListener('click', () => {
      this.moveTagInSubgroup(node, groupIndex, subgroupIndex, tagIndex, 'up');
    });
    item.appendChild(moveUpBtn);

    const moveDownBtn = document.createElement('button');
    moveDownBtn.textContent = '↓';
    moveDownBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: #6B7280;
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    moveDownBtn.addEventListener('click', () => {
      this.moveTagInSubgroup(node, groupIndex, subgroupIndex, tagIndex, 'down');
    });
    item.appendChild(moveDownBtn);

    // Expand/collapse button
    const expandBtn = document.createElement('button');
    expandBtn.textContent = '▾';
    expandBtn.title = 'Expand/Collapse';
    expandBtn.style.cssText = `
            width: 24px;
            height: 24px;
            border-radius: 4px;
            border: 1px solid #2c2c2c;
            background: #4B5563;
            color: white;
            cursor: pointer;
            font-size: 12px;
        `;
    item.appendChild(expandBtn);

    // Text input
    const textInput = document.createElement('input');
    textInput.type = 'text';
    textInput.value = tagData.text || '';
    textInput.placeholder = 'Enter prompt text...';
    textInput.style.cssText = `
            flex: 1;
            background: #1a1a1a;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            padding: 6px;
            color: #ccc;
            font-size: 12px;
        `;
    textInput.addEventListener('blur', () => {
      tagData.text = textInput.value.trim();
      this.updateHiddenWidget(node);
    });
    item.appendChild(textInput);

    // Expandable container below the row
    const expandContainer = document.createElement('div');
    expandContainer.style.cssText = `display:none;`;
    const multiArea = document.createElement('textarea');
    multiArea.value = tagData.text || '';
    multiArea.placeholder = 'Enter prompt text...';
    multiArea.style.cssText = `
            width: 100%;
            min-height: 100px;
            background: #1a1a1a;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            padding: 6px;
            color: #ccc;
            font-size: 12px;
            resize: vertical;
        `;
    multiArea.addEventListener('blur', () => {
      tagData.text = multiArea.value.trim();
      this.updateHiddenWidget(node);
    });
    expandContainer.appendChild(multiArea);

    expandBtn.addEventListener('click', () => {
      const expanding = expandContainer.style.display === 'none';
      if (expanding) {
        const stored = (tagData.text ?? textInput.value ?? '').toString();
        multiArea.value = stored.replace(/\\n/g, '\n');
        expandContainer.style.display = 'block';
        textInput.style.display = 'none';
      } else {
        const encoded = (multiArea.value || '').replace(/\r?\n/g, '\\n');
        tagData.text = encoded;
        this.updateHiddenWidget(node);
        expandContainer.style.display = 'none';
        textInput.style.display = 'block';
        textInput.value = encoded;
      }
    });

    // Right-aligned controls container
    const rightControls = document.createElement('div');
    rightControls.style.cssText = `
            margin-left: auto;
            display: flex;
            align-items: center;
            gap: 8px;
        `;

    // Weight input
    const weightInput = document.createElement('input');
    weightInput.type = 'text';
    weightInput.value = tagData.weight || '1';
    weightInput.placeholder = '1';
    weightInput.style.cssText = `
            width: 60px;
            background: #1a1a1a;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            padding: 6px;
            color: #ccc;
            font-size: 11px;
            text-align: center;
        `;
    weightInput.addEventListener('blur', () => {
      tagData.weight = weightInput.value.trim();
      this.updateHiddenWidget(node);
    });
    rightControls.appendChild(weightInput);

    // Random toggle
    const randomToggle = document.createElement('button');
    randomToggle.textContent = tagData.random_candidate ? 'R' : 'r';
    randomToggle.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 50%;
            border: 1px solid #2c2c2c;
            background: ${tagData.random_candidate ? '#8B5CF6' : '#6B7280'};
            color: white;
            cursor: pointer;
            font-size: 10px;
        `;
    randomToggle.addEventListener('click', () => {
      tagData.random_candidate = !tagData.random_candidate;
      randomToggle.textContent = tagData.random_candidate ? 'R' : 'r';
      randomToggle.style.background = tagData.random_candidate ? '#8B5CF6' : '#6B7280';
      this.updateHiddenWidget(node);
    });
    rightControls.appendChild(randomToggle);

    // Move to subgroup dropdown (within current group)
    const moveDropdown = document.createElement('select');
    moveDropdown.style.cssText = `
            background: #1a1a1a;
            border: 1px solid #2c2c2c;
            border-radius: 4px;
            color: #ccc;
            padding: 4px;
            font-size: 10px;
            width: 140px;
            min-width: 140px;
            max-width: 140px;
        `;
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = 'Move to...';
    moveDropdown.appendChild(defaultOption);
    const currentGroupOption = document.createElement('option');
    currentGroupOption.value = `group_${groupIndex}`;
    currentGroupOption.textContent = 'Current Group';
    moveDropdown.appendChild(currentGroupOption);
    const group = node.promptGroups?.[groupIndex];
    if (group?.items) {
      group.items.forEach((it, idx) => {
        if (it.type === 'prompt_subgroup') {
          const opt = document.createElement('option');
          opt.value = `subgroup_${groupIndex}_${idx}`;
          opt.textContent = `→ ${it.name || `Subgroup ${idx + 1}`}`;
          moveDropdown.appendChild(opt);
        }
      });
    }
    moveDropdown.addEventListener('change', e => {
      if (!e.target.value) return;
      // Extract the tag from current subgroup and move
      const subgroup = node.promptGroups?.[groupIndex]?.items?.[subgroupIndex];
      if (!subgroup || subgroup.type !== 'prompt_subgroup' || !Array.isArray(subgroup.items)) return;
      const itemToMove = subgroup.items.splice(tagIndex, 1)[0];
      if (!itemToMove) return;
      if (e.target.value.startsWith('group_')) {
        const tgtGroupIdx = parseInt(e.target.value.split('_')[1]);
        const tgtGroup = node.promptGroups?.[tgtGroupIdx];
        if (tgtGroup) {
          if (!Array.isArray(tgtGroup.items)) tgtGroup.items = [];
          tgtGroup.items.push(itemToMove);
        }
      } else if (e.target.value.startsWith('subgroup_')) {
        const parts = e.target.value.split('_');
        const tgtGroupIdx = parseInt(parts[1]);
        const tgtSubIdx = parseInt(parts[2]);
        const tgtSub = node.promptGroups?.[tgtGroupIdx]?.items?.[tgtSubIdx];
        if (tgtSub && tgtSub.type === 'prompt_subgroup') {
          if (!Array.isArray(tgtSub.items)) tgtSub.items = [];
          tgtSub.items.push(itemToMove);
        }
      }
      this.updateHiddenWidget(node);
      this.refreshItemsList(node, groupIndex);
      moveDropdown.value = '';
    });
    rightControls.appendChild(moveDropdown);

    // Remove
    const removeBtn = document.createElement('button');
    removeBtn.textContent = '×';
    removeBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 1px solid #EF4444;
            background: #EF4444;
            color: white;
            cursor: pointer;
            font-size: 14px;
        `;
    removeBtn.addEventListener('click', () => {
      this.removeTagFromSubgroup(node, groupIndex, subgroupIndex, tagIndex);
    });
    rightControls.appendChild(removeBtn);

    // Mount right controls
    item.appendChild(rightControls);

    // Assemble
    card.appendChild(item);
    card.appendChild(expandContainer);

    return card;
  }

  static moveTagInSubgroup(node, groupIndex, subgroupIndex, tagIndex, direction) {
    const group = node.promptGroups?.[groupIndex];
    const subgroup = group?.items?.[subgroupIndex];
    if (!subgroup || subgroup.type !== 'prompt_subgroup' || !Array.isArray(subgroup.items)) return;
    const items = subgroup.items;
    if (direction === 'up' && tagIndex > 0) {
      [items[tagIndex], items[tagIndex - 1]] = [items[tagIndex - 1], items[tagIndex]];
    } else if (direction === 'down' && tagIndex < items.length - 1) {
      [items[tagIndex], items[tagIndex + 1]] = [items[tagIndex + 1], items[tagIndex]];
    } else {
      return;
    }
    this.updateHiddenWidget(node);
    this.refreshItemsList(node, groupIndex);
  }

  static removeTagFromSubgroup(node, groupIndex, subgroupIndex, tagIndex) {
    const group = node.promptGroups?.[groupIndex];
    const subgroup = group?.items?.[subgroupIndex];
    if (!subgroup || subgroup.type !== 'prompt_subgroup' || !Array.isArray(subgroup.items)) return;
    subgroup.items.splice(tagIndex, 1);
    this.updateHiddenWidget(node);
    this.refreshItemsList(node, groupIndex);
  }

  /**
   * Create the save template button
   */
  static createSaveTemplateButton(node, groupData, groupIndex) {
    const button = document.createElement('button');
    button.textContent = '💾 Save as Template';
    button.style.cssText = `
            padding: 12px;
            background: #F59E0B;
            border: none;
            border-radius: 6px;
            color: white;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        `;

    button.addEventListener('mouseenter', () => {
      button.style.background = '#D97706';
    });

    button.addEventListener('mouseleave', () => {
      button.style.background = '#F59E0B';
    });

    button.addEventListener('click', () => {
      this.saveGroupAsTemplate(node, groupData, groupIndex);
    });

    return button;
  }

  /**
   * Create the close button
   */
  static createCloseButton(onClick) {
    const button = document.createElement('button');
    button.textContent = '×';
    button.style.cssText = `
            background: none;
            border: none;
            color: #999;
            font-size: 18px;
            cursor: pointer;
            padding: 0;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
        `;
    button.addEventListener('click', onClick);
    return button;
  }

  // Event Handlers

  /**
   * Handle group name change
   */
  static onGroupNameChange(node, groupIndex, newName) {
    if (node.promptGroups && node.promptGroups[groupIndex]) {
      node.promptGroups[groupIndex].name = newName;
      this.updateHiddenWidget(node);
    }
  }

  /**
   * Handle group weight change
   */
  static onGroupWeightChange(node, groupIndex, newWeight) {
    if (node.promptGroups && node.promptGroups[groupIndex]) {
      node.promptGroups[groupIndex].weight = newWeight;
      this.updateHiddenWidget(node);
    }
  }

  /**
   * Handle group random count change
   */
  static onGroupRandomCountChange(node, groupIndex, newCount) {
    if (node.promptGroups && node.promptGroups[groupIndex]) {
      node.promptGroups[groupIndex].random_count = newCount;
      this.updateHiddenWidget(node);
    }
  }

  /**
   * Move an item up or down within a group
   */
  static moveItemInGroup(node, groupIndex, itemIndex, direction) {
    if (node.promptGroups && node.promptGroups[groupIndex] && node.promptGroups[groupIndex].items) {
      const items = node.promptGroups[groupIndex].items;

      if (direction === 'up' && itemIndex > 0) {
        [items[itemIndex], items[itemIndex - 1]] = [items[itemIndex - 1], items[itemIndex]];
        this.updateHiddenWidget(node);
        this.refreshItemsList(node, groupIndex);
      } else if (direction === 'down' && itemIndex < items.length - 1) {
        [items[itemIndex], items[itemIndex + 1]] = [items[itemIndex + 1], items[itemIndex]];
        this.updateHiddenWidget(node);
        this.refreshItemsList(node, groupIndex);
      }
    }
  }

  /**
   * Move a prompt item to a different group or subgroup
   */
  static movePromptItem(node, groupIndex, itemIndex, target) {
    if (!node.promptGroups || !node.promptGroups[groupIndex] || !node.promptGroups[groupIndex].items) {
      return;
    }

    const sourceItems = node.promptGroups[groupIndex].items;
    const itemToMove = sourceItems[itemIndex];

    if (!itemToMove) return;

    // Determine destination BEFORE mutating source to avoid index shift issues
    let destination = null;
    if (target.startsWith('subgroup_')) {
      // Move to subgroup
      const parts = target.split('_');
      const targetGroupIndex = parseInt(parts[1]);
      let targetSubgroupIndex = parseInt(parts[2]);

      // Capture destination pointer prior to source splice
      const targetGroup = node.promptGroups[targetGroupIndex];
      const preRemovalTargetSub = targetGroup?.items?.[targetSubgroupIndex];
      if (preRemovalTargetSub && preRemovalTargetSub.type === 'prompt_subgroup') {
        destination = preRemovalTargetSub;
      }

      // Now remove from source
      sourceItems.splice(itemIndex, 1);

      if (destination) {
        if (!Array.isArray(destination.items)) destination.items = [];
        destination.items.push(itemToMove);
      }
    } else if (target.startsWith('group_')) {
      // Move to group level
      const targetGroupIndex = parseInt(target.split('_')[1]);
      const targetGroup = node.promptGroups[targetGroupIndex];
      // Remove first to avoid duplication
      sourceItems.splice(itemIndex, 1);
      if (targetGroup) {
        if (!Array.isArray(targetGroup.items)) targetGroup.items = [];
        targetGroup.items.push(itemToMove);
      }
    }

    this.updateHiddenWidget(node);
    this.refreshItemsList(node, groupIndex);
  }

  /**
   * Handle group status change
   */
  static onGroupStatusChange(node, groupIndex, newStatus) {
    if (node.promptGroups && node.promptGroups[groupIndex]) {
      node.promptGroups[groupIndex].status = newStatus;
      this.updateHiddenWidget(node);

      // Update button states
      const statusSection = document.querySelector('.status-section');
      if (statusSection) {
        const buttons = statusSection.querySelectorAll('button');
        buttons.forEach(btn => {
          if (btn.dataset.value === newStatus) {
            btn.style.background = '#8B5CF6';
            btn.style.color = 'white';
          } else {
            btn.style.background = '#232323';
            btn.style.color = '#999';
          }
        });
      }
    }
  }

  // Utility Methods

  /**
   * Add a prompt tag to a group
   */
  static addPromptTagToGroup(node, groupIndex) {
    if (node.promptGroups && node.promptGroups[groupIndex]) {
      const newTag = {
        type: 'prompt_tag',
        text: 'New prompt',
        enabled: true,
        weight: '1',
        random_candidate: false,
      };

      if (!node.promptGroups[groupIndex].items) {
        node.promptGroups[groupIndex].items = [];
      }
      node.promptGroups[groupIndex].items.push(newTag);

      this.updateHiddenWidget(node);
      this.refreshItemsList(node, groupIndex);
    }
  }

  /**
   * Add a prompt subgroup to a group
   */
  static addPromptSubgroupToGroup(node, groupIndex) {
    if (node.promptGroups && node.promptGroups[groupIndex]) {
      const newSubgroup = {
        type: 'prompt_subgroup',
        name: 'New subgroup',
        enabled: true,
        weight: '1',
        random_candidate: false,
        items: [],
      };

      if (!node.promptGroups[groupIndex].items) {
        node.promptGroups[groupIndex].items = [];
      }
      node.promptGroups[groupIndex].items.push(newSubgroup);

      this.updateHiddenWidget(node);
      this.refreshItemsList(node, groupIndex);
    }
  }

  /**
   * Add a prompt tag to a subgroup
   */
  static addPromptTagToSubgroup(node, groupIndex, subgroupIndex) {
    if (
      node.promptGroups &&
      node.promptGroups[groupIndex] &&
      node.promptGroups[groupIndex].items &&
      node.promptGroups[groupIndex].items[subgroupIndex] &&
      node.promptGroups[groupIndex].items[subgroupIndex].type === 'prompt_subgroup'
    ) {
      const newTag = {
        type: 'prompt_tag',
        text: 'New prompt',
        enabled: true,
        weight: '1',
        random_candidate: false,
      };

      if (!node.promptGroups[groupIndex].items[subgroupIndex].items) {
        node.promptGroups[groupIndex].items[subgroupIndex].items = [];
      }
      node.promptGroups[groupIndex].items[subgroupIndex].items.push(newTag);

      this.updateHiddenWidget(node);
      this.refreshItemsList(node, groupIndex);
    }
  }

  /**
   * Remove an item from a group
   */
  static removeItemFromGroup(node, groupIndex, itemIndex) {
    if (node.promptGroups && node.promptGroups[groupIndex] && node.promptGroups[groupIndex].items) {
      node.promptGroups[groupIndex].items.splice(itemIndex, 1);
      this.updateHiddenWidget(node);
      this.refreshItemsList(node, groupIndex);
    }
  }

  /**
   * Save group as template
   */
  static saveGroupAsTemplate(node, groupData, groupIndex) {
    const templateName = (groupData.name || `Group_${groupIndex + 1}`).trim();
    if (!templateName) return;

    const performSave = async override => {
      try {
        const payload = { name: templateName, data: groupData };
        const url = `/xyz/grouped_prompt/template${override ? '?override=true' : ''}`;
        const res = await api.fetchApi(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (res.status === 409) {
          // Exists: ask user using ComfyUI dialog API; ensure dialog is above window
          const wnd = node.detailedWindow;
          const oldZ = wnd?.style?.zIndex;
          if (wnd) wnd.style.zIndex = '1';
          const result = await app.extensionManager.dialog.confirm({
            title: 'Confirm overwrite',
            message: `Template "${templateName}" already exists. Override?`,
            type: 'overwrite',
          });
          if (wnd && oldZ !== undefined) wnd.style.zIndex = oldZ;
          if (result) await performSave(true);
          return;
        }
        if (!res.ok) {
          const msg = await res.text();
          const wnd = node.detailedWindow;
          const oldZ = wnd?.style?.zIndex;
          if (wnd) wnd.style.zIndex = '1';
          await app.extensionManager.dialog.confirm({
            title: 'Save failed',
            message: String(msg || 'Unknown error'),
            type: 'default',
          });
          if (wnd && oldZ !== undefined) wnd.style.zIndex = oldZ;
          return;
        }
        // Success dialog and refresh the template dropdown if present
        const wnd = node.detailedWindow;
        const oldZ = wnd?.style?.zIndex;
        if (wnd) wnd.style.zIndex = '1';
        await app.extensionManager.dialog.confirm({
          title: 'Saved',
          message: `Template "${templateName}" saved successfully!`,
          type: 'default',
        });
        if (wnd && oldZ !== undefined) wnd.style.zIndex = oldZ;
        // Refresh dropdown in main node header if available
        if (node && typeof node.refreshTemplateDropdown === 'function') {
          await node.refreshTemplateDropdown();
        }
      } catch (error) {
        console.error('Error saving template:', error);
        const wnd = node.detailedWindow;
        const oldZ = wnd?.style?.zIndex;
        if (wnd) wnd.style.zIndex = '1';
        await app.extensionManager.dialog.confirm({
          title: 'Error',
          message: 'Error saving template. Please try again.',
          type: 'default',
        });
        if (wnd && oldZ !== undefined) wnd.style.zIndex = oldZ;
      }
    };

    performSave(false);
  }

  /**
   * Create import section for tags/subgroups
   */
  static createImportSection(node, groupData, groupIndex) {
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

    // Controls row for import actions
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

    // Subgroup selector
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
    defaultOpt.textContent = groupData.items?.some(it => it.type === 'prompt_subgroup')
      ? 'Select subgroup'
      : 'No subgroups';
    subgroupSelect.appendChild(defaultOpt);
    if (Array.isArray(groupData.items)) {
      groupData.items.forEach((it, idx) => {
        if (it.type === 'prompt_subgroup') {
          const opt = document.createElement('option');
          opt.value = String(idx);
          opt.textContent = it.name || `Subgroup ${idx + 1}`;
          subgroupSelect.appendChild(opt);
        }
      });
    }

    controlsRow.appendChild(importToGroupBtn);
    controlsRow.appendChild(importToExistingBtn);
    controlsRow.appendChild(subgroupSelect);
    controlsRow.appendChild(importToNewBtn);
    section.appendChild(controlsRow);

    const parse = () => this.parseImportString(input.value || '');

    importToGroupBtn.addEventListener('click', () => {
      const items = parse();
      if (items.length === 0) return;
      if (!Array.isArray(node.promptGroups[groupIndex].items)) node.promptGroups[groupIndex].items = [];
      items.forEach(({ text, weight }) => {
        node.promptGroups[groupIndex].items.push({
          type: 'prompt_tag',
          text,
          enabled: true,
          weight,
          random_candidate: false,
        });
      });
      this.updateHiddenWidget(node);
      this.refreshItemsList(node, groupIndex);
      input.value = '';
    });

    importToExistingBtn.addEventListener('click', () => {
      const idxStr = subgroupSelect.value;
      const idx = idxStr === '' ? -1 : parseInt(idxStr);
      if (isNaN(idx) || idx < 0) return;
      const items = parse();
      if (items.length === 0) return;
      const subgroup = node.promptGroups[groupIndex].items?.[idx];
      if (!subgroup || subgroup.type !== 'prompt_subgroup') return;
      if (!Array.isArray(subgroup.items)) subgroup.items = [];
      items.forEach(({ text, weight }) => {
        subgroup.items.push({
          type: 'prompt_tag',
          text,
          enabled: true,
          weight,
          random_candidate: false,
        });
      });
      this.updateHiddenWidget(node);
      this.refreshItemsList(node, groupIndex);
      input.value = '';
    });

    importToNewBtn.addEventListener('click', () => {
      const items = parse();
      if (items.length === 0) return;
      if (!Array.isArray(node.promptGroups[groupIndex].items)) node.promptGroups[groupIndex].items = [];
      const newSub = {
        type: 'prompt_subgroup',
        name: `Imported subgroup ${Date.now()}`,
        enabled: true,
        weight: '1',
        random_candidate: false,
        items: [],
      };
      items.forEach(({ text, weight }) => {
        newSub.items.push({
          type: 'prompt_tag',
          text,
          enabled: true,
          weight,
          random_candidate: false,
        });
      });
      node.promptGroups[groupIndex].items.push(newSub);
      this.updateHiddenWidget(node);
      this.refreshItemsList(node, groupIndex);
      input.value = '';
      // Refresh subgroup dropdown options after creating a new subgroup
      subgroupSelect.innerHTML = '';
      const def = document.createElement('option');
      def.value = '';
      def.textContent = 'Select subgroup';
      subgroupSelect.appendChild(def);
      node.promptGroups[groupIndex].items.forEach((it, idx) => {
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

  /**
   * Parse input string into list of {text, weight}
   */
  static parseImportString(input) {
    if (!input || typeof input !== 'string') return [];
    const parts = input
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);
    const items = [];
    for (const token of parts) {
      let t = token;
      if (t.startsWith('(') && t.endsWith(')')) {
        t = t.slice(1, -1).trim();
      }
      // Support tag:weight or tag, weight
      let tag = '';
      let weight = '1';
      if (t.includes(':')) {
        const idx = t.indexOf(':');
        tag = t.slice(0, idx).trim();
        weight = t.slice(idx + 1).trim();
      } else if (t.includes(',')) {
        const idx = t.indexOf(',');
        tag = t.slice(0, idx).trim();
        weight = t.slice(idx + 1).trim();
      } else {
        tag = t.trim();
      }
      if (!tag) continue;
      if (!weight) weight = '1';
      items.push({ text: tag, weight });
    }
    return items;
  }

  /**
   * Update hidden widget
   */
  static updateHiddenWidget(node) {
    if (node.hiddenWidget) {
      const serializedData = JSON.stringify(node.promptGroups || [], null, 2);
      node.hiddenWidget.value = serializedData;

      if (node.hiddenWidget.callback) {
        node.hiddenWidget.callback(serializedData);
      }
    }
  }

  /**
   * Refresh items list
   */
  static refreshItemsList(node, groupIndex) {
    const itemsContainer = document.querySelector('.items-container');
    if (itemsContainer && node.promptGroups && node.promptGroups[groupIndex]) {
      itemsContainer.innerHTML = '';

      if (node.promptGroups[groupIndex].items && Array.isArray(node.promptGroups[groupIndex].items)) {
        node.promptGroups[groupIndex].items.forEach((item, itemIndex) => {
          if (item.type === 'prompt_tag') {
            const tagItem = this.createTagListItem(node, groupIndex, itemIndex, item);
            itemsContainer.appendChild(tagItem);
          } else if (item.type === 'prompt_subgroup') {
            const subgroupItem = this.createSubgroupListItem(node, groupIndex, itemIndex, item);
            itemsContainer.appendChild(subgroupItem);
          }
        });
      }
    }
  }

  /**
   * Position the window on screen
   */
  static positionWindow(window) {
    // Center the window on screen
    const rect = window.getBoundingClientRect();
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    const centerX = (viewportWidth - rect.width) / 2;
    const centerY = (viewportHeight - rect.height) / 2;

    window.style.left = `${Math.max(8, centerX)}px`;
    window.style.top = `${Math.max(8, centerY)}px`;
  }

  /**
   * Make the window draggable
   */
  static makeWindowDraggable(window, header) {
    let isDragging = false;
    let xOffset = 0;
    let yOffset = 0;

    const dragStart = e => {
      if (e.target === header || header.contains(e.target)) {
        isDragging = true;
        window.style.transition = 'none';
        header.style.cursor = 'grabbing';

        const rect = window.getBoundingClientRect();
        xOffset = e.clientX - rect.left;
        yOffset = e.clientY - rect.top;

        e.preventDefault();
      }
    };

    const dragMove = e => {
      if (isDragging) {
        e.preventDefault();

        const x = e.clientX - xOffset;
        const y = e.clientY - yOffset;

        window.style.left = `${x}px`;
        window.style.top = `${y}px`;
      }
    };

    const dragEnd = () => {
      if (isDragging) {
        isDragging = false;
        header.style.cursor = 'move';
      }
    };

    header.addEventListener('mousedown', dragStart);
    document.addEventListener('mousemove', dragMove);
    document.addEventListener('mouseup', dragEnd);

    // Cleanup function
    return () => {
      header.removeEventListener('mousedown', dragStart);
      document.removeEventListener('mousemove', dragMove);
      document.removeEventListener('mouseup', dragEnd);
    };
  }
}
