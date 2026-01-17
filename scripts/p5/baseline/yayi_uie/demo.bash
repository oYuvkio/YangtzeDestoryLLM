conda activate yayi
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

CUDA_VISIBLE_DEVICES=0,1,2 python - <<'PY'
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_DIR="/hy-tmp/zjx/models/modelscope/wenge-research/yayi-uie"

tok = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=False, trust_remote_code=True)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_DIR,
    trust_remote_code=True,
    torch_dtype=torch.float16,
    device_map="auto",
    low_cpu_mem_usage=True,
    max_memory={0:"22GiB", 1:"22GiB", 2:"22GiB"},
)

print("hf_device_map:", getattr(model, "hf_device_map", None), flush=True)

prompt = "文本：张三在北京工作。\n【实体抽取】抽取文本中可能存在的实体，并以json{人物/地点：[实体]}格式输出。"
prompt = "<reserved_13>" + prompt + "<reserved_14>"
inputs = tok(prompt, return_tensors="pt").to(model.device)

with torch.no_grad():
    out = model.generate(**inputs, max_new_tokens=64, do_sample=False, temperature=0.0)

print(tok.decode(out[0], skip_special_tokens=True), flush=True)

# 让进程停 60 秒，方便你观察 nvidia-smi 显存占用（可删）
import time; time.sleep(60)
PY
