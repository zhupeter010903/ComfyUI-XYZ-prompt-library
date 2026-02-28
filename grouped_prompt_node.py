import json
import random
import os
from typing import Dict, List, Any, Union, Tuple

class GroupedPromptNode:
    """
    A custom node for ComfyUI that enables users to:
    - Enable/disable groups of prompted tags
    - Randomly sample prompt tags or prompt groups
    - Save/load prompt group templates
    """
    
    NAME = "Grouped Prompt Node"
    CATEGORY = "XYZNodes/Prompt"
    DESCRIPTION = "Manage grouped prompts with enable/disable, random sampling, and template saving"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                }),
            },
            "optional": {},
            "hidden": {
                "id": "UNIQUE_ID",
                "prompt_data": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "hidden": True
                })
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "process_prompts"
    
    def __init__(self):
        self.template_dir = os.path.join(os.path.dirname(__file__), "prompt_group_template")
        os.makedirs(self.template_dir, exist_ok=True)
    
    def process_prompts(self, id, seed, prompt_data="", **kwargs):
        """
        Process the prompt data according to the algorithm specified in the markdown.
        
        Args:
            id: Node ID
            prompt_data: JSON string containing prompt group data
            
        Returns:
            Tuple containing the processed prompt string
        """
        # Control randomness with provided seed
        try:
            random.seed(int(seed) if seed is not None else None)
        except Exception:
            pass

        if not prompt_data or prompt_data.strip() == "":
            return ("",)
        
        try:
            # Parse the JSON data from the frontend
            data = json.loads(prompt_data)
            if not isinstance(data, list):
                return ("",)
            
            group_prompt_list = []
            
            for prompt_group in data:
                # Respect enabled flag (default True)
                if not prompt_group.get("enabled", True):
                    continue

                # Get group weight
                group_weight = self._parse_weight(prompt_group.get("weight", "1"))
                
                active_prompts = []
                random_prompts = []
                
                # Process items in the group
                for item in prompt_group.get("items", []):
                    if item.get("type") == "prompt_tag":
                        self._process_prompt_tag(
                            item, group_weight, active_prompts, random_prompts
                        )
                    elif item.get("type") == "prompt_subgroup":
                        self._process_prompt_subgroup(
                            item, group_weight, active_prompts, random_prompts
                        )
                
                # Apply shuffling based on status
                status = str(prompt_group.get("status", "default")).strip()
                if status == "shuffle_active":
                    random.shuffle(active_prompts)
                
                # Get random prompts count
                random_count = self._parse_random_count(prompt_group.get("random_count", "0"))
                
                # Add randomly selected prompts
                if random_count > 0 and random_prompts:
                    selected_random = random.sample(
                        random_prompts, 
                        min(random_count, len(random_prompts))
                    )
                    prompts = active_prompts + selected_random
                else:
                    prompts = active_prompts
                
                # Apply final shuffling if specified
                if status == "shuffle_all":
                    random.shuffle(prompts)
                
                # Join prompts for this group
                if prompts:
                    group_prompt_list.append(", ".join(prompts))
            
            # Join all groups
            result = ",\n".join(group_prompt_list)
            return (result,)
            
        except Exception as e:
            print(f"Error processing grouped prompts: {e}")
            return ("",)
    
    def _process_prompt_tag(self, tag, group_weight, active_prompts, random_prompts):
        """Process a prompt tag item."""
        if tag.get("enabled", False):
            weight = group_weight * self._parse_weight(tag.get("weight", "1"))
            prompt_text = self._decode_newlines(tag.get("text", ""))
            
            if weight == 1:
                active_prompts.append(prompt_text)
            else:
                active_prompts.append(f"({prompt_text}:{weight:.1f})")
        
        elif tag.get("random_candidate", False):
            weight = group_weight * self._parse_weight(tag.get("weight", "1"))
            prompt_text = self._decode_newlines(tag.get("text", ""))
            
            if weight == 1:
                random_prompts.append(prompt_text)
            else:
                random_prompts.append(f"({prompt_text}:{weight:.1f})")
    
    def _process_prompt_subgroup(self, subgroup, group_weight, active_prompts, random_prompts):
        """Process a prompt subgroup item."""
        if not subgroup.get("enabled", True):
            return
        
        subgroup_weight = group_weight * self._parse_weight(subgroup.get("weight", "1"))
        
        for tag in subgroup.get("items", []):
            if tag.get("enabled", False):
                weight = subgroup_weight * self._parse_weight(tag.get("weight", "1"))
                prompt_text = self._decode_newlines(tag.get("text", ""))
                
                if weight == 1:
                    active_prompts.append(prompt_text)
                else:
                    active_prompts.append(f"({prompt_text}:{weight:.1f})")
            
            elif (subgroup.get("random_candidate", False) and 
                  tag.get("random_candidate", False)):
                weight = subgroup_weight * self._parse_weight(tag.get("weight", "1"))
                prompt_text = self._decode_newlines(tag.get("text", ""))
                
                if weight == 1:
                    random_prompts.append(prompt_text)
                else:
                    random_prompts.append(f"({prompt_text}:{weight:.1f})")

    def _decode_newlines(self, text: Any) -> str:
        """Convert literal backslash-n sequences ("\\n") to actual newlines ("\n")."""
        if isinstance(text, str):
            return text.replace("\\n", "\n")
        return ""
    
    def _parse_weight(self, weight_str: str) -> float:
        """Parse weight string in format 'a' or 'a-b'."""
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
                        steps = int((max_val - min_val) * 10) + 1
                        step_index = random.randint(0, steps)
                        return min_val + (step_index * 0.1)
            except ValueError:
                pass
            return 1.0
        else:
            try:
                return float(weight_str)
            except ValueError:
                return 1.0
    
    def _parse_random_count(self, count_str: str) -> int:
        """Parse random count string in format 'a' or 'b-c'."""
        if isinstance(count_str, int):
            return count_str
        
        if not isinstance(count_str, str):
            return 0
        
        count_str = count_str.strip()
        
        if "-" in count_str:
            try:
                parts = count_str.split("-")
                if len(parts) == 2:
                    min_val = int(parts[0].strip())
                    max_val = int(parts[1].strip())
                    if min_val <= max_val:
                        return random.randint(min_val, max_val)
            except ValueError:
                pass
            return 0
        else:
            try:
                return int(count_str)
            except ValueError:
                return 0
    
    def save_template(self, template_name: str, template_data: Dict[str, Any]) -> bool:
        """Save a prompt group template to JSON file."""
        try:
            filename = f"{template_name}.json"
            filepath = os.path.join(self.template_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(template_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"Error saving template {template_name}: {e}")
            return False
    
    def load_template(self, template_name: str) -> Dict[str, Any]:
        """Load a prompt group template from JSON file."""
        try:
            filename = f"{template_name}.json"
            filepath = os.path.join(self.template_dir, filename)
            
            if not os.path.exists(filepath):
                return {}
            
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading template {template_name}: {e}")
            return {}
    
    def list_templates(self) -> List[str]:
        """List all available template names."""
        try:
            templates = []
            for filename in os.listdir(self.template_dir):
                if filename.endswith('.json'):
                    templates.append(filename[:-5])  # Remove .json extension
            return sorted(templates)
        except Exception as e:
            print(f"Error listing templates: {e}")
            return []


# Node class mappings
NODE_CLASS_MAPPINGS = {
    "GroupedPromptNode": GroupedPromptNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GroupedPromptNode": "Grouped Prompt Node"
}
