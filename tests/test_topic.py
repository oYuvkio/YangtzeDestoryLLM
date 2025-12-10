#!/usr/bin/env python3
"""测试脚本 - 运行 build_eval_pool 并输出结果"""
import sys
import traceback
from pathlib import Path

output_file = Path('/home/zjx/dev_ops/YangtzeDestoryLLM/test_topic_output.txt')

try:
    sys.path.insert(0, str(Path(__file__).parent))
    
    from tools.build_eval_pool import (
        load_segments_from_jsonl, _get_topic, sample_by_category, 
        split_dev_test, save_jsonl, Constants
    )
    from collections import Counter
    import random
    
    random.seed(42)
    
    jsonl_path = Path('/home/zjx/dev_ops/YangtzeDestoryLLM/data/corpus_for_kg/filtered_ytz_corpus/light_pool_dedup.jsonl')
    out_dir = Path('/home/zjx/dev_ops/YangtzeDestoryLLM/data/p5_eval_pool')
    
    segs = load_segments_from_jsonl(jsonl_path, 150, 3000)
    
    with output_file.open('w', encoding='utf-8') as f:
        f.write(f'Loaded {len(segs)} segments\n\n')
        
        topics = Counter(_get_topic(seg) for seg in segs)
        f.write('topic_label distribution:\n')
        for k, v in topics.most_common():
            f.write(f'  {k}: {v}\n')
        f.write('\n')
        
        # 使用默认 topic_label 目标
        target = dict(Constants.DEFAULT_TARGET_TOPIC)
        f.write(f'Target: {target}\n\n')
        f.flush()
        
        # 抽样
        f.write('Sampling...\n')
        f.flush()
        sampled = sample_by_category(segs, target, stratify_by='topic_label')
        f.write(f'Sampled: {len(sampled)} segments\n')
        f.flush()
        
        # 划分 Dev/Test
        dev, test = split_dev_test(sampled, 0.6, stratify_by='topic_label')
        f.write(f'Dev: {len(dev)}, Test: {len(test)}\n\n')
        
        # 保存
        out_dir.mkdir(parents=True, exist_ok=True)
        save_jsonl(sampled, out_dir / 'pool.jsonl')
        save_jsonl(dev, out_dir / 'dev.jsonl')
        save_jsonl(test, out_dir / 'test.jsonl')
        
        f.write(f'Saved to {out_dir}\n')
        f.write(f'  - pool.jsonl: {len(sampled)}\n')
        f.write(f'  - dev.jsonl: {len(dev)}\n')
        f.write(f'  - test.jsonl: {len(test)}\n')
    
    print(f'Done! See {output_file}')
except Exception as e:
    with output_file.open('w', encoding='utf-8') as f:
        f.write(f'ERROR: {e}\n')
        f.write(traceback.format_exc())
    print(f'Error: {e}')
