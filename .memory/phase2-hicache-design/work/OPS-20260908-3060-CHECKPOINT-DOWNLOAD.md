# OPS-20260908-3060 checkpoint download

- Task ID: `D3060-CHECKPOINT-DOWNLOAD-016`
- Orchestration epoch: `20260908-3060`
- Role: `devops-executor`
- Status: **blocked**
- Admission: `ENTRY: ACCEPT`
- Scope: download public `LostGentoo/Qwen3.5-4B-AWQ` to `/hy-model/models/Qwen3.5-4B-AWQ`; no server, benchmark, source/3090 modification, or deletion of existing data.

## Outcome

The download could not proceed because the remote `/hy-model` mount is read-only. The requested target directory could not be created. No checkpoint remains on the remote host. No alternate destination was used.

## Baseline evidence

Remote host: `I2aff9805ac001019d1`.

```text
DISK Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1    1.9T  921G  942G  50% /hy-model
TARGET ABSENT
```

Mount/path verification:

```text
TARGET    SOURCE               FSTYPE OPTIONS
/hy-model /dev/nvme0n1[/model] xfs    ro,relatime,attr2,inode64,logbufs=8,logbsize=32k,prjquota
ls: cannot access '/hy-model/models': No such file or directory
drwxr-xr-x 2 root root 6 Apr  3 2025 /hy-model
```

The public repository API listed these files for download: `.gitattributes`, `README.md`, `chat_template.jinja`, `config.json`, `generation_config.json`, `model.safetensors`, `model.safetensors.index.json`, `model_mtp.safetensors`, `processor_config.json`, `recipe.yaml`, `tokenizer.json`, and `tokenizer_config.json`.

## Command and result record

1. Remote baseline check over SSH to port `27460`: succeeded; `/hy-model` had approximately `942G` free and the target was absent.
2. Public repository metadata query: succeeded; repository identity was `LostGentoo/Qwen3.5-4B-AWQ`.
3. Resumable transfer command (`curl --location --continue-at - --retry 3`) attempted to create `/hy-model/models/Qwen3.5-4B-AWQ`: failed at:

   ```text
   mkdir: cannot create directory ‘/hy-model/models’: Read-only file system
   ```

4. The command was stopped before the large weight transfer could continue. It had written six transfer artifacts under `/root` after the failed directory change, including a 134074368-byte partial `model.safetensors`.
5. Cleanup removed only those six files created by this invocation: `/root/.gitattributes`, `/root/README.md`, `/root/chat_template.jinja`, `/root/config.json`, `/root/generation_config.json`, and `/root/model.safetensors`. Verification returned `ROOT_CANDIDATES_ABSENT`.
6. Final free-space check remained:

   ```text
   /dev/nvme0n1    1.9T  921G  942G  50% /hy-model
   ```

## Verification

- Target directory: not created.
- File inventory/size: no target inventory exists; no complete or partial checkpoint remains at the authorized target.
- Config quantization fields: not verified because `config.json` was not retained and the target is unavailable.
- Incomplete files/network errors: transfer was incomplete due to local remote filesystem error (`Read-only file system`), not a reported network failure.
- Server/benchmark/source changes: none performed.
- Existing data deletion: none; cleanup was restricted to artifacts created by this invocation.

## Open issues and follow-up

- **Blocking issue:** the remote `/hy-model` XFS mount is read-only. An authorized operator must make the data disk writable or provide a writable authorized mount at `/hy-model/models` before a new Task ID can retry the download.
- Retry, config verification, inventory/size verification, and checksum verification require a fresh Task ID after the mount state is corrected.
- This is preparation only; no Marlin acceptance was attempted.
