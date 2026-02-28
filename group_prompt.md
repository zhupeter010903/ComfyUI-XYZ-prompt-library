# Grouped prompt node

Grouped_prompt_node is a custom node for Comfyui, the purpose is to enable user to enable/disable groups of prompted tags, randomly sample prompt tags or prompt groups, and save/load prompt group templates

## front end structure

**The node should have the following root features:**

- a button to add prompt groups
- a dropdown menu and a button to load prompt groups from json files saved in ComfyUI-XYZNodes/prompt_group_template folder
- a list of vertically orientated prompt group items
- self-adjustable height to fit the prompt group list

**Each prompt group should have the following feature:**

- a button to enable/disable the entire prompt group. The disable groups will be ignored at output stage
- a name label
- a remove button
- an expand button to open a secondary floating window, with detailed informations about this prompt group

**A secondary floating window should have the following feature:**

- a button to add a prompt tag
- a button to add a prompt subgroup
- a button to close the floating window
- an editable text label and a save button to edit the group name
- a text input for weights that will apply to the entire prompt group. The text input this either "a" or "a-b", where a<b are numbers between 0.0 to 2.0. In the case "a": it means the backend should apply a weight of a to each prompt in the prompt group. In the case "a-b": the backend should first generate a uniformly random weight between a and b with step 0.1, and then apply that weight to all prompts in this group. The default value is 1.
- a text input to control the number of randomly picked prompt tags or prompt subgroups. The input is either an integer "a", or an integer range "b-c", the later means the backend should first pick a random integer *a* between *b* and *c*. At backend's output stage, other then the enabled prompt tags and prompt subgroups, the backend should randomly sample *a* disabled prompt tags or disabled prompt subgroups and add then to the list of output prompts. The default value is 0.
- A save button the save the current prompt group as a json file in the ComfyUI-XYZNodes/prompt_group_template folder, and which can be used to read in and recreate the prompt group. The json file should keep track of the state of all prompt tags and prompt subgroups. If a json file for this group already exists, the save button will update it.
- a status button with three states: default, shuffle active, shuffle all.
- a mixed list of verticalled orientated prompt tags and prompt subgroups

**A prompt tag item should have the following feature:**

- a disable/enable button
- up/down buttons to move the prompt tag one index order up or down in the group list or subgroup list
- an editable text input, which carries the actual prompt string representated by this prompt tag
- an editable text input for weight of this prompt tag, like above, the input can be of the format "a" or "a-b"
- a button to enable/disable this prompt tag being valid candidate for random sample. If being disabled, this tag will not be randomly sampled by the backend.
- a move button, which will open a dropdown menu, to move the prompt tag into any subgroup under the current parent group, or to move it directly under the parent group
- a remove delete button

**A prompt subgroup item should have the following feature:**

- a disable/enable button
- up/down buttons to move the prompt subgroup one index order up or down in the group list
- an editable text input for name
- an editable text input for weight of this prompt subgroup, like above, the input can be of the format "a" or "a-b"
- a button to enable/disable this prompt subgroup being valid candidate for random sample. If being disabled, the prompts in this subgroup will not be randomly sampled by the backend.
- a remove delete button

**Output format**
Everything in the frontend of the node should be packed into a hidden multiline text input in json format for the backend. Then backend will extract and process data from the json, and output a text string. The string output should be generated according to the following algorithm:

```
# pesudocode
group_prompt_list = []
for each prompt group p:
  if p.disabled: pass
  group_weight = p.weight
  active_prompts = []
  random_prompts = []
  for item in p:
    if item is prompt tag:
      if item is enabled:
        weight = group_weight *item.weight
        if weight == 1:
          active_prompts.append("${item.prompt}")
        else:
          active_prompts.append("(${item.prompt}:weight)")
      else if item.ramdom_candiate is enabled:
        weight = group_weight* item.weight
        if weight == 1:
          random_prompts.append("${item.prompt}")
        else:
          random_prompts.append("(${item.prompt}:weight)")
    if item is prompt subgroup:
      if item is disabled: pass
      subgroup_weight = group_weight *item.weight
      for tag in item:
        if tag is enabled:
        weight = subgroup_weight* tag.weight
          if weight == 1:
            active_prompts.append("${tag.prompt}")
          else:
            active_prompts.append("(${tag.prompt}:weight)")
        else if item.ramdom_candiate is enabled && tag.ramdom_candiate is enabled:
          weight = subgroup_weight * tag.weight
          if weight == 1:
            random_prompts.append("${tag.prompt}")
          else:
            random_prompts.append("(${tag.prompt}:weight)")
  if p.shuffle_active:
    shuffle active_prompts
  prompts = active_prompts + [randomly picked n distinct prompts from random_prompts]
  if p.shuffle_all:
    shuffle prompts
  group_prompt_list.append(prompts.join(", "))
return group_prompt_list.join(",\n")
```

**References:**
backend:

- <https://docs.comfy.org/custom-nodes/backend/server_overview>
- <https://docs.comfy.org/custom-nodes/backend/lifecycle>
- <https://docs.comfy.org/custom-nodes/backend/datatypes>
- <https://docs.comfy.org/custom-nodes/backend/more_on_inputs>
- <https://docs.comfy.org/custom-nodes/backend/lists>

frontend:

- <https://docs.comfy.org/custom-nodes/js/javascript_overview>
- <https://docs.comfy.org/custom-nodes/js/javascript_hooks>
- <https://docs.comfy.org/custom-nodes/js/javascript_objects_and_hijacking>
- <https://docs.comfy.org/custom-nodes/js/javascript_dialog>
- <https://docs.comfy.org/custom-nodes/js/javascript_examples>
