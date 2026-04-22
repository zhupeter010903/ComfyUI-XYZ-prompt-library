from pathlib import Path
from gallery.metadata import read_comfy_metadata, ComfyMeta

# Test #1: ComfyUI-generated PNG (含 workflow + prompt 两个 chunk)
m = read_comfy_metadata(r"E:\AI\ComfyUI-aki-v2\ComfyUI\output\2026-04-17\09-40-54-883986218932892_底图_00001_.png")
assert m.has_workflow is True
assert m.errors == ()
assert m.positive_prompt and m.model and m.seed is not None
print("T1 OK", m)

from PIL import Image
from PIL.PngImagePlugin import PngInfo
info = PngInfo()
info.add_text("parameters",
    "beautiful sunset over the sea\n"
    "Negative prompt: ugly, blurry\n"
    "Steps: 20, Sampler: Euler a, CFG scale: 7, Seed: 12345, Model: sd15_foo")
Image.new("RGB", (8, 8), "black").save("a1111.png", pnginfo=info)

from gallery.metadata import read_comfy_metadata
m = read_comfy_metadata("a1111.png")
assert m.positive_prompt == "beautiful sunset over the sea"
assert m.negative_prompt == "ugly, blurry"
assert m.seed == 12345 and m.cfg == 7.0
assert m.sampler == "Euler a" and m.model == "sd15_foo"
assert m.has_workflow is False  # 只有 parameters chunk，没 workflow chunk
print("T2 OK", m)

# Test #3a: 普通 JPG —— 不抛、errors 非空、字段全空
m = read_comfy_metadata(r"C:\Users\XYZ\Downloads\定稿-1.jpg")
assert isinstance(m, ComfyMeta)
assert m.positive_prompt is None and m.has_workflow is False
assert len(m.errors) >= 1
print("T3a OK", m.errors)

# Test #3b: 损坏 PNG (随便填几字节)
Path("bad.png").write_bytes(b"\x89PNG\r\n\x1a\n_garbage_")
m = read_comfy_metadata("bad.png")
assert m.positive_prompt is None and m.errors
print("T3b OK", m.errors)

# Test #3c: 不存在的路径
m = read_comfy_metadata(r"C:\does\not\exist.png")
assert m.errors and "file not found" in m.errors[0]
print("T3c OK")

# Test #4: 无副作用 / 多次调用结果完全一致
p = r"E:\AI\ComfyUI-aki-v2\ComfyUI\output\2026-04-17\09-40-54-883986218932892_底图_00001_.png"
m1 = read_comfy_metadata(p)
m2 = read_comfy_metadata(p)
assert m1 == m2 and hash(m1) == hash(m2)
print("T4 OK")