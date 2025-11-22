import json
import argparse, yaml
from retrievers.text_retriever import BM25Retriever

def eval_text(cfg):
    ret = BM25Retriever(cfg["data_path"])
    golds = [json.loads(l) for l in open(cfg["qa_path"], "r", encoding="utf-8").read().splitlines() if l.strip()]
    correct = 0
    for item in golds:
        q = item["question"]
        gold = item["gold_answer"]
        hit = ret.retrieve(q, k=1)[0][0]["impact"]
        if gold in hit:
            correct += 1
    acc = correct / len(golds) if golds else 0.0
    print(f"Text BM25 accuracy: {acc:.2f} ({correct}/{len(golds)})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/demo.yaml")
    args = parser.parse_args()
    cfg = yaml.safe_load(open(args.config, "r", encoding="utf-8"))
    eval_text(cfg)
