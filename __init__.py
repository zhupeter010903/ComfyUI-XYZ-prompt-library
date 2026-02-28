from .node import *
from .grouped_prompt_node import GroupedPromptNode
from .prompt_library_node import PromptLibraryNode

import os
import json
from aiohttp import web
from server import PromptServer


NODE_CLASS_MAPPINGS = {
    "XYZ Multi Text Concatenate": MultiTextConcate,
    "XYZ Multi Clip Encoder": MultiClipEncoder,
    "XYZ Multi Text Replace": MutiTextReplace,
    "XYZ Random String Picker": RandomStringPicker,
    # "XYZ Group Prompt Toggle": GroupedPromptToggle,
    "XYZ Grouped Prompts": GroupedPromptNode,
    "XYZ Prompt Library": PromptLibraryNode,
}

WEB_DIRECTORY = "./js"
__all__ = ["NODE_CLASS_MAPPINGS", "WEB_DIRECTORY"]


def _template_dir():
    return os.path.join(os.path.dirname(__file__), "prompt_group_template")


def _ensure_template_dir():
    os.makedirs(_template_dir(), exist_ok=True)


@PromptServer.instance.routes.get("/xyz/grouped_prompt/templates")
async def xyz_list_templates(request):
    try:
        _ensure_template_dir()
        names = []
        for filename in os.listdir(_template_dir()):
            if filename.endswith(".json"):
                names.append(filename[:-5])
        return web.json_response({"templates": sorted(names)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.get("/xyz/grouped_prompt/template/{name}")
async def xyz_get_template(request):
    name = request.match_info.get("name", "").strip()
    if not name:
        return web.json_response({"error": "missing name"}, status=400)
    try:
        _ensure_template_dir()
        filepath = os.path.join(_template_dir(), f"{name}.json")
        if not os.path.exists(filepath):
            return web.json_response({"error": "not found"}, status=404)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.post("/xyz/grouped_prompt/template")
async def xyz_save_template(request):
    try:
        payload = await request.json()
        name = (payload.get("name") or "").strip()
        data = payload.get("data")
        if not name or data is None:
            return web.json_response({"error": "missing name or data"}, status=400)

        override = False
        q = request.rel_url.query
        if "override" in q:
            override = q.get("override", "false").lower() in ("true", "1", "yes")

        _ensure_template_dir()
        filepath = os.path.join(_template_dir(), f"{name}.json")
        if os.path.exists(filepath) and not override:
            return web.json_response({"error": "exists"}, status=409)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# Prompt Library API routes
def _prompt_library_dir():
    return os.path.join(os.path.dirname(__file__), "prompt_library")


def _ensure_prompt_library_dir():
    os.makedirs(_prompt_library_dir(), exist_ok=True)


@PromptServer.instance.routes.get("/xyz/prompt_library/entries")
async def xyz_list_prompt_library_entries(request):
    try:
        _ensure_prompt_library_dir()
        entries = {}
        for filename in os.listdir(_prompt_library_dir()):
            if filename.endswith('.json'):
                filepath = os.path.join(_prompt_library_dir(), filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Index by entry ID instead of filename
                        entry_id = data.get("id")
                        if entry_id:
                            entries[entry_id] = data
                        else:
                            # Fallback to filename if no ID (for backward compatibility)
                            entry_name = filename[:-5]
                            entries[entry_name] = data
                except Exception as e:
                    print(f"Error loading library entry {filename}: {e}")
        return web.json_response({"entries": entries})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.get("/xyz/prompt_library/entry/{entry_id}")
async def xyz_get_prompt_library_entry(request):
    entry_id = request.match_info.get("entry_id", "").strip()
    if not entry_id:
        return web.json_response({"error": "missing entry id"}, status=400)
    try:
        _ensure_prompt_library_dir()
        
        # Find entry by ID
        for filename in os.listdir(_prompt_library_dir()):
            if filename.endswith('.json'):
                filepath = os.path.join(_prompt_library_dir(), filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        entry_data = json.load(f)
                        if entry_data.get("id") == entry_id:
                            return web.json_response(entry_data)
                except Exception:
                    continue
        
        return web.json_response({"error": "entry not found"}, status=404)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.post("/xyz/prompt_library/entry")
async def xyz_save_prompt_library_entry(request):
    try:
        payload = await request.json()
        entry_id = payload.get("id")
        data = payload.get("data")
        if not entry_id or data is None:
            return web.json_response({"error": "missing id or data"}, status=400)

        # Check if entry exists by ID
        _ensure_prompt_library_dir()
        existing_entry = None
        existing_filename = None
        
        # Search for existing entry by ID
        for filename in os.listdir(_prompt_library_dir()):
            if filename.endswith('.json'):
                filepath = os.path.join(_prompt_library_dir(), filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        entry_data = json.load(f)
                        if entry_data.get("id") == entry_id:
                            existing_entry = entry_data
                            existing_filename = filename
                            break
                except Exception:
                    continue

        # If entry exists, update it; otherwise create new
        if existing_entry:
            # Check if the name has changed
            old_name = existing_entry.get("name", "")
            new_name = data.get("name", "")
            
            if old_name != new_name:
                # Name changed - delete old file and create new one
                old_filepath = os.path.join(_prompt_library_dir(), existing_filename)
                if os.path.exists(old_filepath):
                    os.remove(old_filepath)
                
                # Create new filename based on new name
                safe_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                safe_name = safe_name.replace(' ', '_')
                filename = f"{safe_name}.json"
                filepath = os.path.join(_prompt_library_dir(), filename)
            else:
                # Name unchanged - use existing file
                filepath = os.path.join(_prompt_library_dir(), existing_filename)
        else:
            # Create new entry with name-based filename
            name = data.get("name", "New Entry")
            safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_name = safe_name.replace(' ', '_')
            filename = f"{safe_name}.json"
            filepath = os.path.join(_prompt_library_dir(), filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.post("/xyz/prompt_library/save_all")
async def xyz_save_all_prompt_library_entries(request):
    try:
        payload = await request.json()
        entries = payload.get("entries", {})
        
        if not entries:
            return web.json_response({"error": "no entries provided"}, status=400)

        _ensure_prompt_library_dir()
        saved_count = 0
        
        for entry_name, entry_data in entries.items():
            try:
                entry_id = entry_data.get("id")
                if not entry_id:
                    print(f"Warning: Entry {entry_name} has no ID, skipping")
                    continue
                
                # Check if entry exists by ID
                existing_filename = None
                for filename in os.listdir(_prompt_library_dir()):
                    if filename.endswith('.json'):
                        filepath = os.path.join(_prompt_library_dir(), filename)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                existing_data = json.load(f)
                                if existing_data.get("id") == entry_id:
                                    existing_filename = filename
                                    break
                        except Exception:
                            continue
                
                # Check if the name has changed
                old_name = None
                if existing_filename:
                    # Try to get old name from existing file
                    try:
                        old_filepath = os.path.join(_prompt_library_dir(), existing_filename)
                        with open(old_filepath, 'r', encoding='utf-8') as f:
                            old_data = json.load(f)
                            old_name = old_data.get("name", "")
                    except Exception:
                        pass
                
                new_name = entry_data.get("name", "")
                
                # Use existing filename if found and name unchanged, otherwise create new
                if existing_filename and old_name == new_name:
                    filename = existing_filename
                else:
                    # Name changed or new entry - create new filename
                    if existing_filename and old_name != new_name:
                        # Delete old file if name changed
                        old_filepath = os.path.join(_prompt_library_dir(), existing_filename)
                        if os.path.exists(old_filepath):
                            os.remove(old_filepath)
                    
                    # Create new filename based on new name
                    safe_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    safe_name = safe_name.replace(' ', '_')
                    filename = f"{safe_name}.json"
                
                filepath = os.path.join(_prompt_library_dir(), filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(entry_data, f, indent=2, ensure_ascii=False)
                saved_count += 1
            except Exception as e:
                print(f"Error saving entry {entry_name}: {e}")
                continue

        return web.json_response({
            "ok": True, 
            "saved_count": saved_count,
            "total_count": len(entries)
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.delete("/xyz/prompt_library/entry/{entry_id}")
async def xyz_delete_prompt_library_entry(request):
    entry_id = request.match_info.get("entry_id", "").strip()
    if not entry_id:
        return web.json_response({"error": "missing entry id"}, status=400)
    try:
        _ensure_prompt_library_dir()
        
        # Find and delete entry by ID
        for filename in os.listdir(_prompt_library_dir()):
            if filename.endswith('.json'):
                filepath = os.path.join(_prompt_library_dir(), filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        entry_data = json.load(f)
                        if entry_data.get("id") == entry_id:
                            os.remove(filepath)
                            return web.json_response({"ok": True})
                except Exception:
                    continue
        
        return web.json_response({"error": "entry not found"}, status=404)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)