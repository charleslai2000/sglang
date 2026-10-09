# OPS-20260908-SSH-KEY

Status: done

## Authorized resources

- Local private key: `/home/dev-codex/.ssh/sglang_3060_ed25519`
- Remote target: `root@i-1.gpushare.com:27460`
- Remote authorized-keys file: `/root/.ssh/authorized_keys`

## Key evidence

- Type: ED25519
- Fingerprint: `SHA256:efH37RxPX487OKqEE4S8Wq0yHOiWIoHEE+11z7xfowg`
- Local private-key mode: `600`
- Remote exact public-key count: `1`

## Verification evidence

Command used: noninteractive SSH with `BatchMode=yes` and the authorized key.

```text
local_mode=600
local_fingerprint=256 SHA256:efH37RxPX487OKqEE4S8Wq0yHOiWIoHEE+11z7xfowg sglang-3060 (ED25519)
hostname=I2aff9805ac001019d1
identity_uid=0
key_count=1
```

No product files, branches, or remote source were modified.
