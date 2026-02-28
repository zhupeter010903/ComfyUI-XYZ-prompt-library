# Grouped Prompt Node

A custom ComfyUI node that enables users to manage grouped prompts with advanced features including enable/disable, random sampling, and template saving.

## Features

### Core Functionality

- **Prompt Groups**: Organize prompts into logical groups
- **Enable/Disable**: Toggle entire groups or individual items on/off
- **Random Sampling**: Randomly select prompts from disabled items
- **Weight Control**: Apply weights to groups, subgroups, and individual prompts
- **Template System**: Save and load prompt group configurations

### Advanced Features

- **Shuffling**: Shuffle active prompts or all prompts within groups
- **Subgroups**: Create nested prompt structures within groups
- **Random Candidates**: Mark items as eligible for random selection
- **Dynamic Sizing**: Node automatically adjusts height based on content

## File Structure

```
ComfyUI-XYZNodes/
├── grouped_prompt_node.py          # Python backend implementation
├── js/
│   ├── grouped_prompt_node.js      # Main frontend extension
│   ├── prompt_group_ui.js          # UI component creation
│   ├── detailed_window.js          # Floating window controller (uses helper modules below)
│   ├── detailed_window_sections.js # Section builders: top settings, shuffle options, import, add-buttons row
│   ├── detailed_window_items.js    # Items list rendering: tags and subgroups inside the detailed window
│   ├── grouped_prompt_utils.js     # Utility functions
│   ├── grouped_prompt_styles.css   # Styling
│   └── test_template.js            # Test template data
└── prompt_group_template/           # Template storage directory
```

## Testing

### Test Templates

The node includes a test template system with sample data. To test the functionality:

1. **Load test templates**: Open the browser console and run:

   ```javascript
   populateTestTemplates()
   ```

2. **Available test templates**:
   - **Portrait Style**: Professional portrait with art style subgroups
   - **Landscape Scene**: Mountain landscape with random elements
   - **Character Design**: Character design with clothing subgroups

3. **Test commands**:

   ```javascript
   populateTestTemplates()  // Load sample templates
   clearTestTemplates()     // Remove all templates
   listTemplates()          // Show current templates
   ```

### Testing Workflow

1. Add the "XYZ Grouped Prompts" node to your workflow
2. Load test templates using the console command
3. Use the dropdown to select and load templates
4. Test adding/removing groups, tags, and subgroups
5. Test the detailed window functionality
6. Verify the node size adjusts automatically
7. Check that the hidden widget updates with changes

## Implementation Status

### ✅ Completed

- Basic node structure and registration
- Python backend with prompt processing algorithm
- Main UI framework
- Utility functions and data structures
- CSS styling framework
- **UI component creation methods** - All UI components now implemented
- **Event handlers for user interactions** - Complete event handling system
- **Template save/load functionality** - Basic localStorage-based template system
- **Detailed floating window implementation** - Complete detailed window with all features
- **Dynamic node sizing** - Node automatically adjusts height based on content
- **Basic error handling and validation** - Input validation and error display
- **Move operations** - Up/down buttons for groups and items, move-to-subgroup functionality
- **Proper UI separation** - Main interface shows only groups, details are in floating windows

### 🚧 In Progress / TODO

- **Backend template integration** - Connect template system to Python backend
- **Enhanced error handling** - User-friendly error notifications and validation
- **Performance optimization** - Large prompt group handling
- **Accessibility improvements** - Keyboard navigation and screen reader support

### ✅ Recent Fixes

- Group/subgroup disable now respected by backend output
- Subgroup tags list: vertical layout, functional controls, and move-to dropdown
- Detailed window: resizable and fills viewport height; compact group controls
- Subgroup UI: move up/down in detailed window and header-only one-line controls
- Persistence: node groups load from and save to hidden `prompt_data` so data survives refresh

### 📝 New TODOs

- Persist UI-only states (like subgroup dropdown expanded) to the saved data format if needed
- Hook template save/load to backend filesystem API in `grouped_prompt_node.py`

### 📋 Detailed TODO List

#### UI Components (`prompt_group_ui.js`) ✅ COMPLETED

- [x] `createToggleButton()` - Enable/disable toggle buttons
- [x] `createEditableName()` - Editable name inputs
- [x] `createEditableText()` - Editable text inputs
- [x] `createWeightInput()` - Weight input fields
- [x] `createRandomToggle()` - Random candidate toggles
- [x] `createMoveButton()` - Up/down move buttons
- [x] `createMoveDropdown()` - Move to subgroup dropdown
- [x] `createRemoveButton()` - Remove/delete buttons
- [x] `createButton()` - Generic button creation
- [x] **Group move operations** - Up/down buttons for prompt groups

#### Event Handlers ✅ COMPLETED

- [x] Group management events (toggle, rename, delete)
- [x] Tag management events (toggle, edit, move, delete)
- [x] Subgroup management events (toggle, rename, delete)
- [x] Weight and random count changes
- [x] Status/shuffle changes
- [x] **Move operations** - Group reordering, item reordering within groups

#### Detailed Window (`detailed_window.js`) ✅ COMPLETED

- [x] `createAddTagButton()` - Add new prompt tags
- [x] `createAddSubgroupButton()` - Add new subgroups
- [x] `createItemsList()` - Display group items
- [x] `createSaveTemplateButton()` - Save group as template
- [x] `createCloseButton()` - Close window button
- [x] Event handlers for all form inputs
- [x] **Move operations** - Up/down buttons for items, move-to-subgroup dropdown
- [x] **Status buttons** - Working shuffle status selection

#### Utility Functions ✅ COMPLETED

- [x] Template save/load operations (localStorage-based)
- [x] Data validation and sanitization
- [x] Node size calculations
- [x] Error and success message display
- [x] **Move operations** - Item and group movement logic

#### Main Node Functionality ✅ COMPLETED

- [x] Add prompt groups
- [x] Load templates from dropdown
- [x] Dynamic UI rendering
- [x] Hidden widget management
- [x] Node size adjustment
- [x] **Proper UI separation** - Groups only in main interface, details in windows

## Usage

### Basic Setup

1. Place the files in your ComfyUI custom nodes directory
2. Restart ComfyUI
3. The "XYZ Grouped Prompts" will appear in the "XYZNodes/Prompt" category

### Creating Prompt Groups

1. Add a Grouped Prompt Node to your workflow
2. Click "+ Add Group" to create a new prompt group
3. Click the gear icon (⚙) to open detailed settings
4. Configure group settings (name, weight, random count, status)
5. Add prompt tags or subgroups within the group

### Managing Prompts

- **Enable/Disable**: Click the toggle button next to items
- **Edit Text**: Click on text fields to edit
- **Adjust Weights**: Modify weight values (supports ranges like "0.5-1.5")
- **Random Selection**: Set random count and mark items as candidates
- **Shuffling**: Choose between default, shuffle active, or shuffle all

### Templates

- **Save**: Use the detailed window to save group configurations
- **Load**: Select from saved templates in the dropdown
- **Templates are stored** in localStorage (will be extended to backend files)

## Data Structure

### Prompt Group

```json
{
  "name": "Group Name",
  "enabled": true,
  "weight": "1",
  "random_count": "0",
  "status": "default",
  "items": []
}
```

### Prompt Tag

```json
{
  "type": "prompt_tag",
  "text": "prompt text",
  "enabled": true,
  "weight": "1",
  "random_candidate": false
}
```

### Prompt Subgroup

```json
{
  "type": "prompt_subgroup",
  "name": "Subgroup Name",
  "enabled": true,
  "weight": "1",
  "random_candidate": false,
  "items": []
}
```

## Backend Processing

The Python backend processes prompts according to this algorithm:

1. **Filter disabled groups** - Skip groups marked as disabled
2. **Apply group weights** - Multiply all item weights by group weight
3. **Collect active prompts** - Gather enabled items
4. **Collect random candidates** - Gather disabled items marked as random candidates
5. **Apply shuffling** - Shuffle active prompts if specified
6. **Random selection** - Select random items based on count
7. **Final shuffling** - Shuffle all prompts if specified
8. **Format output** - Join prompts with appropriate separators

## Weight Format

- **Single value**: "1.0", "0.5", "2.0"
- **Range**: "0.5-1.5" (randomly selects between 0.5 and 1.5 with 0.1 steps)

## Random Count Format

- **Single value**: "0", "1", "3"
- **Range**: "1-3" (randomly selects between 1 and 3)

## Status Options

- **default**: No shuffling
- **shuffle_active**: Shuffle only active prompts
- **shuffle_all**: Shuffle all prompts (active + random)

## Development Notes

### Adding New Features

1. Implement the feature in the appropriate JavaScript file
2. Add corresponding CSS styles if needed
3. Update the Python backend if the feature affects data processing
4. Test thoroughly with different data configurations

### Styling

- Use CSS custom properties for consistent theming
- Follow the existing color scheme and spacing patterns
- Ensure responsive design for different screen sizes
- Use `!important` declarations to override ComfyUI defaults

### Error Handling

- Validate user input before processing
- Provide clear error messages
- Gracefully handle malformed data
- Log errors for debugging

## Contributing

When contributing to this node:

1. Follow the existing code structure and patterns
2. Add comprehensive TODO comments for incomplete features
3. Test with various data configurations
4. Update this README with new features
5. Ensure backward compatibility

## License

This node is part of the ComfyUI-XYZNodes project. Please refer to the main project license for usage terms.
