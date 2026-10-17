# Security boundary

The exact-action gate applies only to this plugin's own artifact writer. It is
not a sandbox or mandatory enforcement for all Hermes tools. The operator,
executor code, configuration and sidecar state must be trusted and protected
from untrusted execution. See README for data, credentials and outcome limits.

Please report suspected vulnerabilities privately through
https://github.com/seanebones-lang/deadbolt-hermes-plugin/security/advisories/new .
Include the pinned plugin/Hermes/engine versions and a fictional reproduction.
Never include real secrets or user content in public issues.
