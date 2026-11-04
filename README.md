# DeadBolt for Hermes

**Review a text artifact before an agent writes it.**

This standalone Hermes plugin provides two tools:

* `deadbolt_prepare_write` saves a private review request containing the exact
  destination and UTF-8 content. It does not create the destination or approve it.
* `deadbolt_commit_write` asks a separately running DeadBolt 2.0.1 sidecar for
  exact-action admission, then creates that new file. A denial does not run the
  write. The grant binds run, tool, workspace, path, content, nonce and deadline;
  it is consumed once.

Useful for a research report, generated configuration, or other text artifact
that an operator wants to inspect before creation. This first version deliberately
creates new files only; it cannot overwrite, patch or delete existing files.
Existing parent directories are required. Requests, including review metadata,
are limited to 32 KiB and expire after five minutes.

## Scope comes first

Only this plugin's `deadbolt_commit_write` effect is protected. Hermes terminal,
ordinary file tools, browser, delegation, other plugins and MCP connections are
outside this route. Do not claim whole-agent containment or protection against
an agent that can bypass the route. Keep Hermes's own approvals enabled.

The executor and operator are trusted. Protect the sidecar database, operator
token, CLI and configuration using separate OS/service ownership when running
untrusted code. A shared UID is not isolation. A plugin that is disabled or never
called does not enforce anything. This plugin does not use Hermes middleware,
whose documented failure behavior is fail-open.

Admission is not completion. If writing fails after admission, the tool returns
`admitted: true`, `completed: false`, `outcome: unknown`; inspect the destination
before any retry. Revocation does not cancel work already admitted. No exactly-once
filesystem transaction is claimed.

## Install

Requires Hermes **0.22.2 or later**, a supported POSIX host (macOS/Linux), and a
separately installed **DeadBolt 2.0.1** engine. Plugin **0.1.1** and engine **2.0.1**
are separate versions. The plugin is Python source using
only the standard library. It bundles no executable, downloads nothing at startup,
does not start the sidecar and does not modify Hermes core.

```sh
hermes plugins install seanebones-lang/deadbolt-hermes-plugin --no-enable
hermes plugins enable deadbolt
```

This is a direct repository install, **not a claim of Nous catalog approval**.
Inspect and pin a reviewed commit for your environment. The catalog submission,
if accepted, pins the reviewed source separately.

Install the engine from its [current installation guide](https://github.com/seanebones-lang/deadbolt/blob/main/docs/INSTALL.md)
and verify `deadbolt --version` reports **2.0.1** in the operator environment that
starts the sidecar. The plugin does not install or upgrade the engine for you.
Back up operator state before upgrading. Refresh an existing repository install
to a reviewed plugin commit and start a new Hermes session; copying source alone
does not establish which plugin the session loaded. See the pinned framework and
engine revisions in [the validation record](docs/VALIDATION.md).

## Operator setup — outside the agent

1. Select a fresh existing output directory and a unique run ID. Set up private
   `DEADBOLT_DB` and `DEADBOLT_EVENTS` paths and a private `DEADBOLT_TOKEN` in the
   **operator/sidecar process only**, following the [official authentication guide](https://github.com/seanebones-lang/deadbolt/blob/main/docs/HTTP-AUTHENTICATION.md).
   Never put the operator token into Hermes.
2. Provision a finite run, explicit policy and scoped admission credential:

   ```sh
   deadbolt ensure --agent hermes-report-001 --lease-ttl-secs 3600
   deadbolt policy --agent hermes-report-001 --tools hermes_artifact_write_v1
   deadbolt action require --agent hermes-report-001 --tool hermes_artifact_write_v1
   deadbolt credential issue --agent hermes-report-001 --id hermes-report-admission-001 \
     --ttl-secs 3600 --out /absolute/private/path/new-admission-credential
   deadbolt serve --bind 127.0.0.1:9782 --lease-ttl-secs 3600
   ```

   Use a private existing parent directory for the new credential file. Issuance
   never overwrites it or prints its secret. This finite setup expires after one
   hour; admissions do not renew it. For ongoing jobs use a separately trusted
   [supervisor](https://github.com/seanebones-lang/deadbolt/blob/main/docs/SUPERVISION.md).
   Reconnection must not automatically create a fresh run or revive a killed ID.
3. In Hermes Desktop → Plugins → DeadBolt settings, set `workspace` to the
   existing absolute output directory, `run_id` to `hermes-report-001`, and
   `sidecar_port` to `9782`. Supply the new scoped admission credential in the
   secret `admission_token` field. Hermes stores it through its own credential
   route as `DEADBOLT_HERMES_ADMISSION_TOKEN`. The plugin reads only that active
   profile's secret using `agent.secret_scope.get_secret`; it never reads credential
   files, `.env`, keychains, browser profiles or another account's login.

   CLI users can configure the nonsecret settings in their active profile:

   ```yaml
   plugins:
     enabled: [deadbolt]
     entries:
       deadbolt:
         settings:
           workspace: /absolute/path/to/reviewed-output
           run_id: hermes-report-001
           sidecar_port: 9782
   ```

   Preserve your other configuration. Configure the secret through Hermes's
   supported profile-secret workflow; do not put it in YAML or tool arguments.
4. Start a new Hermes session. Ask it to prepare a fictional artifact:
   “Use `deadbolt_prepare_write` to propose `review-example.txt` containing
   `A fictional reviewed report.` Do not execute or approve it.”
5. The result names a private review file under the active profile's
   `plugin-data/deadbolt/requests/`. In your **operator** terminal:

   ```sh
   deadbolt action inspect --file /the/exact/returned/review-file.json
   deadbolt action approve --file /the/exact/returned/review-file.json \
     --fingerprint sha256:THE_DIGEST_YOU_ACTUALLY_REVIEWED
   ```

   Inspect displays the complete arguments. Review them, including workspace,
   path and content. Never automatically approve arbitrary files or use an agent
   to grant its own authority. Then ask Hermes to call `deadbolt_commit_write`
   with the returned request ID. Changing the review content after approval is
   denied; the same approval cannot authorize a second write.

## Data and access disclosures

* Only outbound connection: bounded HTTP to literal `127.0.0.1` at the configured
  port, endpoint `/admit-action`, using a single-run admission credential.
  No redirects, remote service, telemetry or paid provider calls.
  Use this route only on a trusted private host with the sidecar's port controlled
  by the operator. Loopback restriction is not peer authentication or an OS
  isolation boundary.
* Reads/writes private pending requests containing raw proposed text in the active
  profile's plugin data. They persist after completion/expiry for operator review.
  Review and remove old request files using your normal private-file workflow;
  the plugin does not automatically erase them or empty Trash.
* Creates new mode-0600 UTF-8 files in the selected workspace, using directory
  descriptors and refusing symlink traversal and overwrite. No shell commands or
  background tasks run from the plugin.
* The operator separately runs the DeadBolt service. Its normal evidence storage
  contains decision metadata/fingerprints; review files contain the actual text.
  Fingerprints are not encryption. Protect the Hermes profile and backups too.
* macOS and Linux are the intended platforms. Windows is refused before execution
  because this version relies on POSIX directory-descriptor operations.

## Validation and reproducibility

See [the acceptance record](docs/VALIDATION.md). These are deterministic framework
and process checks, not a model conversation or an independent endorsement.

```sh
python3 -m unittest discover -s tests -v
hermes plugins validate /absolute/path/to/this/repo --install-deps
```

For real discovery and dispatch acceptance, run `tests/acceptance.py` inside an
isolated, officially prepared Hermes checkout at the pinned revision:

```sh
bash scripts/run-in-hermes-env python /absolute/path/to/this/repo/tests/acceptance.py \
  --hermes /absolute/path/to/hermes-checkout --binary /absolute/path/to/deadbolt
```

Run that last command from the Hermes checkout with a **disposable** `HERMES_HOME`
and `HERMES_RUNTIME_DIR`, following its development guide. The script creates a
second temporary profile, fictional artifacts, private synthetic credentials and
a local sidecar; it cleans up its own temporary state and processes. It never
uses your installed profile or model account.

Source is Apache-2.0. [DeadBolt engine](https://github.com/seanebones-lang/deadbolt)
is a separate Apache-2.0 project. Hermes is independently maintained by Nous
Research under MIT. This plugin is maintained by NextEleven and is not affiliated
with or endorsed by Nous Research.
