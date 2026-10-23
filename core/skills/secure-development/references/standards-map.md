# Security standards map

Use current stable standards as scoped evidence, not as a claim of compliance. Pin requirement identifiers and versions in reports so later revisions do not silently change meaning.

| Need | Stable baseline | Use |
|---|---|---|
| Common web risks | [OWASP Top 10 2025](https://owasp.org/www-project-top-ten/) | Awareness and prioritization only |
| Verifiable application controls | [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/) | Select applicable requirements and cite IDs as `v5.0.0-x.y.z` |
| API risks | [OWASP API Security Top 10 2023](https://owasp.org/www-project-api-security/) | Object/function authorization, resource limits, inventory, business flows, SSRF, and unsafe API consumption |
| Web security testing | [OWASP WSTG 4.2](https://owasp.org/www-project-web-security-testing-guide/) | Versioned test scenarios; WSTG 5 remains under development |
| Weakness prevalence | [CWE Top 25 2025](https://cwe.mitre.org/top25/archive/2025/2025_cwe_top25.html) | Prioritization signal, never a complete checklist |
| Identity assurance | [NIST SP 800-63-4](https://pages.nist.gov/800-63-4/) | Authentication, authenticators, federation, sessions, and recovery |
| Secure development lifecycle | [NIST SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final) | Stable SDLC practices; do not treat draft SSDF revisions as normative |
| Secure product defaults | [CISA Secure by Design](https://www.cisa.gov/securebydesign) | Ownership, transparency, secure defaults, and reduced customer burden |
| Program maturity | [OWASP SAMM v2](https://owaspsamm.org/model/) | Organizational improvement, not a per-change gate |
| Supply chain | [OpenSSF OSPS Baseline v2026.02.19](https://baseline.openssf.org/) and [SLSA 1.2](https://slsa.dev/spec/v1.2/) | Delegate implementation to `dependency-safety` |
| AI systems | [OWASP AISVS 1.0](https://github.com/OWASP/AISVS) and [OWASP GenAI Security](https://genai.owasp.org/) | Apply only to AI-enabled features; most production AI should target at least AISVS Level 2 |

## Selection rule

1. Start from the changed surface, assets, and trust boundaries.
2. Select only controls that can prevent or detect a plausible abuse case.
3. Record exact version and requirement/test IDs when used.
4. Never report “OWASP compliant”, “ASVS compliant”, or “secure” without an independently defined assessment scope and evidence.
