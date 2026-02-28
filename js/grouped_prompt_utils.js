// Utility functions for the Grouped Prompt Node
// This file contains common helper functions and data structures

export class GroupedPromptUtils {
  /**
   * Create a new empty prompt group
   */
  static createEmptyPromptGroup(name = null) {
    return {
      name: name || `Group ${Date.now()}`,
      enabled: true,
      weight: '1',
      random_count: '0',
      status: 'default', // default, shuffle_active, shuffle_all
      items: [],
    };
  }

  /**
   * Create a new empty prompt tag
   */
  static createEmptyPromptTag(text = '') {
    return {
      type: 'prompt_tag',
      text: text,
      enabled: true,
      weight: '1',
      random_candidate: false,
    };
  }

  /**
   * Create a new empty prompt subgroup
   */
  static createEmptyPromptSubgroup(name = null) {
    return {
      type: 'prompt_subgroup',
      name: name || `Subgroup ${Date.now()}`,
      enabled: true,
      weight: '1',
      random_candidate: false,
      items: [],
    };
  }

  /**
   * Validate weight string format (a or a-b)
   */
  static validateWeightString(weightStr) {
    if (!weightStr || typeof weightStr !== 'string') {
      return false;
    }

    weightStr = weightStr.trim();

    // Check if it's a single number
    if (/^\d+(\.\d+)?$/.test(weightStr)) {
      const weight = parseFloat(weightStr);
      return weight >= 0.0 && weight <= 2.0;
    }

    // Check if it's a range (a-b)
    if (/^\d+(\.\d+)?-\d+(\.\d+)?$/.test(weightStr)) {
      const parts = weightStr.split('-');
      const min = parseFloat(parts[0]);
      const max = parseFloat(parts[1]);
      return min >= 0.0 && max <= 2.0 && min < max;
    }

    return false;
  }

  /**
   * Validate random count string format (a or b-c)
   */
  static validateRandomCountString(countStr) {
    if (!countStr || typeof countStr !== 'string') {
      return false;
    }

    countStr = countStr.trim();

    // Check if it's a single integer
    if (/^\d+$/.test(countStr)) {
      const count = parseInt(countStr);
      return count >= 0;
    }

    // Check if it's a range (b-c)
    if (/^\d+-\d+$/.test(countStr)) {
      const parts = countStr.split('-');
      const min = parseInt(parts[0]);
      const max = parseInt(parts[1]);
      return min >= 0 && max >= 0 && min <= max;
    }

    return false;
  }

  /**
   * Serialize prompt data to JSON string for backend
   */
  static serializePromptData(node) {
    try {
      const data = node.promptGroups || [];
      return JSON.stringify(data, null, 2);
    } catch (error) {
      console.error('Error serializing prompt data:', error);
      return '[]';
    }
  }

  /**
   * Deserialize prompt data from JSON string
   */
  static deserializePromptData(jsonString) {
    try {
      if (!jsonString || jsonString.trim() === '') {
        return [];
      }
      return JSON.parse(jsonString);
    } catch (error) {
      console.error('Error deserializing prompt data:', error);
      return [];
    }
  }

  /**
   * Update the hidden widget with current prompt data
   */
  static updateHiddenWidget(node) {
    if (node.hiddenWidget) {
      const serializedData = this.serializePromptData(node);
      node.hiddenWidget.value = serializedData;

      // Trigger change event
      if (node.hiddenWidget.callback) {
        node.hiddenWidget.callback(serializedData);
      }
    }
  }

  /**
   * Create a floating window with the given content
   */
  static createFloatingWindow(content, title = 'Window', width = '400px', height = '300px') {
    const window = document.createElement('div');
    window.className = 'grouped-prompt-floating-window';
    window.style.cssText = `
            position: fixed;
            z-index: 10000;
            background: #1b1b1b;
            border: 1px solid #2c2c2c;
            border-radius: 8px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            color: #ccc;
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            width: ${width};
            height: ${height};
            display: flex;
            flex-direction: column;
            overflow: hidden;
        `;

    // Header
    const header = document.createElement('div');
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

    const titleElement = document.createElement('div');
    titleElement.textContent = title;
    titleElement.style.cssText = `
            color: #fff;
            font-size: 14px;
            font-weight: 500;
            margin: 0;
            user-select: none;
        `;
    header.appendChild(titleElement);

    const closeBtn = document.createElement('button');
    closeBtn.textContent = '×';
    closeBtn.style.cssText = `
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
    closeBtn.onclick = () => window.remove();
    header.appendChild(closeBtn);

    window.appendChild(header);

    // Content
    const contentContainer = document.createElement('div');
    contentContainer.style.cssText = `
            flex: 1;
            overflow: auto;
            padding: 16px;
        `;
    contentContainer.appendChild(content);
    window.appendChild(contentContainer);

    return window;
  }

  /**
   * Make a window draggable by its header
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

  /**
   * Show an error message
   */
  static showError(message) {
    console.error('Grouped Prompt Error:', message);
    // TODO: Implement user-friendly error display
    // Could show a toast notification or modal
  }

  /**
   * Show a success message
   */
  static showSuccess(message) {
    console.log('Grouped Prompt Success:', message);
    // TODO: Implement user-friendly success display
    // Could show a toast notification
  }

  /**
   * Calculate the required height for the node based on content
   */
  static calculateNodeHeight(node) {
    const baseHeight = 200; // Minimum height
    const groupHeight = 50; // Height per group
    const groupSpacing = 8; // Spacing between groups

    if (!node.promptGroups || node.promptGroups.length === 0) {
      return baseHeight;
    }

    let totalHeight = baseHeight;

    node.promptGroups.forEach(group => {
      totalHeight += groupHeight + groupSpacing;

      // Add height for items in the group
      if (group.items && Array.isArray(group.items)) {
        const itemHeight = 40; // Height per item
        const itemSpacing = 4; // Spacing between items

        group.items.forEach(item => {
          totalHeight += itemHeight + itemSpacing;

          // If it's a subgroup, add height for its items
          if (item.type === 'prompt_subgroup' && item.items) {
            item.items.forEach(() => {
              totalHeight += itemHeight + itemSpacing;
            });
          }
        });
      }
    });

    return Math.max(baseHeight, totalHeight);
  }

  /**
   * Update the node size based on content
   */
  static updateNodeSize(node) {
    const requiredHeight = this.calculateNodeHeight(node);
    const currentHeight = node.size[1];

    if (currentHeight !== requiredHeight) {
      node.setSize([node.size[0], requiredHeight]);
      node.setDirtyCanvas(true, true);
    }
  }

  /**
   * Generate a unique ID for items
   */
  static generateUniqueId() {
    return `item_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Deep clone an object
   */
  static deepClone(obj) {
    if (obj === null || typeof obj !== 'object') {
      return obj;
    }

    if (obj instanceof Date) {
      return new Date(obj.getTime());
    }

    if (obj instanceof Array) {
      return obj.map(item => this.deepClone(item));
    }

    if (typeof obj === 'object') {
      const cloned = {};
      for (const key in obj) {
        if (obj.hasOwnProperty(key)) {
          cloned[key] = this.deepClone(obj[key]);
        }
      }
      return cloned;
    }

    return obj;
  }
}
