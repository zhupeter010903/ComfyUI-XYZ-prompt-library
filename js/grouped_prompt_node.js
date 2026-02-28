import { api } from '../../../scripts/api.js';
import { app } from '../../../scripts/app.js';

// Main GroupedPromptNode extension
app.registerExtension({
  name: 'XYZNodes.GroupedPromptNode',

  setup() {
    // TODO: Add message handlers for communication with Python backend
    // - Template save/load operations
    // - Error handling
  },

  async nodeCreated(node) {
    if (node.comfyClass === 'XYZ Grouped Prompts') {
      // Enable widget serialization
      node.serialize_widgets = true;

      // Initialize the node
      this.initializeNode(node);

      // Ensure hydration after Comfy loads saved widget values
      const originalOnConfigure = node.onConfigure?.bind(node);
      node.onConfigure = o => {
        if (originalOnConfigure) originalOnConfigure(o);
        // After widgets_values are applied, hydrate UI from hidden widget
        this.hydrateFromHiddenWidget(node);
        this.updateNodeSize(node);
      };
    }
  },

  initializeNode(node) {
    // Store node state
    node.promptGroups = [];
    node.selectedTemplate = null;

    // Attach to backend hidden widget and hydrate state
    this.attachHiddenWidget(node);
    this.hydrateFromHiddenWidget(node);

    // Create the main UI structure
    this.createMainUI(node);

    // Create the prompt groups list
    this.createPromptGroupsList(node);

    // Hidden widget is already attached; ensure it reflects current state
    this.updateHiddenWidget(node);

    // Set initial size
    this.updateNodeSize(node);
  },

  createMainUI(node) {
    // Create main container
    const container = document.createElement('div');
    container.className = 'grouped-prompt-container';
    container.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 8px;
            padding: 8px;
            width: 100%;
            min-height: 200px;
        `;

    // Create header with controls
    const header = this.createHeader(node);
    container.appendChild(header);

    // Create prompt groups list container
    const groupsContainer = document.createElement('div');
    groupsContainer.className = 'prompt-groups-container';
    groupsContainer.style.cssText = `
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 8px;
            min-height: 150px;
        `;
    container.appendChild(groupsContainer);

    // Store references
    node.mainContainer = container;
    node.groupsContainer = groupsContainer;

    // Add to node
    node.addDOMWidget('main_ui', 'custom', container, {
      getValue: () => '',
      setValue: () => {},
      getMinHeight: () => 200,
    });
  },

  createHeader(node) {
    const header = document.createElement('div');
    header.className = 'grouped-prompt-header';
    header.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px;
            background: rgba(40, 44, 52, 0.6);
            border-radius: 6px;
            border: 1px solid rgba(226, 232, 240, 0.2);
        `;

    // Add prompt group button
    const addGroupBtn = this.createButton('+ Add Group', () => {
      this.addPromptGroup(node);
    });
    header.appendChild(addGroupBtn);

    // Template dropdown
    const templateDropdown = this.createTemplateDropdown(node);
    header.appendChild(templateDropdown);
    // Expose a refresh function for other modules (e.g., detailed window) to call after saves
    node.templateDropdown = templateDropdown;
    node.refreshTemplateDropdown = async () => {
      // Reset options to just the default, then repopulate from backend
      templateDropdown.innerHTML = '';
      const defaultOption = document.createElement('option');
      defaultOption.value = '';
      defaultOption.textContent = 'Select Template';
      templateDropdown.appendChild(defaultOption);
      await this.populateTemplateDropdown(templateDropdown);
    };

    // Load template button
    const loadTemplateBtn = this.createButton('Load', () => {
      this.loadTemplate(node);
    });
    header.appendChild(loadTemplateBtn);

    // (Import feature removed per request)

    return header;
  },

  createTemplateDropdown(node) {
    const dropdown = document.createElement('select');
    dropdown.className = 'template-dropdown';
    dropdown.style.cssText = `
            background: rgba(45, 55, 72, 0.7);
            border: 1px solid rgba(226, 232, 240, 0.2);
            border-radius: 4px;
            color: rgba(226, 232, 240, 0.8);
            padding: 4px 8px;
            font-size: 12px;
            min-width: 120px;
        `;

    // Add default option
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = 'Select Template';
    dropdown.appendChild(defaultOption);

    // Populate with available templates from backend
    this.populateTemplateDropdown(dropdown);

    dropdown.addEventListener('change', e => {
      node.selectedTemplate = e.target.value;
    });

    return dropdown;
  },

  async populateTemplateDropdown(dropdown) {
    try {
      const res = await api.fetchApi('/xyz/grouped_prompt/templates');
      const json = await res.json();
      const names = Array.isArray(json.templates) ? json.templates : [];
      names.forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        dropdown.appendChild(option);
      });
    } catch (error) {
      console.error('Error loading templates:', error);
    }
  },

  createPromptGroupsList(node) {
    // Clear existing content
    node.groupsContainer.innerHTML = '';

    if (!node.promptGroups || node.promptGroups.length === 0) {
      // Show placeholder
      const placeholder = document.createElement('div');
      placeholder.className = 'groups-placeholder';
      placeholder.style.cssText = `
            text-align: center;
            padding: 40px 20px;
            color: rgba(226, 232, 240, 0.6);
            font-style: italic;
        `;
      placeholder.textContent = "No prompt groups yet. Click 'Add Group' to get started.";
      node.groupsContainer.appendChild(placeholder);
    } else {
      // Render all groups using the PromptGroupUI class
      this.renderPromptGroups(node);
    }
  },

  renderPromptGroups(node) {
    // Import and use the PromptGroupUI class
    import('./prompt_group_ui.js')
      .then(module => {
        const { PromptGroupUI } = module;

        node.promptGroups.forEach((groupData, groupIndex) => {
          const groupUI = PromptGroupUI.createPromptGroupUI(node, groupData, groupIndex);
          node.groupsContainer.appendChild(groupUI);

          // Don't render individual items here - they only appear in the detailed window
          // The main interface should only show the prompt groups themselves
        });
      })
      .catch(error => {
        console.error('Error loading PromptGroupUI:', error);
        this.showError('Failed to load UI components');
      });
  },

  attachHiddenWidget(node) {
    // Find existing backend-provided hidden widget named 'prompt_data'
    if (node.widgets && Array.isArray(node.widgets)) {
      const existing = node.widgets.find(w => w && (w.name === 'prompt_data' || w.label === 'prompt_data'));
      if (existing) {
        existing.hidden = true;
        existing.type = 'converted-widget';
        existing.computeSize = () => [0, -4];
        // Keep original callback
        const originalCb = existing.callback;
        existing.callback = v => {
          // Keep node state in sync if external changes happen
          this.hydrateFromHiddenWidget(node);
          if (typeof originalCb === 'function') {
            try {
              originalCb(v);
            } catch (e) {
              /* noop */
            }
          }
        };
        node.hiddenWidget = existing;
        return;
      }
    }
    // Fallback: create if not found (shouldn't normally happen)
    const hiddenWidget = node.addWidget('text', 'prompt_data', '');
    hiddenWidget.type = 'converted-widget';
    hiddenWidget.hidden = true;
    hiddenWidget.computeSize = () => [0, -4];
    node.hiddenWidget = hiddenWidget;
  },

  hydrateFromHiddenWidget(node) {
    try {
      const raw = node.hiddenWidget ? node.hiddenWidget.value : '';
      if (raw && typeof raw === 'string' && raw.trim().length) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          node.promptGroups = parsed;
          // If UI already exists, refresh it
          if (node.groupsContainer) {
            this.createPromptGroupsList(node);
          }
          this.updateNodeSize(node);
          return;
        }
      }
      // Initialize default if no data
      if (!node.promptGroups) node.promptGroups = [];
    } catch (e) {
      console.warn('Failed to hydrate prompt groups from hidden widget:', e);
      if (!node.promptGroups) node.promptGroups = [];
    }
  },

  createButton(text, onClick) {
    const button = document.createElement('button');
    button.textContent = text;
    button.style.cssText = `
            background: rgba(66, 153, 225, 0.9);
            border: none;
            border-radius: 4px;
            color: white;
            padding: 6px 12px;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
        `;

    button.addEventListener('click', onClick);
    button.addEventListener('mouseenter', () => {
      button.style.background = 'rgba(66, 153, 225, 1)';
    });
    button.addEventListener('mouseleave', () => {
      button.style.background = 'rgba(66, 153, 225, 0.9)';
    });

    return button;
  },

  addPromptGroup(node) {
    // Create new prompt group data
    const newGroup = {
      name: `Group ${node.promptGroups.length + 1}`,
      enabled: true,
      weight: '1',
      random_count: '0',
      status: 'default',
      items: [],
    };

    // Add to promptGroups array
    node.promptGroups.push(newGroup);

    // Update UI
    this.createPromptGroupsList(node);

    // Update hidden widget
    this.updateHiddenWidget(node);

    // Update node size
    this.updateNodeSize(node);

    console.log('Added new prompt group:', newGroup);
  },

  loadTemplate(node) {
    if (!node.selectedTemplate) {
      this.showError('Please select a template first');
      return;
    }

    (async () => {
      try {
        const res = await api.fetchApi(`/xyz/grouped_prompt/template/${encodeURIComponent(node.selectedTemplate)}`);
        if (!res.ok) {
          this.showError(`Template "${node.selectedTemplate}" not found`);
          return;
        }
        const templateData = await res.json();
        if (templateData) {
          const newGroup = JSON.parse(JSON.stringify(templateData));
          const nameExists = (node.promptGroups || []).some(
            g => (g.name || '').trim() === (newGroup.name || '').trim(),
          );
          if (nameExists) newGroup.name = `${newGroup.name} (copy)`;
          if (!Array.isArray(newGroup.items)) newGroup.items = [];
          node.promptGroups.push(newGroup);
          this.createPromptGroupsList(node);
          this.updateHiddenWidget(node);
          this.updateNodeSize(node);
          const dropdown = node.mainContainer.querySelector('.template-dropdown');
          if (dropdown) dropdown.value = '';
          node.selectedTemplate = null;
          this.showSuccess('Template loaded');
        }
      } catch (error) {
        console.error('Error loading template:', error);
        this.showError('Error loading template. Please try again.');
      }
    })();
  },

  updateNodeSize(node) {
    const baseHeight = 150;
    const groupHeight = 60;
    const groupSpacing = 8;

    let totalHeight = baseHeight;
    if (node.promptGroups && node.promptGroups.length > 0) {
      totalHeight += (groupHeight + groupSpacing) * node.promptGroups.length;
    }

    const requiredHeight = Math.max(baseHeight, totalHeight);
    const currentHeight = node.size[1];

    if (currentHeight !== requiredHeight) {
      node.setSize([node.size[0], requiredHeight]);
      node.setDirtyCanvas(true, true);
    }
  },

  updateHiddenWidget(node) {
    if (node.hiddenWidget) {
      const serializedData = JSON.stringify(node.promptGroups || [], null, 2);
      node.hiddenWidget.value = serializedData;

      // Trigger change event
      if (node.hiddenWidget.callback) {
        node.hiddenWidget.callback(serializedData);
      }
    }
  },

  showError(message) {
    console.error('Grouped Prompt Error:', message);
    if (app?.extensionManager?.dialog?.confirm) {
      app.extensionManager.dialog.confirm({
        title: 'Error',
        message: String(message),
        type: 'default',
      });
    }
  },

  showSuccess(message) {
    console.log('Grouped Prompt Success:', message);
    if (app?.extensionManager?.dialog?.confirm) {
      app.extensionManager.dialog.confirm({
        title: 'Info',
        message: String(message),
        type: 'default',
      });
    }
  },
});
