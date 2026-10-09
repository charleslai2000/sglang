# G3-PROFILE-C-C6-LAUNCH-TRANSPORT3-20260908

## Status

blocked

## Evidence

- Verified v1 PID 486264 on `127.0.0.1:8035` before action.
- Candidate launch on `18036` used the requested capacity tuple (max-running 6,
  Mamba pool 32, decode graph max batch 8), but the remote shell transport
  stripped JSON quotes and SGLang rejected `'{preserve_thinking:false}'` before
  startup. No candidate traffic occurred.
- Candidate was not left running. v1 restore PID 487847 was launched with the
  frozen argv and is loading normally; health was still unavailable at the
  bounded observation window, with weight loading in progress.
- No product files, model files, or benchmark data were changed.

## Open issue

The argv-preserving retry command still needs a fresh dispatch using a robust
transport (for example, base64-encoded remote script). This invocation stops
here per the deterministic executor contract.
