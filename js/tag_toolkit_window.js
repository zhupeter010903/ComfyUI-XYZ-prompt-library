/**
 * Tag Toolkit Window Extension
 *
 * This extension provides a tag management interface for the prompt library.
 * It allows users to bulk edit tags across multiple entries.
 *
 * @author XYZNodes
 * @version 1.0.0
 */

export class TagToolkitWindow {
  constructor(promptLibraryWindow) {
    this.promptLibraryWindow = promptLibraryWindow;
    this.tagToolkitWindow = null;
    this.tagSelect = null;
    this.entriesContainer = null;
    this.tagChanges = {};
    this.selectedTag = '';
  }

  show() {
    if (this.tagToolkitWindow && document.body.contains(this.tagToolkitWindow)) {
      this.tagToolkitWindow.style.display = 'flex';
      this.refresh();
      return;
    }

    this.createWindow();
  }

  hide() {
    if (this.tagToolkitWindow) {
      this.tagToolkitWindow.remove();
      this.tagToolkitWindow = null;
    }
  }

  createWindow() {
    // Create the main window container
    const windowContainer = document.createElement('div');
    windowContainer.className = 'tag-toolkit-window';
    windowContainer.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 600px;
      height: 500px;
      min-width: 400px;
      min-height: 300px;
      background: rgba(30, 41, 59, 0.95);
      border: 2px solid rgba(148, 163, 184, 0.6);
      border-radius: 8px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
      z-index: 10001;
      display: flex;
      flex-direction: column;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      overflow: hidden;
    `;

    // Create header
    const header = this.createHeader(windowContainer);
    windowContainer.appendChild(header);

    // Create main content
    const content = this.createContent();
    windowContainer.appendChild(content);

    // Add to document
    document.body.appendChild(windowContainer);

    // Store reference
    this.tagToolkitWindow = windowContainer;

    // Initialize the toolkit
    this.refresh();

    // Make window draggable
    this.makeDraggable(windowContainer, header);

    // Make window resizable
    this.makeResizable(windowContainer);
  }

  createHeader(container) {
    const header = document.createElement('div');
    header.style.cssText = `
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 16px;
      background: rgba(40, 44, 52, 0.8);
      border-bottom: 1px solid rgba(66, 153, 225, 0.3);
      border-radius: 8px 8px 0 0;
      cursor: move;
    `;

    // Title
    const title = document.createElement('h3');
    title.textContent = '🔧 Tag Toolkit';
    title.style.cssText = `
      margin: 0;
      color: rgba(226, 232, 240, 0.9);
      font-size: 16px;
      font-weight: 600;
    `;
    header.appendChild(title);

    // Close button
    const closeBtn = document.createElement('button');
    closeBtn.textContent = '✕';
    closeBtn.style.cssText = `
      background: rgba(220, 53, 69, 0.8);
      border: none;
      border-radius: 4px;
      color: white;
      padding: 8px 12px;
      font-size: 14px;
      cursor: pointer;
      transition: all 0.2s ease;
    `;
    closeBtn.addEventListener('click', () => {
      if (this.tagToolkitWindow) {
        this.tagToolkitWindow.remove();
        this.tagToolkitWindow = null;
      }
    });
    header.appendChild(closeBtn);

    return header;
  }

  createContent() {
    const content = document.createElement('div');
    content.style.cssText = `
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 16px;
      gap: 16px;
      min-height: 0;
      overflow: hidden;
    `;
    content.className = 'tag-toolkit-content';

    // Top controls section
    const controlsSection = this.createControls();
    content.appendChild(controlsSection);

    // Entries list section
    const entriesSection = this.createEntriesList();
    content.appendChild(entriesSection);

    // Store references
    this.controlsSection = controlsSection;
    this.entriesSection = entriesSection;

    return content;
  }

  createControls() {
    const section = document.createElement('div');
    section.style.cssText = `
      display: flex;
      gap: 12px;
      align-items: center;
      padding: 12px;
      background: rgba(45, 55, 72, 0.6);
      border-radius: 6px;
      border: 1px solid rgba(66, 153, 225, 0.2);
    `;

    // Tag selection label
    const label = document.createElement('label');
    label.textContent = 'Select Tag:';
    label.style.cssText = `
      color: rgba(226, 232, 240, 0.8);
      font-size: 12px;
      font-weight: 500;
      white-space: nowrap;
    `;

    // Tag dropdown
    const tagSelect = document.createElement('select');
    tagSelect.style.cssText = `
      flex: 1;
      padding: 8px 12px;
      background: rgba(30, 41, 59, 0.7);
      border: 1px solid rgba(148, 163, 184, 0.3);
      border-radius: 4px;
      color: rgba(226, 232, 240, 0.9);
      font-size: 12px;
      cursor: pointer;
    `;
    tagSelect.addEventListener('change', () => {
      this.onTagSelectionChange(tagSelect.value);
    });

    // Save button
    const saveBtn = this.createButton('💾 Save Changes', () => {
      this.saveTagChanges();
    });
    saveBtn.style.cssText += `
      background: rgba(40, 167, 69, 0.8);
      padding: 8px 16px;
      font-size: 12px;
      white-space: nowrap;
    `;

    section.appendChild(label);
    section.appendChild(tagSelect);
    section.appendChild(saveBtn);

    // Store references
    this.tagSelect = tagSelect;
    this.saveBtn = saveBtn;

    return section;
  }

  createEntriesList() {
    const section = document.createElement('div');
    section.style.cssText = `
      flex: 1;
      display: flex;
      flex-direction: column;
      background: rgba(25, 29, 37, 0.6);
      border-radius: 6px;
      border: 1px solid rgba(66, 153, 225, 0.2);
      overflow: hidden;
      min-height: 0;
      max-height: 100%;
    `;
    section.className = 'entries-list-section';

    // Section header
    const header = document.createElement('div');
    header.style.cssText = `
      padding: 8px 12px;
      background: rgba(45, 55, 72, 0.8);
      border-bottom: 1px solid rgba(66, 153, 225, 0.2);
      font-weight: 600;
      color: rgba(226, 232, 240, 0.9);
      font-size: 12px;
      flex-shrink: 0;
    `;
    header.textContent = 'Entries (check to add tag, uncheck to remove tag)';
    section.appendChild(header);

    // Entries container
    const entriesContainer = document.createElement('div');
    entriesContainer.style.cssText = `
      flex: 1;
      overflow-y: scroll;
      overflow-x: hidden;
      padding: 8px;
      min-height: 0;
      max-height: 100%;
    `;
    entriesContainer.className = 'entries-container';
    section.appendChild(entriesContainer);

    // Store reference
    this.entriesContainer = entriesContainer;

    return section;
  }

  createButton(text, onClick) {
    const button = document.createElement('button');
    button.textContent = text;
    button.style.cssText = `
      background: rgba(66, 153, 225, 0.9);
      border: none;
      border-radius: 4px;
      color: white;
      padding: 8px 16px;
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
  }

  makeDraggable(container, header) {
    let isDragging = false;
    let startX, startY, startLeft, startTop;

    const startDrag = e => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;

      const rect = container.getBoundingClientRect();
      startLeft = rect.left;
      startTop = rect.top;

      document.addEventListener('mousemove', drag);
      document.addEventListener('mouseup', stopDrag);
      e.preventDefault();
    };

    const drag = e => {
      if (!isDragging) return;

      const deltaX = e.clientX - startX;
      const deltaY = e.clientY - startY;

      const newLeft = startLeft + deltaX;
      const newTop = startTop + deltaY;

      container.style.left = newLeft + 'px';
      container.style.top = newTop + 'px';
      container.style.transform = 'none';
    };

    const stopDrag = () => {
      isDragging = false;
      document.removeEventListener('mousemove', drag);
      document.removeEventListener('mouseup', stopDrag);
    };

    header.addEventListener('mousedown', startDrag);
  }

  makeResizable(container) {
    const resizeHandle = document.createElement('div');
    resizeHandle.className = 'resize-handle';
    resizeHandle.style.cssText = `
      position: absolute;
      bottom: 0;
      right: 0;
      width: 20px;
      height: 20px;
      cursor: se-resize;
      background: linear-gradient(135deg, transparent 0%, transparent 50%, rgba(148, 163, 184, 0.6) 50%, rgba(148, 163, 184, 0.6) 100%);
      border-radius: 0 0 8px 0;
      z-index: 1;
    `;

    let isResizing = false;
    let startX, startY, startWidth, startHeight;

    const startResize = e => {
      isResizing = true;
      startX = e.clientX;
      startY = e.clientY;

      const rect = container.getBoundingClientRect();
      startWidth = rect.width;
      startHeight = rect.height;

      document.addEventListener('mousemove', resize);
      document.addEventListener('mouseup', stopResize);
      e.preventDefault();
    };

    const resize = e => {
      if (!isResizing) return;

      const deltaX = e.clientX - startX;
      const deltaY = e.clientY - startY;

      const newWidth = Math.max(400, startWidth + deltaX); // min-width: 400px
      const newHeight = Math.max(300, startHeight + deltaY); // min-height: 300px

      container.style.width = newWidth + 'px';
      container.style.height = newHeight + 'px';
    };

    const stopResize = () => {
      isResizing = false;
      document.removeEventListener('mousemove', resize);
      document.removeEventListener('mouseup', stopResize);
    };

    resizeHandle.addEventListener('mousedown', startResize);
    container.appendChild(resizeHandle);
  }

  refresh() {
    this.populateTagDropdown();
    this.populateEntriesList();
  }

  populateTagDropdown() {
    if (!this.tagSelect) return;

    // Clear existing options
    this.tagSelect.innerHTML = '<option value="">-- Select a tag --</option>';

    // Collect all unique tags from all entries
    const allTags = new Set();
    Object.values(this.promptLibraryWindow.libraryData).forEach(entry => {
      if (entry.tags && Array.isArray(entry.tags)) {
        entry.tags.forEach(tag => {
          if (tag && tag.trim()) {
            allTags.add(tag.trim());
          }
        });
      }
    });

    // Add tag options
    Array.from(allTags)
      .sort()
      .forEach(tag => {
        const option = document.createElement('option');
        option.value = tag;
        option.textContent = tag;
        this.tagSelect.appendChild(option);
      });
  }

  populateEntriesList() {
    if (!this.entriesContainer) return;

    // Clear existing entries
    this.entriesContainer.innerHTML = '';

    // Get selected tag
    const selectedTag = this.tagSelect.value;
    if (!selectedTag) {
      const placeholder = document.createElement('div');
      placeholder.style.cssText = `
        text-align: center;
        padding: 40px 20px;
        color: rgba(226, 232, 240, 0.5);
        font-style: italic;
      `;
      placeholder.textContent = 'Select a tag to see entries';
      this.entriesContainer.appendChild(placeholder);
      return;
    }

    this.selectedTag = selectedTag;

    // Create entry checkboxes
    Object.entries(this.promptLibraryWindow.libraryData).forEach(([entryId, entry]) => {
      const entryItem = document.createElement('div');
      entryItem.style.cssText = `
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px;
        background: rgba(45, 55, 72, 0.4);
        border-radius: 4px;
        margin-bottom: 4px;
      `;

      // Checkbox
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = entry.tags && Array.isArray(entry.tags) && entry.tags.includes(selectedTag);
      checkbox.style.cssText = `
        margin: 0;
        cursor: pointer;
        width: 16px;
        height: 16px;
      `;
      checkbox.addEventListener('change', e => {
        // Store the change for later saving
        if (!this.tagChanges[entryId]) this.tagChanges[entryId] = {};
        this.tagChanges[entryId][selectedTag] = e.target.checked;
      });

      // Entry name
      const nameSpan = document.createElement('span');
      nameSpan.textContent = entry.name || entryId;
      nameSpan.style.cssText = `
        flex: 1;
        color: rgba(226, 232, 240, 0.9);
        font-size: 12px;
      `;

      entryItem.appendChild(checkbox);
      entryItem.appendChild(nameSpan);
      this.entriesContainer.appendChild(entryItem);
    });
  }

  onTagSelectionChange(selectedTag) {
    this.tagChanges = {}; // Clear previous changes
    this.populateEntriesList();
  }

  saveTagChanges() {
    if (!this.selectedTag) {
      this.promptLibraryWindow.showError('Please select a tag first!');
      return;
    }

    if (Object.keys(this.tagChanges).length === 0) {
      this.promptLibraryWindow.showSuccess('No changes to save!');
      return;
    }

    // Apply changes to entries
    Object.entries(this.tagChanges).forEach(([entryId, tagStates]) => {
      const entry = this.promptLibraryWindow.libraryData[entryId];
      if (!entry) return;

      // Ensure tags array exists
      if (!entry.tags) entry.tags = [];
      if (!Array.isArray(entry.tags)) entry.tags = [];

      const tagIndex = entry.tags.indexOf(this.selectedTag);
      const shouldHaveTag = tagStates[this.selectedTag];

      if (shouldHaveTag && tagIndex === -1) {
        // Add tag
        entry.tags.push(this.selectedTag);
      } else if (!shouldHaveTag && tagIndex !== -1) {
        // Remove tag
        entry.tags.splice(tagIndex, 1);
      }

      // Update entry state to mark as modified
      if (this.promptLibraryWindow.entryStates[entry.id]) {
        this.promptLibraryWindow.entryStates[entry.id] = {
          ...this.promptLibraryWindow.entryStates[entry.id],
          modified: true,
        };
      }

      // Save to local storage
      this.promptLibraryWindow.saveEntryToLocalStorage(entry);
    });

    // Store the count before clearing
    const updatedCount = Object.keys(this.tagChanges).length;

    // Clear changes
    this.tagChanges = {};

    // Refresh displays
    this.promptLibraryWindow.refreshEntryList();
    this.populateEntriesList();

    // Update all prompt library nodes
    this.promptLibraryWindow.updateAllPromptLibraryNodes();

    this.promptLibraryWindow.showSuccess(`Tag "${this.selectedTag}" updated for ${updatedCount} entries!`);
  }
}
