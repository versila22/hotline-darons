#!/usr/bin/env python3
import re
import subprocess
import sys

PATTERNS = [
    ("GitHub PAT classic", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("GitHub PAT fine-grained", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("GitHub OAuth/App token", re.compile(r"gho_[A-Za-z0-9]{36}")),
    ("GitHub refresh token", re.compile(r"ghr_[A-Za-z0-9]{36}")),
    ("GitHub app/user token", re.compile(r"ghu_[A-Za-z0-9]{36}")),
    ("GitLab PAT", re.compile(r"glpat-[A-Za-z0-9\-_]{20,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("OpenAI API key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("Stripe live secret", re.compile(r"sk_live_[0-9A-Za-z]{16,}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
]


def staged_files():
    out = subprocess.check_output([
        'git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'
    ], text=True)
    return [p for p in out.splitlines() if p.strip()]


def file_content_from_index(path: str) -> str:
    return subprocess.check_output(['git', 'show', f':{path}'], text=True, errors='ignore')


def main() -> int:
    hits = []
    for rel in staged_files():
        try:
            content = file_content_from_index(rel)
        except subprocess.CalledProcessError:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            for name, pattern in PATTERNS:
                m = pattern.search(line)
                if m:
                    hits.append((rel, i, name, m.group(0)[:120]))
    if hits:
        print('\n🚨 Secret-like values detected in staged changes. Commit blocked.\n', file=sys.stderr)
        for rel, line_no, name, sample in hits:
            print(f'- {rel}:{line_no}: {name}: {sample}', file=sys.stderr)
        sys.exit(1)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
