#!/usr/bin/env python3
"""Three-layer semantic compliance linter and one-pass rewrite helper."""
import argparse
import json
import re
import time
from pathlib import Path

import yaml

from brand_loader import DEFAULT_BRAND, load_brand
from llm_router import complete


ROOT = Path(__file__).resolve().parent
FALSE_PRECISION = {
    "author_year_citation": r"\b[A-Z][a-z]+ et al\.,? \d{4}\b",
    "sample_size": r"\bn\s*=\s*\d+\b",
    "dose": r"\b\d+\s?(?:mg|mcg|µg|μg|ug|iu)\b",
    "study_count": r"\b\d+\s+studies\b",
}
OPERATIONAL_REVIEW = {
    "shipping_or_storage": r"\b(?:cold[- ]chain|refrigerated shipping|temperature[- ]controlled)\b",
    "physician_availability": (
        r"\b(?:(?:physicians?|clinicians?) available (?:24/7|today|now)|"
        r"(?:every|each) (?:case|patient).{0,80}(?:reviewed|seen) by.{0,40}"
        r"(?:physician|clinician))\b"
    ),
    "specific_lab_practice": (
        r"\b(?:(?:every|all) (?:batch|lot) (?:is )?(?:lab[- ]tested|tested)|"
        r"we(?:['’]ll| will) (?:track|monitor|order|review).{0,40}(?:labs?|markers?))\b"
    ),
}


class ComplianceError(RuntimeError):
    pass


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def serialize_output(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def _matches(text, patterns, source):
    rows = []
    for raw in patterns or []:
        for match in re.finditer(raw, text, flags=re.IGNORECASE):
            rows.append({"text": match.group(0), "rule": source, "pattern": raw})
    return rows


def layer1(text, brand):
    hard = _matches(text, brand.compliance.get("hard_block") or [], "hard_block")
    review = _matches(text, brand.compliance.get("review") or [], "review")
    for rule, pattern in FALSE_PRECISION.items():
        review.extend(_matches(text, [pattern], rule))
    for rule, pattern in OPERATIONAL_REVIEW.items():
        review.extend(_matches(text, [pattern], rule))
    return hard, review


def _strip_fences(raw):
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _policy(brand):
    path = brand.prompt_path("compliance_policy")
    if not path or not path.exists():
        raise ComplianceError(f"{brand.brand_id} has no compliance policy prompt")
    return path.read_text(encoding="utf-8")


def llm_judgment(text, brand, brief, candidates, context=None):
    request = {
        "output_text": text,
        "factual_claims": brief.get("factual_claims") or [],
        "mechanism_claims": brief.get("mechanism_claims") or [],
        "layer1_candidates": candidates,
        "context": context or {},
        "required_schema": {
            "pass": "boolean",
            "violations": [{"text": "string", "rule": "string", "severity": "block|warn"}],
            "suggested_rewrite": "full corrected output string, or empty string",
        },
        "instructions": [
            "Judge semantic meaning, not merely regex forms.",
            "A first-person research act is fabricated even when unquantified.",
            "Fail named mechanisms absent from mechanism_claims.",
            "Clear candidates used only to reject hype or disclaim a claim.",
            "If rewriting, preserve the complete output structure and rewrite only violations.",
            "Use the policy's exact machine-readable rule IDs in every violation.",
        ],
    }
    raw = complete(
        system=_policy(brand),
        user=json.dumps(request, ensure_ascii=False),
        task="compliance_lint",
        max_tokens=1200,
        temperature=0,
    )
    try:
        data = json.loads(_strip_fences(raw))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ComplianceError(f"compliance response was not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("pass"), bool):
        raise ComplianceError("compliance response is missing boolean pass")
    violations = data.get("violations")
    if not isinstance(violations, list):
        raise ComplianceError("compliance response violations must be a list")
    clean = []
    for violation in violations:
        if not isinstance(violation, dict) or violation.get("severity") not in {"block", "warn"}:
            raise ComplianceError("compliance violation has an invalid schema")
        quoted = str(violation.get("text") or "")
        rule = canonical_rule(violation.get("rule"))
        if rule in {"review", "semantic_compliance"} and re.search(
                r"\b(?:cure|treat|prevent|heal)s?\b", quoted, re.I):
            rule = "disease_claim"
        severity = violation["severity"]
        if rule == "unverifiable_operational_claim":
            severity = "warn"
        clean.append({
            "text": quoted,
            "rule": rule,
            "severity": severity,
        })
    return {
        "pass": data["pass"],
        "violations": clean,
        "suggested_rewrite": str(data.get("suggested_rewrite") or ""),
    }


def canonical_rule(value):
    raw = str(value or "semantic_compliance")
    lowered = raw.lower()
    mappings = [
        ("affiliate", "missing_affiliate_disclosure"),
        ("avatar", "missing_ai_label"),
        ("illustrative", "missing_ai_label"),
        ("mechanism", "unsourced_mechanism"),
        ("pathway", "unsourced_mechanism"),
        ("receptor", "unsourced_mechanism"),
        ("research", "fabricated_research_act"),
        ("digging", "fabricated_research_act"),
        ("shipping", "unverifiable_operational_claim"),
        ("operational", "unverifiable_operational_claim"),
        ("disease", "disease_claim"),
        ("cure", "disease_claim"),
        ("heal", "disease_claim"),
        ("treat", "disease_claim"),
        ("prescription", "rx_outcome_promise"),
        ("guarante", "rx_outcome_promise"),
        ("citation", "fabricated_evidence"),
        ("sample", "fabricated_evidence"),
        ("dose", "fabricated_evidence"),
    ]
    known = {
        "fabricated_research_act", "unsourced_mechanism", "fabricated_evidence",
        "disease_claim", "rx_outcome_promise", "unverifiable_operational_claim",
        "missing_affiliate_disclosure", "missing_ai_label",
    }
    if raw in known:
        return raw
    for token, canonical in mappings:
        if token in lowered:
            return canonical
    return raw


def _missing_disclaimers(text, brand, format_name):
    if not format_name:
        return []
    violations = []
    for item in brand.compliance.get("required_disclaimers") or []:
        if format_name in (item.get("applies_to") or []) and item.get("text") not in text:
            violations.append({
                "text": item.get("text") or "",
                "rule": "missing_required_disclaimer",
                "severity": "warn",
            })
    return violations


def _research_act(text):
    return bool(re.search(
        r"(?i)(?:\bI\b|\bI['’]ve\b|\bwe\b|\bwe['’]ve\b|\bmy\b|\bour\b|^\s*been\b)"
        r".{0,80}\b(?:read|reading|study|studied|review|reviewed|research|digging)\b",
        text,
    ))


def _debunk_context(text):
    lead = (r"(?:hype|marketing|forums?|claims?|won['’]t|do not|don['’]t|not|"
            r"far cry from)")
    claim = r"(?:cure|heal|treat|prevent|miracle)"
    return bool(
        re.search(rf"(?i){lead}.{{0,120}}{claim}", text)
        or re.search(rf"(?i){claim}.{{0,120}}(?:hype|forums?|claims?)", text)
    )


def _consistent_with_mechanism_claims(text, claims):
    words = set(re.findall(r"[a-z]{4,}", text.lower()))
    stop = {"with", "from", "that", "this", "have", "been", "effects", "animal", "models"}
    for claim in claims or []:
        approved = set(re.findall(r"[a-z]{4,}", str(claim).lower())) - stop
        if len(words & approved) >= 2:
            return True
    return False


def context_clear_violations(violations, brief):
    kept = []
    notes = []
    for item in violations:
        quoted = str(item.get("text") or "")
        rule = item.get("rule")
        clear = False
        if rule == "fabricated_research_act" and not _research_act(quoted):
            clear = True
        elif rule == "disease_claim" and _debunk_context(quoted):
            clear = True
        elif (rule == "fabricated_evidence"
              and _consistent_with_mechanism_claims(
                  quoted, brief.get("mechanism_claims") or [])
              and not any(re.search(pattern, quoted, re.I)
                          for pattern in FALSE_PRECISION.values())):
            clear = True
        if clear:
            notes.append(f"context-cleared Layer-2 violation: {quoted}")
        else:
            kept.append(item)
    return kept, notes


def grounded_violations(violations, output_text, brief):
    haystack = " ".join(output_text.split()).casefold()
    source = " ".join(serialize_output({
        "factual_claims": brief.get("factual_claims") or [],
        "mechanism_claims": brief.get("mechanism_claims") or [],
    }).split()).casefold()
    kept = []
    notes = []
    unresolved = False
    for item in violations:
        quoted = " ".join(str(item.get("text") or "").split()).casefold()
        if quoted and quoted not in haystack:
            if quoted in source:
                notes.append(
                    f"discarded source-only Layer-2 violation: {item.get('text') or ''}")
            else:
                unresolved = True
                notes.append(
                    f"ungrounded Layer-2 violation requires review: {item.get('text') or ''}")
        else:
            kept.append(item)
    return kept, notes, unresolved


def operational_candidate_fallbacks(candidates, violations):
    covered = " ".join(str(item.get("text") or "").casefold() for item in violations)
    fallbacks = []
    for item in candidates:
        if item.get("rule") not in OPERATIONAL_REVIEW:
            continue
        quoted = str(item.get("text") or "")
        if quoted.casefold() not in covered:
            fallbacks.append({
                "text": quoted,
                "rule": "unverifiable_operational_claim",
                "severity": "warn",
            })
    return fallbacks


def lint_output(output, brand, brief=None, format_name=None, context=None):
    brief = brief or {}
    text = serialize_output(output)
    hard, candidates = layer1(text, brand)
    if hard:
        violations = [
            {"text": item["text"], "rule": "hard_block", "severity": "block"}
            for item in hard
        ]
        return {
            "status": "fail", "violations": violations, "checked_at": now_iso(),
            "candidates": candidates, "notes": [], "suggested_rewrite": "",
        }
    semantic_context = dict(context or {})
    semantic_context.update({
        "has_affiliate_link": bool(re.search(r"\b(?:amzn\.to|amazon\.[^\s/]+/[^\s]+)", text, re.I)),
        "has_affiliate_disclosure": bool(re.search(
            r"\b(?:affiliate|commission|paid link|ad:)\b", text, re.I)),
    })
    try:
        judged = llm_judgment(text, brand, brief, candidates, semantic_context)
    except Exception as exc:
        return {
            "status": "needs_review",
            "violations": [{
                "text": "", "rule": "llm_judgment_error", "severity": "warn",
                "detail": str(exc),
            }],
            "checked_at": now_iso(), "candidates": candidates, "notes": [],
            "suggested_rewrite": "",
        }
    grounded, grounding_notes, ungrounded = grounded_violations(
        judged["violations"], text, brief)
    judged_violations, semantic_notes = context_clear_violations(grounded, brief)
    violations = judged_violations + _missing_disclaimers(text, brand, format_name)
    violations.extend(operational_candidate_fallbacks(candidates, violations))
    if (brand.brand_id == "gloskin" and semantic_context.get("avatar_testimonial")
            and not re.search(r"\b(?:illustrative|AI[- ]generated)\b", text, re.I)):
        violations.append({
            "text": "", "rule": "missing_ai_label", "severity": "block",
        })
    blocks = any(item["severity"] == "block" for item in violations)
    warns = any(item["severity"] == "warn" for item in violations)
    cleared_model_verdict = bool(semantic_notes or (grounding_notes and not ungrounded))
    unresolved_model_fail = (
        ungrounded or (not judged["pass"] and not violations and not cleared_model_verdict))
    status = "fail" if blocks else "needs_review" if warns or unresolved_model_fail else "pass"
    violated_text = [str(item.get("text") or "").lower() for item in violations]
    notes = grounding_notes + semantic_notes + [
        f"context-cleared Layer-1 candidate: {item['text']}"
        for item in candidates
        if not any(item["text"].lower() in value or value in item["text"].lower()
                   for value in violated_text if value)
    ]
    return {
        "status": status,
        "violations": violations,
        "checked_at": now_iso(),
        "candidates": candidates,
        "notes": notes,
        "suggested_rewrite": judged["suggested_rewrite"],
    }


def lint_file(path, format_name, brand, brief, tracking_code=None, context=None):
    """Lint a rendered output and apply at most one model-supplied rewrite."""
    import text_formats as tf

    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    output = json.loads(raw) if format_name == "x_thread" else raw
    first = lint_output(output, brand, brief, format_name, context)
    if first["status"] != "fail" or not first.get("suggested_rewrite"):
        first["rewrite_attempted"] = False
        return first
    try:
        rewritten = tf.normalize_format(
            format_name,
            first["suggested_rewrite"],
            brand=brand,
            tracking_code=tracking_code,
        )
        tf.write_format(path.parent, format_name, rewritten)
    except Exception as exc:
        first["status"] = "needs_review"
        first["rewrite_attempted"] = True
        first["violations"].append({
            "text": "", "rule": "rewrite_render_error", "severity": "warn",
            "detail": str(exc),
        })
        return first
    second = lint_output(rewritten, brand, brief, format_name, context)
    second["rewrite_attempted"] = True
    second["initial_violations"] = first["violations"]
    if second["status"] != "pass":
        second["status"] = "needs_review"
    return second


def aggregate_results(results):
    statuses = [item.get("status") for item in results.values()]
    status = "fail" if "fail" in statuses else "needs_review" if "needs_review" in statuses else "pass"
    violations = []
    for output_name, result in results.items():
        for item in result.get("violations") or []:
            violations.append({**item, "output": output_name})
    return {
        "status": status,
        "violations": violations,
        "checked_at": now_iso(),
        "outputs": results,
    }


def selftest(path=ROOT / "tests" / "compliance_cases.yaml"):
    cases = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    failures = []
    for case in cases:
        brand = load_brand(case["brand"])
        brief = {
            "factual_claims": case.get("factual_claims") or [],
            "mechanism_claims": case.get("mechanism_claims") or [],
        }
        result = lint_output(
            case["text"], brand, brief, case.get("format"), case.get("context"))
        status_ok = result["status"] == case["expect"]
        rule = case.get("rule")
        rule_ok = not rule or any(v.get("rule") == rule for v in result["violations"])
        ok = status_ok and rule_ok
        print(f"[{'PASS' if ok else 'FAIL'}] {case['id']}: expected={case['expect']} actual={result['status']}")
        if not ok:
            failures.append({"case": case["id"], "result": result})
    if failures:
        raise ComplianceError(json.dumps(failures, indent=2))
    print(f"[ok] {len(cases)} compliance seed cases")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--cases", default=str(ROOT / "tests" / "compliance_cases.yaml"))
    parser.add_argument("--file")
    parser.add_argument("--brief")
    parser.add_argument("--brand", default=DEFAULT_BRAND)
    parser.add_argument("--format")
    args = parser.parse_args()
    if args.selftest:
        selftest(args.cases)
        return
    if not args.file:
        parser.error("pass --file or --selftest")
    output = Path(args.file).read_text(encoding="utf-8")
    brief = json.loads(Path(args.brief).read_text(encoding="utf-8")) if args.brief else {}
    print(json.dumps(lint_output(output, load_brand(args.brand), brief, args.format), indent=2))


if __name__ == "__main__":
    main()
