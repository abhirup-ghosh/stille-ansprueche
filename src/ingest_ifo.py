"""Phase 1a: download and parse the ifo-institute/sozialleistungen YAML inventory.

Source: https://github.com/ifo-institute/sozialleistungen (CC-BY-SA-4.0).
Structure discovered by inspection: a single file `sozialleistungen.yml` with
<Gesetzbuch (law book)> -> <Kategorie (category)> -> list of entries with fields
`leistung`, `rechtsnorm`, `zielgruppen`, `themenfelder`.
"""
import hashlib
import io
import re
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import requests
import yaml
from pydantic import BaseModel

from src import config

REPO_URL = "https://github.com/ifo-institute/sozialleistungen"
BRANCHES = ["main", "master"]
IFO_DIR = config.DATA_DIR / "ifo"
REPO_DIR = IFO_DIR / "repo"
PARSED_PATH = IFO_DIR / "benefits_parsed.jsonl"
ATTRIBUTION_PATH = config.DATA_DIR / "ATTRIBUTION.md"

TRANSLIT = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
})


class BenefitRecord(BaseModel):
    id: str
    name: str
    description: str
    legal_norm: str
    law_book: str
    category: str
    target_groups: list[str]
    topic_fields: list[str]
    source: str = "ifo-institute/sozialleistungen"


def slugify(name: str) -> str:
    s = name.translate(TRANSLIT).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:40].strip("-") or "leistung"


def make_id(name: str, law_book: str, category: str, legal_norm: str) -> str:
    base = slugify(name)
    h = hashlib.sha1(f"{law_book}|{category}|{name}|{legal_norm}".encode("utf-8")).hexdigest()[:4]
    return f"{base}-{h}"


def extract_name(leistung_text: str) -> str:
    match = re.search(r"[.,]", leistung_text)
    if match:
        return leistung_text[: match.start()].strip()
    return leistung_text.strip()


def download_repo() -> Path:
    IFO_DIR.mkdir(parents=True, exist_ok=True)
    if REPO_DIR.exists() and any(REPO_DIR.rglob("*.yml")):
        print(f"[ingest_ifo] Repo already downloaded and extracted at {REPO_DIR}, skipping fetch.")
        return REPO_DIR

    last_err = None
    for branch in BRANCHES:
        url = f"{REPO_URL}/archive/refs/heads/{branch}.zip"
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                names = zf.namelist()
                if not names:
                    continue
                zf.extractall(IFO_DIR)
                extracted_root = IFO_DIR / names[0].split("/")[0]
                if REPO_DIR.exists():
                    import shutil
                    shutil.rmtree(REPO_DIR)
                extracted_root.rename(REPO_DIR)
            print(f"[ingest_ifo] Downloaded and extracted branch '{branch}' to {REPO_DIR}")
            return REPO_DIR
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(
        f"Could not download {REPO_URL} on branches {BRANCHES}. Last error: {last_err}. "
        "Fallback per PLAN.md: download the repo manually into data/ifo/repo/."
    )


def write_attribution(repo_dir: Path) -> None:
    license_path = None
    for candidate in ["LICENSE", "LICENSE.md", "LICENSE.txt"]:
        p = repo_dir / candidate
        if p.exists():
            license_path = p
            break
    license_excerpt = license_path.read_text(encoding="utf-8")[:500].strip() if license_path else "LICENSE file not found in repo."

    content = f"""# Data Attribution

## ifo Institute — Sozialleistungen inventory

- **Repository:** {REPO_URL}
- **License:** Creative Commons Attribution-ShareAlike 4.0 International (CC-BY-SA-4.0), per the
  repository's GitHub metadata and LICENSE file.
- **Access date:** {date.today().isoformat()}
- **Citation:** ifo Institut (2025), *Eine Inventur im Haus der sozialen Hilfe und Unterstützung*,
  https://www.ifo.de/publikationen/2025/monographie-autorenschaft/eine-inventur-im-haus-der-sozialen-hilfe-und
  Methodology article: https://www.ifo.de/publikationen/2025/aufsatz-zeitschrift/auf-der-suche-nach-passierschein-a38

LICENSE file excerpt:

```
{license_excerpt}
```

## Portal enrichment (Phase 1b)

See below (this section is appended by `src/enrich_portals.py`) for sozialplattform.de and
familienportal.de attribution, once enrichment has run.
"""
    ATTRIBUTION_PATH.write_text(content, encoding="utf-8")
    print(f"[ingest_ifo] Wrote attribution to {ATTRIBUTION_PATH}")


def parse_yaml(repo_dir: Path) -> list[BenefitRecord]:
    yaml_files = list(repo_dir.glob("*.yml")) + list(repo_dir.glob("*.yaml"))
    if not yaml_files:
        raise RuntimeError(f"No YAML files found in {repo_dir}")

    records: list[BenefitRecord] = []
    seen_ids: set[str] = set()
    for yf in yaml_files:
        with open(yf, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for law_book, categories in data.items():
            for category, entries in categories.items():
                for entry in entries:
                    leistung = (entry.get("leistung") or "").strip()
                    if not leistung:
                        continue
                    name = extract_name(leistung)
                    legal_norm = (entry.get("rechtsnorm") or "").strip()
                    target_groups = entry.get("zielgruppen") or []
                    topic_fields = entry.get("themenfelder") or []
                    rec_id = make_id(name, law_book, category, legal_norm)
                    while rec_id in seen_ids:
                        rec_id = f"{rec_id}x"
                    seen_ids.add(rec_id)
                    records.append(BenefitRecord(
                        id=rec_id,
                        name=name,
                        description=leistung,
                        legal_norm=legal_norm,
                        law_book=law_book,
                        category=category,
                        target_groups=target_groups,
                        topic_fields=topic_fields,
                    ))
    return records


def main():
    repo_dir = download_repo()
    write_attribution(repo_dir)
    records = parse_yaml(repo_dir)

    PARSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PARSED_PATH, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(rec.model_dump_json() + "\n")

    law_book_counts = Counter(r.law_book for r in records)
    primary_target_counts = Counter(r.target_groups[0] for r in records if r.target_groups)

    print(f"\n[ingest_ifo] Total parsed records: {len(records)}")
    print("[ingest_ifo] Counts per law book:")
    for lb, c in law_book_counts.most_common():
        print(f"  {lb}: {c}")
    print("[ingest_ifo] Counts per primary target group:")
    for tg, c in primary_target_counts.most_common():
        print(f"  {tg}: {c}")
    print(f"[ingest_ifo] Wrote {PARSED_PATH}")


if __name__ == "__main__":
    main()
