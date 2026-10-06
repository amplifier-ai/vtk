# VTK SDK deep-review ledger

Repository: `amplifier-ai/vtk`.
Pull request: [VTK PR 4](https://github.com/amplifier-ai/vtk/pull/4).
Original committed-range base: `190f3c0ce64af90fa9996ad0b5954d23e50f8582`.
Original reviewed head: `64c1bca5d8c4d38f7a99ab0f38b0faad472b7860`.
Scope mode: committed range; every per-finding source read uses an explicit Git snapshot.
User-selected workflow: MeddyLib deep-review skill with its reviewer and finding-record contracts.
No existing findings; first independent cycle allocated with next ID `F-001`.
Reports and immutable finding packets are appended before any source edits.
Current lifecycle is recorded by stable finding IDs and exact closure evidence.

## Deep Review Cycle 1

**Scope**: PR [amplifier-ai/vtk#4](https://github.com/amplifier-ai/vtk/pull/4), committed range `190f3c0ce64af90fa9996ad0b5954d23e50f8582..64c1bca5d8c4d38f7a99ab0f38b0faad472b7860`: all 21 changed files, plus importers and supporting installation/generation paths. All source evidence below refers to HEAD `64c1bca5d8c4d38f7a99ab0f38b0faad472b7860`, except explicitly identified BASE evidence. Per-finding source reads used explicit `git show` snapshots.

**Verdict**: 🟡 minor findings — two open findings; no demonstrated runtime or clinical blocker.

Changed files reviewed:

- `.github/sdk/`: `README.md`, `package_csharp.py`, `package_sdk.py`, `validate_release.py`, `verify_csharp.py`, `verify_sdk.py`.
- `.github/sdk/csharp-consumer/`: `CSharpRuntimeConsumer.csproj`, `Program.cs`.
- `.github/sdk/tests/`: `test_csharp_runtime.py`, `test_publication.py`, `test_release_tags.py`, `test_release_validation.py`, `test_sdk.py`.
- `.github/workflows/`: `csharp-bindings.yml`, `native-sdk.yml`.
- `Wrapping/CSharp/Testing/`: `CMakeLists.txt`, `CSharpBindingCoverage.cs`, and `BindingCoverageRegression/{BindingCoverageRegression.csproj,Program.cs,StubWrappers.cs}`.
- `Wrapping/CSharp/vtk/`: `VtkNativeLibrary.cs.in`.

Existing evidence was read as qualification context: run `37364380166`, attempt 3, completed successfully; both SDK receipts and both runtime receipts identify the exact HEAD and report successful consumers. Stored coverage logs show 159 tested classes and zero errors on each platform, and zero failing synthetic regression cases. This does not demonstrate master publication.

### Cycle 1: Importer audit

The changed public surfaces are the new packaging/validation helpers and CLIs, the macOS deployment contract, resolver search ordering, and coverage-runner failure behavior. Importers inspected include both workflows, all five changed Python test modules, the C# consumer, `Wrapping/CSharp/{CMakeLists.txt,Testing/Program.cs,Testing/VTK.CSharp.Tests.csproj.in}`, the regression project, `vtkObjectBase.cs`, `CMake/vtkModuleWrapCSharp.cmake`, and the native-library names emitted by `Wrapping/Tools/vtkParseCSharp.c`. Signatures, CLI arguments, manifest fields, installed paths, generated import names and test registration remain compatible. No importer breakage was found. Publication dependency consistency produces F-001.

### Cycle 1: Control-&-data-flow audit

Traced installed SDK → recursive dependency queue → basename collision checks → macOS import/rpath rewriting and signing → runtime inventory → archive → extraction → native validation → .NET consumer. Production calls at `csharp-bindings.yml:336-342,377-380` activate both platforms, the Windows dependency-directory branch and the macOS minimum-version branch. ONNX qualification is explicitly macOS-only at `verify_csharp.py:95-96`.

The portability risks are guarded by dependency resolution/collision checks at `package_csharp.py:194-268` and post-rewrite validation at `131-161`. Coverage failures reach error accounting at `CSharpBindingCoverage.cs:99-151`, including disposal after failed `GetClassName`. Publication flow realizes F-001 when `build` succeeds and `sdk_unit` fails. No numeric/geometric algorithm changes or unresolved default-only dead path were found.

### Cycle 1: Behaviour-change audit

Resolver precedence moves packaged locations ahead of build/system locations at `VtkNativeLibrary.cs.in:72-111`; resolver installation and macOS warmup remain at their existing initialization boundary. Coverage disposal moves into `finally` at `CSharpBindingCoverage.cs:114-128`, preserving cleanup after constructor/name failures and counting disposal failures. SDK verification removes the original installation before runtime verification; `verify_csharp.py:104-123` additionally hides/restores the build and records the result. No construction-time validator, cached-property or lifecycle invariant was demoted.

### Cycle 1: Findings

| # | Item | Review status | Finding IDs / evidence |
| --- | --- | --- | --- |
| 1 | New-feature completeness | ⚠️ | F-001: C# publication does not require the unit job. |
| 2 | Test-name vs implementation | ✅ | Dependency, alias, collision, restoration and release tests assert their named behavior. |
| 3 | Dead code / redundant guards / defensive coercion / silent-failure surfaces | ✅ | Recursive closure fails on unresolved/colliding dependencies; required wrapper failures become errors. |
| 4 | Docstring invariants | ✅ | Archive isolation, relative dependencies and restoration claims have corresponding guards. |
| 5 | Cross-platform | ✅ | ZIP/tar, aliases, Windows case folding/redist resolution and macOS deployment/signing paths inspected. |
| 6 | Cross-call-site consistency | ⚠️ | F-001: sibling publishers require different prerequisite jobs. |
| 7 | Naming = behaviour | ✅ | Packaging, extraction, validation and coverage operations match their names. |
| 8 | Error-message quality | ⚠️ | F-002: new identity/version gates omit compared values. |
| 9 | Wire format / contract version | ✅ | New runtime manifest declares schema 1; no workspace wire format or version contract changes. |
| 10 | Documentation drift | ⚠️ | F-001: documented unit-check publication gate exceeds the C# dependency graph. |
| 11 | Test coverage (100 %, FDA / IEC 62304) | ⚠️ | No additional finding ID: branch tests and stored execution evidence inspected; 100% line/branch coverage remains unverified. Clinical Class C coverage classification is N/A here. |
| 12 | FDA / regulatory traceability | ✅ | N/A: no clinical threshold, algorithm, measurement semantics, patient-data path or workspace result changes. |

| ID | Finding | Severity | Fix status | Location |
| --- | --- | --- | --- | --- |
| F-001 | C# release can publish while the packaging unit job fails | minor | fixed | `.github/workflows/csharp-bindings.yml:460` |
| F-002 | New identity/version failure diagnostics omit actual and expected values | minor | fixed | `.github/sdk/package_csharp.py:143` |

### Cycle 1: Finding packets

#### F-001 — C# release can publish while the packaging unit job fails

- **Severity**: minor.
- **Location / affected surface**: `.github/workflows/csharp-bindings.yml:458-460`; stable C# releases and their two runtime archives.
- **Expected contract**: `.github/sdk/README.md:61-65` states that platform and unit checks gate publication. The new runtime packaging tests belong to the producer’s complete unit suite.
- **Observed evidence and reachability**: The Ubuntu `sdk_unit` job runs that suite at `csharp-bindings.yml:427-444`. Native publication requires `[build, sdk_unit]` at `446-448`, while C# publication requires only `build` at `458-460`. A master push with successful platform builds and failed `sdk_unit` therefore blocks native publication but leaves C# publication eligible to create a stable release at `494-504`. The macOS build also runs the suite at `75-77`; that duplicate execution does not enforce success of the Ubuntu job. The missing dependency existed at BASE `csharp-bindings.yml:487-489`, but remains an uncovered gate for the new runtime packaging contract.
- **Consequence**: Public runtimes can be released from a producer workflow whose required packaging unit job failed, contrary to the documented publication boundary.
- **Recommended remedy**: Require `[build, sdk_unit]` for the C# release job.
- **Alternatives considered**: Treating the macOS duplicate suite as sufficient would require an explicit documented exception and leave the failed Ubuntu job outside publication eligibility. Matching the existing native publisher is the smaller, clearer correction.
- **Closure criteria**: Both publication jobs require successful `build` and `sdk_unit`; add a workflow dependency regression assertion covering the C# release. Run the packaging suite and verify that a failed/skipped unit prerequisite cannot make either publisher eligible. A PR run alone does not prove actual publication behavior.

#### F-002 — New identity/version failure diagnostics omit actual and expected values

- **Severity**: minor.
- **Location / affected surface**: `.github/sdk/package_csharp.py:126-127,141-147`; `.github/sdk/verify_csharp.py:80-86`; `.github/sdk/validate_release.py:96-98`.
- **Expected contract**: Review checklist 8 requires failure diagnostics to identify the field/path and actual versus expected values so the failing artifact can be diagnosed from its receipt or log.
- **Observed evidence and reachability**: For a dylib with minimum macOS `27.0` against contract `26.0`, `package_csharp.py:142-143` rejects it but omits `27.0`; the existing negative fixture exercises this input at `test_csharp_runtime.py:159-166`. Native identity/rpath failures at `144-147` also omit observed values. A stale runtime source SHA reaches `verify_csharp.py:84-86`, whose error prints neither SHA. Publication receipt mismatches at `validate_release.py:96-98` print the field/platform but omit both compared values; the mismatch tests at `test_release_validation.py:66-75` check only the field name.
- **Consequence**: These gates fail safely, but troubleshooting the wrong source, deployment requirement or package identity requires reopening artifacts or re-running inspection.
- **Recommended remedy**: Include the relevant library/manifest/receipt field, its actual value and the expected value in these new comparison diagnostics. Preserve the existing checks.
- **Alternatives considered**: Dumping complete manifests would add unnecessary log noise. Reporting only the failing field and compared values supplies the missing evidence directly.
- **Closure criteria**: Negative tests assert field/path plus both actual and expected values for deployment-version, source/platform and receipt-identity mismatches; the packaging suite passes with unchanged rejection behavior.

### Cycle 1: Action items

1. **F-001** — Align C# publication prerequisites with native publication and add the dependency regression assertion.
2. **F-002** — Complete the new comparison diagnostics and strengthen the corresponding negative assertions.

Both findings remain open; this reviewer made no changes.

### Cycle 1: Sister-skill triggers

- **Available `devils-advocate` Codex prompt**: triggered for publication execution claims; separate read-only review returned 🟡 and independently confirmed F-001. Its other inspected source-identity, tag-uniqueness and archive-preservation guarantees were supported.
- **`security-checker`**: trigger applies to subprocess/file I/O/deserialization. Unavailable in the actual SDK/umbrella Codex prompt inventory; no specialist security verdict is claimed. Scoped inspection covered fixed argument arrays, archive path validation, package containment, dependency resolution and digest checks.
- **Licensing specialist**: dependency redistribution/license evidence warrants domain attention, but no owning SDK/umbrella prompt is available. Copying evidence is not a legal-sufficiency verdict.
- **Regulatory, clinical-reference, fact-check, HIPAA, translation, ITK/Slicer and device specialists**: N/A to this producer/packaging review; no clinical claims, patient payloads, citations, localization or imaging-coordinate logic changed.
- **Docstring rendering hooks**: N/A trigger; no new multiline structured API docstring requires the MeddyLib documentation toolchain.

Dynamic inventory was checked before delegation: the SDK exposes no Codex prompt assets; the umbrella exposes `devils-advocate` and `pr-creator`. No named Claude role or unavailable specialist verdict was fabricated.

### Cycle 1: Skipped checks

- Jira issue fetch: no ticket key supplied or present in the branch scope.
- Tests, pre-commit, builds and executable documentation examples: intentionally not run under the read-only review contract.
- Measured 100% line/branch coverage and test-mutation effectiveness: needs runtime verification; stored passing receipts establish execution of named checks, not exhaustive branch coverage.
- Workspace schema/fixture field matrices and `get_version()` bumps: N/A; no such models changed.
- FDA classification, clinical traceability and clinical qualification: N/A to the reviewed behavior; no regulatory classification was inferred.
- Live master publication, remote tag/asset readback, notarization and Unity activation: outside scope; the supplied PR evidence does not establish these outcomes.

### Cycle 1 execution evidence

- F-001 transitioned from open to in progress. New publication dependency regression failed before the fix: C# release has scalar `needs: build`, missing `sdk_unit`; native publisher already has both prerequisites. Command: `python3 -B -m unittest discover -s .github/sdk/tests -p test_publication.py -q`, exit 1, one failing release subcase.

- F-001 targeted publication tests now pass: 5 tests, exit 0. Lifecycle remains in progress until full validation and independent rereview.
- F-002 transitioned to in progress after portable read-only Python fix planning. Plan: keep all predicates and ordering, print only field/path plus compared values, extract the verifier manifest identity checks into a small runtime-free helper, and add negative message assertions and positive acceptance cases. No unavailable named specialist verdict is claimed.

- Additional SDK Markdown validation initially reported the parent-authored bare URL and table separator formatting in the ledger. Formatting corrected without changing finding packets or disabling any rule; the full canonical umbrella pre-commit run remains separate.

- F-002 negative diagnostics first failed before the message/helper edits: full SDK suite exit 1, 11 failures and 7 missing-helper subcase errors. After edits, the full suite passed 58 tests, including rejection diagnostics and preserved normalized-minimum/optional-source acceptance.
- Full canonical umbrella `uvx pre-commit run --all-files` passed every configured hook. VTK has no own pre-commit configuration; target-specific full SDK unit discovery, full actionlint with shellcheck/pyflakes, SDK README/ledger Markdown validation and `git diff --check` additionally passed. No check was weakened or suppressed.
- F-001 and F-002 table rows transitioned to fixed after their closure tests and validation passed. A fresh independent cycle over the entire original scope plus fixes is still required; the prior exact-head CI proves the original candidate, not these uncommitted edits.

## Deep Review Cycle 2

**Scope**: [VTK PR 4](https://github.com/amplifier-ai/vtk/pull/4), entire original change plus all fixes: BASE commit `190f3c0ce64af90fa9996ad0b5954d23e50f8582` compared with immutable tree `d9f4eff9755bfa2ad227adcae3205512df01c4f3`. Original PR HEAD remains `64c1bca5d8c4d38f7a99ab0f38b0faad472b7860`. Review used `git diff BASE TREE` and explicit `git show TREE:path` source reads. The mutable working tree and review ledger were excluded from source judgment.

**Verdict**: 🟢 all clear within the reviewed scope — no new actionable findings. F-001 and F-002 are addressed by the snapshot. No new finding ID was allocated; the next available ID remains F-003.

Changed files reviewed:

- `.github/sdk/`: `README.md`, `package_csharp.py`, `package_sdk.py`, `validate_release.py`, `verify_csharp.py`, `verify_sdk.py`.
- `.github/sdk/csharp-consumer/`: `CSharpRuntimeConsumer.csproj`, `Program.cs`.
- `.github/sdk/tests/`: `test_csharp_runtime.py`, `test_publication.py`, `test_release_tags.py`, `test_release_validation.py`, `test_sdk.py`.
- `.github/workflows/`: `csharp-bindings.yml`, `native-sdk.yml`.
- `Wrapping/CSharp/Testing/`: `CMakeLists.txt`, `CSharpBindingCoverage.cs`, and `BindingCoverageRegression/{BindingCoverageRegression.csproj,Program.cs,StubWrappers.cs}`.
- `Wrapping/CSharp/vtk/`: `VtkNativeLibrary.cs.in`.

The ledger records 58 passing SDK unit tests, a successful full canonical umbrella pre-commit run, and successful SDK workflow/Markdown/diff checks after the fixes. These are parent-recorded execution results, not tests rerun by this reviewer. Prior CI evidence for the original PR HEAD does not qualify the uncommitted snapshot on either platform.

### Cycle 2: Importer audit

Audited the new packaging and validation helpers, CLI arguments, manifest/receipt consumers, resolver directory ordering, and coverage-runner return behavior. Importers and supporting paths inspected include both workflows, all five changed Python test modules, both consumer projects, `Wrapping/CSharp/{CMakeLists.txt,Testing/Program.cs,Testing/VTK.CSharp.Tests.csproj.in}`, the synthetic regression project, `vtkObjectBase.cs`, `CMake/vtkModuleWrapCSharp.cmake`, and the generated native names in `Wrapping/Tools/vtkParseCSharp.c`. Installed paths, generated import names, signatures, manifest fields and test registration remain compatible. The extracted `validate_manifest_contract` helper is called at the original validation boundary. No importer breakage was found.

### Cycle 2: Control-&-data-flow audit

Traced installed SDK → dependency queue → collision checks → macOS rewriting/signing → runtime inventory → archive/extraction → native validation → isolated .NET consumer → publication. Both platform branches are active at `csharp-bindings.yml:336–342,377–380`; ONNX remains intentionally macOS-only at `verify_csharp.py:105–106`.

Unresolved dependencies and conflicting basenames fail before release at `package_csharp.py:204–278`; post-rewrite validation enforces deployment requirements, relative identities/rpaths and packaged dependency containment at `136–172`. Windows VC runtime imports explicitly use redistributable directories. Required wrapper failures reach error accounting and disposal at `CSharpBindingCoverage.cs:97–151`. Both publication jobs now require successful `build` and `sdk_unit` jobs at `csharp-bindings.yml:446–460`. No unresolved default-only path or numeric/geometric algorithm change was found.

### Cycle 2: Behaviour-change audit

Packaged resolver directories precede build/system locations at `VtkNativeLibrary.cs.in:72–111`; resolver installation and macOS warmup retain their initialization boundary. Coverage cleanup remains in `finally`, with constructor/name/disposal failures counted as errors. Native verification removes the matching original installation; C# verification hides/restores the original build and preserves unexpected recreated content. F-002 retains predicate ordering, normalized macOS comparison and optional expected-source behavior. No construction-time validator, lifecycle invariant or cached-property enforcement was demoted.

### Cycle 2: Findings

| # | Item | Review status | Finding IDs / evidence |
| --- | --- | --- | --- |
| 1 | New-feature completeness | ✅ | Both platforms, package types, consumer checks and publication prerequisites are wired; F-001 addressed. |
| 2 | Test-name vs implementation | ✅ | Alias, closure, collision, restoration, release and diagnostic assertions match their stated behavior. |
| 3 | Dead code / redundant guards / defensive coercion / silent-failure surfaces | ✅ | Dependency/identity failures propagate; required wrapper failures cannot become skips. |
| 4 | Docstring invariants | ✅ | Isolation, restoration and portability claims have corresponding guards. |
| 5 | Cross-platform | ✅ | Windows case folding/redist resolution, ZIP/tar aliases, macOS deployment and signing paths inspected. |
| 6 | Cross-call-site consistency | ✅ | Both publishers require the same prerequisite jobs; identity checks remain consistent. |
| 7 | Naming = behaviour | ✅ | Packaging, extraction, validation, coverage and publication names match their operations. |
| 8 | Error-message quality | ✅ | F-002 gates now identify the artifact/field and actual versus expected values. |
| 9 | Wire format / contract version | ✅ | New runtime manifest declares schema 1; no workspace result/version contract changes. |
| 10 | Documentation drift | ✅ | README publication, qualification, platform and archive boundaries match the snapshot. |
| 11 | Test coverage (100 %, FDA / IEC 62304) | ⚠️ | No actionable finding ID: tests and parent-recorded results inspected; measured 100% line/branch coverage remains unverified. Clinical Class C classification is N/A here. |
| 12 | FDA / regulatory traceability | ✅ | N/A to clinical changes: no threshold, measurement semantics, patient-data path or workspace result change. |

Existing lifecycle dispositions are retained from the ledger; this reviewer made no fixes.

| ID | Finding | Severity | Fix status | Location |
| --- | --- | --- | --- | --- |
| F-001 | C# release can publish while the packaging unit job fails | minor | fixed | `.github/workflows/csharp-bindings.yml:460` |
| F-002 | New identity/version failure diagnostics omit actual and expected values | minor | fixed | `.github/sdk/package_csharp.py:143` — original packet location |

F-001 is supported by both `needs: [build, sdk_unit]` declarations and the regression at `test_publication.py:16–29`, which checks prerequisites and preservation of the default success gate. F-002 is supported by the packaging, verifier and receipt diagnostics, their negative assertions, and positive normalization/optional-source cases. The original immutable packets remain in Cycle 1; no replacement packets or action items are required.

### Cycle 2: Sister-skill triggers

- **Available `devils-advocate` Codex prompt**: separately dispatched for publication execution claims; returned no new actionable finding. It confirmed F-001’s correction, receipt/source binding, relocation boundaries, unique release identities and absence of publisher repackaging.
- **`security-checker`**: subprocess, file I/O and deserialization triggers apply, but no matching SDK/umbrella prompt exists. No specialist security verdict is claimed. Scoped inspection covered argument arrays, archive containment, dependency resolution and digest checks.
- **Licensing specialist**: redistribution/license evidence warrants domain attention; no matching prompt exists. Collecting evidence does not establish legal sufficiency.
- **Regulatory specialist**: release/signing machinery was inspected as an operational boundary; no regulatory specialist prompt exists and no classification or compliance verdict is claimed.
- **Clinical-reference, clinical fact-check, HIPAA, translation, ITK/Slicer and device specialists**: N/A; no clinical claims, patient payloads, citations, localization or imaging-coordinate logic changed.
- **Docstring rendering hooks**: N/A; no new structured multiline API docstring requires the MeddyLib documentation toolchain.

Dynamic inventory found no SDK Codex prompt assets. The umbrella exposes `devils-advocate` and `pr-creator`; PR creation is outside this review. No unavailable specialist role was fabricated.

### Cycle 2: Skipped checks

- Jira context: no ticket key supplied or present in the branch scope.
- Tests, pre-commit, builds, installs and executable documentation examples: not run under the read-only reviewer contract.
- Measured 100% coverage and mutation effectiveness: need runtime verification; passing named tests do not establish exhaustive coverage.
- Windows/macOS qualification of this fixed snapshot: not established by the earlier CI run.
- Workspace schema/fixture matrices and `get_version()` bumps: N/A; no such models changed.
- Clinical qualification, FDA classification and controlled QMS promotion: outside this producer review.
- Live master publication, remote tag/asset readback, delivered archive-byte identity, notarization and Unity activation: not established by static review or mocked publication tests.

This reviewer changed no source, ledger, configuration, Git state or external state.

### Cycle 2: Successful disposition

Cycle 2 accepted: all actionable findings are fixed and independently cleared across the full original scope plus fixes. The commit and PR push remain pending; the existing platform CI receipts belong to the prior committed head. Proposed message: `fix: gate runtime releases and clarify validation diagnostics`.

- Ledger section headings are qualified by cycle to satisfy duplicate-heading validation; immutable finding packet contents and cycle reports remain semantically unchanged. No Markdown rule was disabled.
