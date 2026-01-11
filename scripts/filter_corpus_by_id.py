import json
import os
import shutil

def filter_corpus():
    gold_file = 'data/p5_eval_pool/gold_hybrid_tbox.jsonl'
    target_file = 'data/p5_eval_pool/final/test_final.jsonl'
    backup_file = target_file + '.bak'

    # Check if files exist
    if not os.path.exists(gold_file):
        print(f"Error: Gold file not found at {gold_file}")
        return
    if not os.path.exists(target_file):
        print(f"Error: Target file not found at {target_file}")
        return

    # 1. Collect valid doc_ids from gold file
    valid_ids = set()
    print(f"Reading valid IDs from {gold_file}...")
    try:
        with open(gold_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    if 'doc_id' in data:
                        valid_ids.add(data['doc_id'])
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading gold file: {e}")
        return

    print(f"Found {len(valid_ids)} valid doc_ids.")

    # 2. Backup target file
    print(f"Backing up {target_file} to {backup_file}...")
    shutil.copy2(target_file, backup_file)

    # 3. Filter target file
    kept_count = 0
    removed_count = 0
    
    print(f"Filtering {target_file}...")
    temp_output = target_file + '.temp'
    
    try:
        with open(target_file, 'r', encoding='utf-8') as f_in, \
             open(temp_output, 'w', encoding='utf-8') as f_out:
            
            for line in f_in:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    doc_id = data.get('doc_id')
                    
                    if doc_id in valid_ids:
                        f_out.write(line)
                        kept_count += 1
                    else:
                        removed_count += 1
                except json.JSONDecodeError:
                    # Keep lines that fail to parse or skip? usually skip if broken
                    print("Warning: Skipping invalid JSON line")
                    removed_count += 1
                    
        # Replace original with filtered
        os.replace(temp_output, target_file)
        print(f"Done. Kept {kept_count} lines, removed {removed_count} lines.")
        
    except Exception as e:
        print(f"Error during filtering: {e}")
        if os.path.exists(temp_output):
            os.remove(temp_output)

if __name__ == "__main__":
    filter_corpus()
