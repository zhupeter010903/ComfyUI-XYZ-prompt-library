// Detailed Window Items
// This module encapsulates list rendering for tags and subgroups inside the detailed window.
// Features:
// - Items list container that expands to fill available height
// - Tag items with enable toggle, move up/down, text/weight inputs, random candidate toggle, move-to dropdown, remove
// - Subgroup items with enable toggle (leftmost), move up/down, name/weight inputs, random candidate toggle, add-tag, collapsible tag list

export function createItemsList(node, groupData, groupIndex) {
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
