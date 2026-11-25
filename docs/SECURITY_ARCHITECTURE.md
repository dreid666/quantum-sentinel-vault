# Cross-repository security architecture (proposal)

**Status:** design guidance only. This document does not implement, certify, or assert the availability of the controls below. The repositories remain independently built components. No merge, deployment, service endpoint, or cross-repository runtime integration is created by this document.

## Design boundary: no APIs

This architecture introduces no HTTP/REST, RPC, cloud callback, or externally listening service. Components are not to call one another through network endpoints. If a future integration is approved, exchange must use a reviewed, versioned artifact through an operator-controlled local file/spool or removable-media workflow, with integrity/authenticity verification, replay protection, size limits, and explicit operator action. Do not treat shared files as trusted merely because they are local. Any move to socket-based IPC needs a separately reviewed decision and is outside this no-API design.

## Modes and egress

- **OFFLINE is the default:** no DNS, cloud LLM, search, provider, telemetry, or network fallback. Missing local data or a required capability means unavailable/error, never silent online fallback.
- **ONLINE is a separate, explicit operator-selected mode:** disclose which external provider/host and data categories are involved; require consent and credentials from the platform secret store. Switching modes is explicit, audited, and does not happen automatically after an offline failure.
- Enforce egress at the host/firewall or device policy boundary. Application-level checks and source scans are supplemental and do not prove air-gapping. Offline builds must use pre-provisioned, verified dependencies; GitHub-hosted CI still communicates with GitHub.

## Identity, authorization, and approvals

Use the local OS account/device boundary for interactive access, least privilege for processes and files, and signed, versioned release artifacts where feasible. Never trust an LLM plan, input artifact, filename, local process, or claimed device identity as authorization. Validate issuer, signature, audience/purpose, expiry, nonce/replay status, schema, bounds, and policy before any state-changing action. High-impact actions require a human approval bound to the exact action digest; approval expires on any change. Denial, missing identity, invalid signature, policy uncertainty, or unavailable approver means no action.

## Secrets and sensitive data

Do not commit credentials, private keys, entropy, signing material, or production secrets. Use Android Keystore on Android and an OS/hardware-backed secret store or protected operator provisioning on hosts. Do not pass secrets in command-line arguments, logs, prompts, memory stores, audit records, or ordinary exchange artifacts. Keep provider credentials out of offline mode. Define rotation, revocation, backup, and recovery procedures before production use. A software-emulated PUF or deterministic simulator is not hardware entropy and must not be used as a root of trust.

## Audit and provenance

Record UTC time, component/build identity, mode, actor/device identity reference, event/action, decision, result, approval reference, and artifact digest. Redact secrets and minimize user data. Persist audit records locally with access controls; hash-linking can reveal modification but is not a substitute for protected storage, independent checkpoints, or signatures. If audit persistence or integrity verification is required for an action and unavailable, block that action. Do not claim a Merkle tree, tamper-proof ledger, hardware attestation, or immutable storage unless actually implemented and independently tested.

## Fail-closed state policy

Use explicit states: `OFFLINE_READY`, `ONLINE_READY`, `QUARANTINED`, `RECOVERY_PENDING`. Any integrity/authentication/policy failure enters quarantine; disable the affected capability, preserve evidence where safe, and require operator-led recovery. No autonomous release of a physical interlock, radio, SIM/eSIM profile, vault asset, or key after a model-selected remediation. Recovery requires independently verified signed software/configuration, valid operator authorization, a successful self-test, and an auditable manual release. If a check, clock, audit store, or required local dependency is unavailable, do not proceed with protected operations.

## Proposed artifact handoff (not yet implemented)

The only integration boundary in this proposal is an offline artifact exchange: producer writes a bounded, schema-versioned intent/evidence bundle into an operator-controlled staging area; consumer verifies signature and digest, rejects duplicates/expired or malformed bundles, applies local policy, and writes a result artifact plus audit event. Transfer is an explicit operator action. No executable code or arbitrary remediation script is accepted in a bundle. This is a design contract, not a deployed workflow.

## QFFRF / UPSM claims and implementation cautions

The supplied QFFRF/UPSM text is an unverified proposal, not a production hardware specification. No physical addresses, MMIO register values, transceiver-cut guarantees, QPUF/optical-lattice claims, 1,024-shot error rates, constant-time behavior, zeroization, cache timing, `no_std` kernel, or sub-microsecond bounds are adopted as facts. Do not write to the example addresses or build firmware against them. Real MMIO requires an identified board, vendor memory map, privilege model, electrical safety review, hardware-in-loop testing, and independent verification. Rust `volatile` writes and compiler-level branchless code alone do not prove secure zeroization or constant-time execution. The proposed weighted-energy solver needs fixed-point range/overflow analysis, signedness and scaling specifications, deterministic tie rules, bounds-safe parsing, and adversarial tests before implementation. Cryptographic integrity must use a reviewed standard construction and constant-time library comparisons; masked tags are not encryption or authentication.

Quantum SDK simulation is classical simulation unless execution on a named, verified QPU is evidenced. Do not infer quantum entropy, physical attestation, advantage, or quantum security from simulator state vectors or terminology.

## Component responsibilities in this system (proposed)

- **Edg30n3:** user interface, local mode/consent display, Android Keystore integration; no embedded provider credential and no direct hardware authority.
- **JARVIS v4:** planning and review only; generated plans are untrusted proposals, never authorization. Keep external backends disabled in offline mode; no untrusted `exec`/`eval` as a security boundary.
- **SQ-NET:** potential local bridge/daemon only after hardware and threat-model review; no autonomous physical control based solely on UPSM output.
- **Q-REZ:** offline policy and verification evidence; scans are signals, not proof of no network capability or certification.
- **quantum-sentinel-vault:** separately scoped vault/test component; no live asset or signing-key operation from model output. Smart contracts require independent review and deployment controls.

## Acceptance gates before implementation

1. Threat model, data classification, component owners, exact artifact format, and trust anchors reviewed.
2. Offline mode tested with OS-level egress denied, DNS blocked, and no cloud credentials present; all attempted egress and fallback paths fail safely.
3. Online-mode consent, destination allow-list, data minimization, timeouts, quotas, revocation, and audit redaction tested.
4. Authentication/replay/tamper/schema/size/approval tests pass for artifact exchange.
5. Fault injection covers missing/corrupt audit store, wrong signatures, stale approvals, clock rollback, malformed offsets/lengths, unavailable secrets, and partial writes.
6. Hardware claims are withheld until board-specific implementation and independent hardware-in-loop evidence exist.

**Current limitation:** this is a documentation proposal only. The repositories' existing behaviors may not satisfy these policies; in particular, direct web/cloud integrations and unsafe dynamic evaluation must be reviewed or removed before asserting strict offline operation.