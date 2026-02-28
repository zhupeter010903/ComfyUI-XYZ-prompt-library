import json
import random
import os
import re
from typing import Dict, List, Any, Union, Tuple, Optional

# Import ByPassTypeTuple from the same directory
from .node import ByPassTypeTuple

class PromptLibraryNode:
    """
    A custom node for ComfyUI that enables users to create, edit, save, and manage 
    prompt libraries with dynamic outputs and advanced pattern recognition.
    
    This node provides a comprehensive prompt management system with:
    - Hierarchical organization (entries -> groups -> prompts)
    - Advanced random selection algorithms with active/inactive item control
    - Pattern recognition for dynamic prompt generation
    - Tag-based entry resolution
    - Real-time synchronization with frontend library manager
    
    The node processes prompt templates through a three-step algorithm:
    1. Pattern Recognition: Handles {option1|option2|...} patterns for output generation
    2. Tag Resolution: Processes [[tag_name]] patterns for tag-based entry selection
    3. Entry Resolution: Resolves [entry_name] and [entry_name/group_name] references
    
    Features:
    - Multiple output generation with seed-based randomness
    - Weight multiplication across entry, group, and prompt levels
    - Random range weights (e.g., "1.0-2.0")
    - Order preservation for non-shuffled random sampling
    - Active/inactive item control with colon-separated syntax
    """
    
    NAME = "Prompt Library Node"
    CATEGORY = "XYZNodes/Prompt"
    DESCRIPTION = "Create and manage prompt libraries with dynamic outputs and pattern recognition"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                }),
                "prompt_template": ("STRING", {
                    "default": "",
                    "multiline": True
                }),
            },
            "optional": {},
            "hidden": {
                "id": "UNIQUE_ID",
                "library_data": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "hidden": True
                }),
                "output_count": ("STRING", {
                    "default": "1",
                    "hidden": True
                })
            }
        }
    
    RETURN_TYPES = ByPassTypeTuple(("STRING",))
    RETURN_NAMES = ByPassTypeTuple(("prompt_1",))
    FUNCTION = "process_prompts"
    OUTPUT_NODE = True
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")
    
    def __init__(self):
        # Use absolute path to ensure correct library directory resolution
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.library_dir = os.path.join(current_dir, "prompt_library")
        os.makedirs(self.library_dir, exist_ok=True)
        # Remove library cache loading since we'll use widget data only
        self.output_count = 1
    
    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True
    
    def get_output_names(self):
        """Get output names for the current number of outputs."""
        names = []
        for i in range(1, self.output_count + 1):
            names.append(f"prompt_{i}")
        return names
    
    # Library cache loading removed - we now rely entirely on widget data

    # Library cache refresh removed - we now rely entirely on widget data
    
    def process_prompts(self, id, seed, prompt_template="", library_data="", output_count="1", **kwargs):
        """
        Process the prompt template according to the three-step algorithm.
        
        This method processes prompt templates through a sophisticated pattern recognition
        and resolution system that supports dynamic content generation, tag-based selection,
        and hierarchical library management.
        
        IMPORTANT: This method relies ENTIRELY on widget data from the frontend.
        The frontend is responsible for:
        1. Loading data from disk on startup
        2. Merging with browser storage (modified/new entries)
        3. Keeping all node widgets synchronized
        4. Providing complete, up-to-date library data
        
        Args:
            id: Node ID for identification
            seed: Random seed for reproducible results across executions
            prompt_template: Template string containing patterns and library references
            library_data: JSON string containing complete library data from frontend
            output_count: Number of outputs to generate (supports multiple outputs)
            
        Returns:
            Tuple containing the processed prompt strings for each output
            
        Processing Algorithm:
        1. Pattern Recognition: Processes {option1|option2|...} patterns for output generation
        2. Tag Resolution: Handles [[tag_name]] patterns for tag-based entry selection
        3. Entry Resolution: Resolves [entry_name] and [entry_name/group_name] references
        """
        debug_template_len = len(prompt_template or "")
        debug_library_len = len((library_data or "").strip())
        self._debug(f"process_prompts start id={id} seed={seed} template_len={debug_template_len} library_len={debug_library_len} output_count={output_count}")

        # Control randomness with provided seed
        try:
            random.seed(int(seed) if seed is not None else None)
        except Exception:
            pass
        
        # Parse output count
        try:
            num_outputs = int(output_count) if output_count.isdigit() else 1
        except (ValueError, TypeError):
            num_outputs = 1
        
        if not prompt_template or prompt_template.strip() == "":
            return ("",) * num_outputs
        
        # Parse library data if provided
        library_entries = {}
        if library_data and library_data.strip():
            try:
                library_entries = json.loads(library_data)
                
                # Convert ID-indexed data to name-indexed data for prompt processing
                name_indexed_entries = {}
                for entry_id, entry_data in library_entries.items():
                    if entry_data and isinstance(entry_data, dict):
                        entry_name = entry_data.get("name", "")
                        if entry_name:
                            name_indexed_entries[entry_name] = entry_data
                        else:
                            # Skip entries without names
                            pass
                
                library_entries = name_indexed_entries
                self._debug(f"Parsed library entries: {len(library_entries)} names derived from {len(name_indexed_entries)} ids")
                
            except Exception as e:
                # Silently handle parsing errors
                self._debug(f"Failed to parse library_data: {e}")
        
        # Use only widget data - it should contain the complete, up-to-date library
        if not library_entries:
            self._debug("No library entries available after parsing; returning empty outputs")
            return ("",) * num_outputs
        
        # Generate outputs
        outputs = []
        for i in range(num_outputs):
            processed = self._process_single_output(prompt_template, library_entries, i)
            filtered = self._remove_empty_prompts(processed)
            outputs.append(filtered)
        
        result = tuple(outputs)
        self._debug(f"process_prompts generated {len(result)} outputs; first='{result[0] if result else ''}'")
        return result
    
    def _process_single_output(self, template: str, library_entries: Dict, output_index: int) -> str:
        """Process a single output according to the three-step algorithm."""
        result = template
        
        # Step 1: Pattern Recognition and Output Generation
        result = self._process_pattern_recognition(result, output_index)
        
        # Step 2: Tag-Based Entry Resolution
        result = self._process_tag_resolution(result, library_entries)
        
        # Step 3: Entry and Group Resolution
        result = self._process_entry_resolution(result, library_entries)
        
        return result
    
    def _process_pattern_recognition(self, text: str, output_index: int) -> str:
        """Step 1: Process {string1|string2|...} patterns for output generation."""
        def replace_pattern(match):
            options = match.group(1).split('|')
            if output_index < len(options):
                return options[output_index]
            else:
                return ""  # Empty string for missing options
        
        return re.sub(r'\{([^}]+)\}', replace_pattern, text)
    
    def _process_tag_resolution(self, text: str, library_entries: Dict) -> str:
        """Step 2: Process [[tag_name]...] patterns for tag-based resolution."""
        def replace_tag_pattern(match):
            tag_name = match.group(1)
            count_spec = match.group(2)
            remaining_text = match.group(3) if match.group(3) else ""
            
            # Find entries with matching tag
            matching_entries = []
            for entry_name, entry_data in library_entries.items():
                if entry_data.get("active", True):
                    tags = entry_data.get("tags", [])
                    if tag_name in tags:
                        matching_entries.append(entry_name)
            
            if not matching_entries:
                return f"[[{tag_name}]]"
            
            # Determine count
            if count_spec:
                try:
                    if "-" in count_spec:  # range like 2-5
                        min_count, max_count = map(int, count_spec.split("-"))
                        count = random.randint(min_count, max_count)
                    else:  # single number
                        count = int(count_spec)
                except ValueError:
                    count = 1
            else:
                count = 1
                        
            # Select random entries
            count = min(count, len(matching_entries))
            selected_entries = random.sample(matching_entries, count)
            
            # Replace with selected entries
            replacements = []
            for entry_name in selected_entries:
                replacements.append(f"[{entry_name}{remaining_text}]")
            
            return ", ".join(replacements)
        
        # Handle [[tag] patterns - this will be processed in two stages:
        # 1. Tag Resolution: [[tag] → [entry_name]
        # 2. Entry Resolution: [entry_name/group] → resolved group content
        return re.sub(r'\[\[([^:\]]+)(?::([^]]*))?\]([^[]*)?\]', replace_tag_pattern, text)
    
    def _replace_tag_group_pattern(self, match, library_entries):
        """Handle [[tag/group]] patterns."""
        tag_name = match.group(1)
        group_name = match.group(2)
        count_spec = match.group(3)
        remaining_text = match.group(4) if match.group(4) else ""
        
        # Find entries with matching tag
        matching_entries = []
        for entry_name, entry_data in library_entries.items():
            if entry_data.get("active", True):
                tags = entry_data.get("tags", [])
                if tag_name in tags:
                    # Check if group exists in this entry
                    groups = entry_data.get("groups", [])
                    for group in groups:
                        if group.get("name") == group_name and group.get("active", True):
                            matching_entries.append((entry_name, group_name))
                            break
        
        if not matching_entries:
            return f"[[{tag_name}/{group_name}]]"
        
        # Determine count
        if count_spec:
            if ":" in count_spec:
                count_range = count_spec[1:]  # Remove the colon
                if "-" in count_range:
                    try:
                        min_count, max_count = map(int, count_range.split("-"))
                        count = random.randint(min_count, max_count)
                    except ValueError:
                        count = 1
                else:
                    try:
                        count = int(count_range)
                    except ValueError:
                        count = 1
            else:
                count = 1
        else:
            count = 1
        
        # Select random entries
        count = min(count, len(matching_entries))
        selected_entries = random.sample(matching_entries, count)
        
        # Replace with selected entry/group references
        replacements = []
        for entry_name, group_name in selected_entries:
            replacements.append(f"[{entry_name}/{group_name}]{remaining_text}")
        
        return ", ".join(replacements)
    
    def _process_entry_resolution(self, text: str, library_entries: Dict) -> str:
        """Step 3: Process [entry_name] and [entry_name/group_name] patterns."""
        def replace_entry_pattern(match):
            entry_name = match.group(1)
            group_name = match.group(2)
            
            if entry_name not in library_entries:
                return f"[{entry_name}]"
            
            entry_data = library_entries[entry_name]
            if not entry_data.get("active", True):
                return ""
            # Process entry
            if group_name:
                # Group reference: [entry_name/group_name]
                return self._process_group_reference(entry_data, group_name)
            else:
                # Full entry reference: [entry_name]
                return self._process_entry_output(entry_data)
        
        return re.sub(r'\[([^/\]]+)(?:/([^(\]]+))?\]', replace_entry_pattern, text)
    
    def _process_group_reference(self, entry_data: Dict, group_name: str) -> str:
        """Process a group reference within an entry."""
        groups = entry_data.get("groups", [])
        target_group = None
        
        for group in groups:
            if group.get("name") == group_name and group.get("active", True):
                target_group = group
                break
        
        if not target_group:
            return ""
        
        # Use entry and group defaults
        entry_weight = entry_data.get("weight", "1")
        group_weight = target_group.get("weight", "1")
        random_count = target_group.get("random", "")
        
        return self._process_group_output(target_group, entry_weight, group_weight, random_count, entry_data)
    
    def _process_entry_output(self, entry_data: Dict) -> str:
        """Process a full entry output."""
        # Use entry defaults
        weight = entry_data.get("weight", "1")
        random_count = entry_data.get("random", "")
        
        groups = entry_data.get("groups", [])
        active_groups = [g for g in groups if g.get("active", True)]
        
        if not active_groups:
            return ""
        
        # Apply random selection if specified
        if random_count and random_count != "" and random_count != "0":
            try:
                # Parse the random count string for active and inactive items
                active_part, inactive_part = self._parse_random_count(random_count)
                
                # Process active groups
                if active_part:
                    if active_part == "":
                        # Include all active groups (no change needed)
                        pass
                    elif "-" in active_part:
                        min_count, max_count = map(int, active_part.split("-"))
                        count = random.randint(min_count, max_count)
                        count = min(count, len(active_groups))
                        if entry_data.get("shuffle", False):
                            # Shuffle is true, use random sampling
                            active_groups = random.sample(active_groups, count)
                        else:
                            # Shuffle is false, preserve order by sampling indices first, then sorting
                            indices = random.sample(range(len(active_groups)), count)
                            indices.sort()  # Sort indices to preserve original order
                            active_groups = [active_groups[i] for i in indices]
                    else:
                        count = int(active_part)
                        count = min(count, len(active_groups))
                        if entry_data.get("shuffle", False):
                            # Shuffle is true, use random sampling
                            active_groups = random.sample(active_groups, count)
                        else:
                            # Shuffle is false, preserve order by sampling indices first, then sorting
                            indices = random.sample(range(len(active_groups)), count)
                            indices.sort()  # Sort indices to preserve original order
                            active_groups = [active_groups[i] for i in indices]
                
                # Process inactive groups if specified
                if inactive_part:
                    inactive_groups = [g for g in groups if not g.get("active", True)]
                    if inactive_part == "":
                        # Include no inactive groups (no change needed)
                        pass
                    elif "-" in inactive_part:
                        min_count, max_count = map(int, inactive_part.split("-"))
                        count = random.randint(min_count, max_count)
                        count = min(count, len(inactive_groups))
                        selected_inactive = random.sample(inactive_groups, count)
                        active_groups.extend(selected_inactive)
                    else:
                        count = int(inactive_part)
                        count = min(count, len(inactive_groups))
                        selected_inactive = random.sample(inactive_groups, count)
                        active_groups.extend(selected_inactive)
                        
            except (ValueError, TypeError):
                pass
        
        # Apply shuffling if specified
        if entry_data.get("shuffle", False):
            random.shuffle(active_groups)
        
        # Process each group
        group_outputs = []
        for group in active_groups:
            group_output = self._process_group_output(group, weight, group.get("weight", "1"), group.get("random", ""), entry_data)
            if group_output:
                group_outputs.append(group_output)
        
        return ",\n".join(group_outputs)
    
    def _process_group_output(self, group: Dict, entry_weight: str, group_weight: str, random_count: str, entry_data: Dict = None) -> str:
        """Process a group's output."""
        prompts = group.get("prompts", [])
        active_prompts = [p for p in prompts if p.get("active", True)]
        
        if not active_prompts:
            return ""
        
        # Apply random selection if specified
        if random_count and random_count != "" and random_count != "0":
            try:
                # Parse the random count string for active and inactive items
                active_part, inactive_part = self._parse_random_count(random_count)
                
                # Process active prompts
                if active_part:
                    if active_part == "":
                        # Include all active prompts (no change needed)
                        pass
                    elif "-" in active_part:
                        min_count, max_count = map(int, active_part.split("-"))
                        count = random.randint(min_count, max_count)
                        count = min(count, len(active_prompts))
                        if group.get("shuffle", False):
                            # Shuffle is true, use random sampling
                            active_prompts = random.sample(active_prompts, count)
                        else:
                            # Shuffle is false, preserve order by order_index
                            # First sort by order_index to ensure proper order
                            active_prompts.sort(key=lambda p: p.get("order_index", 0))
                            # Then sample indices and preserve order
                            indices = random.sample(range(len(active_prompts)), count)
                            indices.sort()  # Sort indices to preserve original order
                            active_prompts = [active_prompts[i] for i in indices]
                    else:
                        count = int(active_part)
                        count = min(count, len(active_prompts))
                        if group.get("shuffle", False):
                            # Shuffle is true, use random sampling
                            active_prompts = random.sample(active_prompts, count)
                        else:
                            # Shuffle is false, preserve order by order_index
                            # First sort by order_index to ensure proper order
                            active_prompts.sort(key=lambda p: p.get("order_index", 0))
                            # Then sample indices and preserve order
                            indices = random.sample(range(len(active_prompts)), count)
                            indices.sort()  # Sort indices to preserve original order
                            active_prompts = [active_prompts[i] for i in indices]
                
                # Process inactive prompts if specified
                if inactive_part:
                    inactive_prompts = [p for p in prompts if not p.get("active", True)]
                    if inactive_part == "":
                        # Include no inactive prompts (no change needed)
                        pass
                    elif "-" in inactive_part:
                        min_count, max_count = map(int, inactive_part.split("-"))
                        count = random.randint(min_count, max_count)
                        count = min(count, len(inactive_prompts))
                        selected_inactive = random.sample(inactive_prompts, count)
                        active_prompts.extend(selected_inactive)
                    else:
                        count = int(inactive_part)
                        count = min(count, len(inactive_prompts))
                        selected_inactive = random.sample(inactive_prompts, count)
                        active_prompts.extend(selected_inactive)
                        
            except (ValueError, TypeError):
                pass
        
        # Apply shuffling if specified
        if group.get("shuffle", False):
            random.shuffle(active_prompts)
        
        # Get prefix - group prefix overrides entry prefix
        prefix = ""
        if entry_data:
            entry_prefix = entry_data.get("prefix", "")
            group_prefix = group.get("prefix", "")
            # Group prefix overrides entry prefix
            prefix = group_prefix if group_prefix else entry_prefix
        
        # Process each prompt
        prompt_outputs = []
        for prompt in active_prompts:
            prompt_weight = prompt.get("weight", "1")
            
            # Calculate final weight
            final_weight = self._calculate_final_weight(entry_weight, group_weight, prompt_weight)
            
            prompt_text = prompt.get("context", "")
            # Apply prefix to prompt text
            if prefix:
                prompt_text = f"{prefix}{prompt_text}"
            
            if final_weight == 1.0:
                prompt_outputs.append(prompt_text)
            else:
                prompt_outputs.append(f"({prompt_text}:{final_weight:.1f})")
        
        return ", ".join(prompt_outputs)
    
    def _parse_random_count(self, random_count: str) -> tuple[str, str]:
        """
        Parse a random count string that may contain a colon to separate active and inactive item control.
        
        This method supports the advanced random selection algorithm that allows users to
        control both active and inactive items independently. The syntax supports:
        - Empty string ("") for "all active" or "no inactive"
        - Single numbers ("3") for exact counts
        - Ranges ("1-3") for random selection within bounds
        - Colon separation (":2") for active/inactive control
        
        Args:
            random_count: String like "", "3", "1-3", ":2", "2:1-3", etc.
            
        Returns:
            Tuple of (active_part, inactive_part) where each part can be "", "i", or "i-j"
            
        Examples:
            "" -> ("", "")           # All active, no inactive
            "3" -> ("3", "")        # 3 random active, no inactive
            "1-3" -> ("1-3", "")    # 1-3 random active, no inactive
            ":2" -> ("", "2")       # All active, 2 random inactive
            "2:1-3" -> ("2", "1-3") # 2 random active, 1-3 random inactive
        """
        if not random_count:
            return "", ""
        
        if ":" not in random_count:
            # No colon means only active items control
            return random_count, ""
        
        # Split by colon
        parts = random_count.split(":", 1)
        if len(parts) == 2:
            active_part = parts[0].strip()
            inactive_part = parts[1].strip()
            return active_part, inactive_part
        else:
            # Malformed colon syntax, treat as active only
            return random_count, ""
    
    def _calculate_final_weight(self, entry_weight: str, group_weight: str, prompt_weight: str) -> float:
        """
        Calculate the final weight by multiplying all weight components.
        
        This method implements a hierarchical weight system where weights are multiplied
        across three levels: entry, group, and prompt. This allows for fine-grained
        control over prompt emphasis in the final output.
        
        The method supports:
        - Static weights (e.g., "1.5")
        - Dynamic weight ranges (e.g., "1.0-2.0") that generate random weights
        - Automatic fallback to 1.0 for invalid inputs
        
        Args:
            entry_weight: Weight string from the entry level
            group_weight: Weight string from the group level  
            prompt_weight: Weight string from the prompt level
            
        Returns:
            Final calculated weight as a float
            
        Examples:
            entry="2", group="1.5", prompt="1" -> 3.0
            entry="1.0-2.0", group="1", prompt="1" -> random between 1.0-2.0
        """
        def parse_weight(weight_str: str) -> float:
            if isinstance(weight_str, (int, float)):
                return float(weight_str)
            
            if not isinstance(weight_str, str):
                return 1.0
            
            weight_str = weight_str.strip()
            
            if "-" in weight_str:
                try:
                    parts = weight_str.split("-")
                    if len(parts) == 2:
                        min_val = float(parts[0].strip())
                        max_val = float(parts[1].strip())
                        if min_val <= max_val:
                            # Generate random weight between min and max with 0.1 step
                            # Calculate the number of steps between min and max
                            steps = int((max_val - min_val) * 10)
                            if steps > 0:
                                # Generate random step index (0 to steps inclusive)
                                step_index = random.randint(0, steps)
                                # Calculate weight: min_val + (step_index * 0.1)
                                weight = min_val + (step_index * 0.1)
                                # Ensure weight doesn't exceed max_val
                                return min(weight, max_val)
                            else:
                                # If min and max are very close, return min_val
                                return min_val
                except ValueError:
                    pass
                return 1.0
            else:
                try:
                    return float(weight_str)
                except ValueError:
                    return 1.0
        
        entry_w = parse_weight(entry_weight)
        group_w = parse_weight(group_weight)
        prompt_w = parse_weight(prompt_weight)
        
        return entry_w * group_w * prompt_w
    
    def save_library_entry(self, entry_name: str, entry_data: Dict[str, Any]) -> bool:
        """Save a library entry to JSON file."""
        try:
            filename = f"{entry_name}.json"
            filepath = os.path.join(self.library_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(entry_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"Error saving library entry {entry_name}: {e}")
            return False
    
    def load_library_entry(self, entry_name: str) -> Dict[str, Any]:
        """Load a library entry from JSON file."""
        try:
            filename = f"{entry_name}.json"
            filepath = os.path.join(self.library_dir, filename)
            
            if not os.path.exists(filepath):
                return {}
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data
        except Exception as e:
            print(f"Error loading library entry {entry_name}: {e}")
            return {}
    
    def delete_library_entry(self, entry_name: str) -> bool:
        """Delete a library entry from disk."""
        try:
            filename = f"{entry_name}.json"
            filepath = os.path.join(self.library_dir, filename)
            
            if os.path.exists(filepath):
                os.remove(filepath)
            
            return True
        except Exception as e:
            print(f"Error deleting library entry {entry_name}: {e}")
            return False
    
    def list_library_entries(self) -> List[str]:
        """List all available library entry names."""
        try:
            entries = []
            for filename in os.listdir(self.library_dir):
                if filename.endswith('.json'):
                    entries.append(filename[:-5])  # Remove .json extension
            return sorted(entries)
        except Exception as e:
            print(f"Error listing library entries: {e}")
            return []
    
    def _remove_empty_prompts(self, text: str) -> str:
        """
        Remove empty and duplicate prompts from the final output text.
        
        This method:
        1. Separates the text by commas
        2. Filters out substrings that become empty after trimming
        3. Removes duplicate prompts (comparing stripped versions)
        4. Joins the remaining substrings back with ", " separator
        
        Args:
            text: The processed prompt text that may contain empty or duplicate prompts
            
        Returns:
            The filtered text with empty and duplicate prompts removed
        """
        if not text or text.strip() == "":
            return ""
        
        # Split by comma and process each part
        parts = text.split(',')
        filtered_parts = []
        seen_prompts = set()
        
        for part in parts:
            stripped_part = part.strip()
            # Keep the part if it's not empty and not a duplicate
            if stripped_part and stripped_part not in seen_prompts:
                filtered_parts.append(part)  # Keep original part (with original spacing)
                seen_prompts.add(stripped_part)
        
        # Join back with ", " separator
        return ", ".join(filtered_parts)

    def _debug(self, message: str):
        """Temporary debug logger for diagnosing prompt processing issues."""
        try:
            print(f"[PromptLibraryNode] {message}")
        except Exception:
            pass
    
    def search_entries_by_tag(self, tag: str) -> List[str]:
        """Search for entries containing a specific tag."""
        # This method is no longer functional since we removed the library cache
        # It would need to be called with actual entry data from the frontend
        print(f"Warning: search_entries_by_tag called but library cache is disabled")
        return []



