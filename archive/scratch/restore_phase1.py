import json
import traceback

full_path = r'C:\Users\edtli\.gemini\antigravity\brain\7c137a69-7b2b-4715-a243-ec0297549714\.system_generated\logs\transcript_full.jsonl'

def get_args(step_num):
    with open(full_path, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f, 1):
            if idx == step_num:
                data = json.loads(line)
                for tc in data.get('tool_calls', []):
                    args = tc.get('args', {})
                    res = {}
                    for k, v in args.items():
                        if isinstance(v, str) and (v.startswith('"') or v.startswith('{')):
                            try:
                                res[k] = json.loads(v)
                            except Exception:
                                res[k] = v
                        else:
                            res[k] = v
                    return res

print('[*] Extracting from transcript_full.jsonl...')

# 1. index.html: base 752, edits: 842, 873, 966
idx_code = get_args(752)['CodeContent']
for s in [842, 873, 966]:
    args = get_args(s)
    idx_code = idx_code.replace(args['TargetContent'], args['ReplacementContent'])
with open('scratch/index_restored.html', 'w', encoding='utf-8') as f:
    f.write(idx_code)
print('Restored index.html, len:', len(idx_code))

# 2. studio.css: base 748, edits: 788, 832
css_code = get_args(748)['CodeContent']
for s in [788, 832]:
    args = get_args(s)
    css_code = css_code.replace(args['TargetContent'], args['ReplacementContent'])
with open('scratch/studio_restored.css', 'w', encoding='utf-8') as f:
    f.write(css_code)
print('Restored studio.css, len:', len(css_code))

# 3. server.py: base 824, edits: 962, 1127
srv_code = get_args(824)['CodeContent']
for s in [962, 1127]:
    args = get_args(s)
    srv_code = srv_code.replace(args['TargetContent'], args['ReplacementContent'])
with open('scratch/server_restored.py', 'w', encoding='utf-8') as f:
    f.write(srv_code)
print('Restored server.py, len:', len(srv_code))

# 4. compiler.py: base 760, edits: 766, 770
cmp_code = get_args(760)['CodeContent']
for s in [766, 770]:
    args = get_args(s)
    cmp_code = cmp_code.replace(args['TargetContent'], args['ReplacementContent'])
with open('scratch/compiler_restored.py', 'w', encoding='utf-8') as f:
    f.write(cmp_code)
print('Restored compiler.py, len:', len(cmp_code))

# 5. app.js: base 970, edits: 975, 1065, 1067, 1143, 1145, 1149, 1262, 1291
app_code = get_args(970)['CodeContent']
for s in [975, 1065, 1067, 1143, 1145, 1149, 1262, 1291]:
    args = get_args(s)
    target = args['TargetContent']
    rep = args['ReplacementContent']
    if target in app_code:
        app_code = app_code.replace(target, rep)
    else:
        print(f"Warning: Target for step {s} not found in app_code!")
with open('scratch/app_restored.js', 'w', encoding='utf-8') as f:
    f.write(app_code)
print('Restored app.js, len:', len(app_code))
