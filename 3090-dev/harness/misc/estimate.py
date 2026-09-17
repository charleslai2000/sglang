import json, subprocess, os
m=json.load(open("/tmp/blind24_dataset_image_refs.json")) if os.path.exists("/tmp/blind24_dataset_image_refs.json") else None
