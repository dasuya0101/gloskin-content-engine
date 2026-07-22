#!/usr/bin/env python3
"""Three-layer semantic compliance linter and one-pass rewrite helper."""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import yaml

from brand_loader import DEFAULT_BRAND, load_brand
from claim_packs import (
    approved_claims,
    caveats,
    disallowed_claims,
    regulatory_hold_is_active,
    regulatory_holds,
)
from llm_router import complete


ROOT = Path(__file__).resolve().parent
FALSE_PRECISION = {
    "author_year_citation": r"\b[A-Z][a-z]+ et al\.,? \d{4}\b",
    "sample_size": r"\bn\s*=\s*\d+\b",
    "dose": r"\b\d+\s?(?:mg|mcg|µg|μg|ug|iu)\b",
    "study_count": r"\b\d+\s+studies\b",
}
PATTERNABLE_CLAIMS = {
    "named_mechanism": (
        r"\b(?:receptors?|agonists?|antagonists?|signaling|pathways?|modulation of|"
        r"angiogenesis|growth factors?|IGF-?1|pituitary|satiety|gastric emptying|"
        r"mitochondri(?:a|al)|sirtuins?|electron transport|redox|ATP|NADH|NMN|"
        r"nicotinamide riboside|SNAC|semaglutide|tirzepatide|ipamorelin|"
        r"tesamorelin|GHRH|GHRPs?|feedback loops?|fibroblasts?|collagen|"
        r"inflammation|tissue repair|skin barrier|absorption|bioavailability|"
        r"degrad(?:es?|ation)|safety profile|extracellular matrix|gene expression|"
        r"dopamine|reward pathways?|stimulat(?:es?|ing).{0,40}(?:GH|growth hormone|"
        r"production)|(?:suppress|increase|raise|lower|reduce).{0,40}(?:GH|"
        r"growth hormone|inflammation|NAD\+|collagen|production))\b"
    ),
    "percentage_stat": r"(?:<\s*)?\b\d+(?:\.\d+)?\s?%",
    "trial_scale": (
        r"\b(?:large(?:[- ]scale)? (?:randomized )?(?:human )?trials?|randomi[sz]ed|"
        r"n\s*=\s*\d+|MACE|sample size|small cohort|large cohort|"
        r"small (?:human )?trials?|case studies|observational studies|"
        r"decades of.{0,30}research|hard endpoints?|biomarkers?|HbA1c|A1C|"
        r"C-reactive protein|CRP)\b"
    ),
    "regulatory_conclusion": (
        r"\b(?:is|isn't|is not|are|aren't|are not) legal\b|\bFDA guidance\b|"
        r"\bDEA\b|\bscheduled(?: substance)?\b|"
        r"\b(?:U\.S\.C\.|CFR)\s*\d+\b"
    ),
}
RESEARCH_OR_REGULATORY_CONTEXT = re.compile(
    r"\b(?:study|studies|trial|research|published|evidence|FDA|DEA|guidance|"
    r"law|legal|regulat(?:ion|ory)|scheduled|approval)\b", re.I)
ELIGIBILITY_503A = re.compile(
    r"(?:\b(?:eligible|eligibility|allowed|permitted|available|qualif(?:y|ies)|"
    r"can be compounded|may be compounded)\b.{0,100}\b503A\b|"
    r"\b503A\b.{0,100}\b(?:eligible|eligibility|allowed|permitted|available|"
    r"qualif(?:y|ies)|can compound|may compound)\b)",
    re.I,
)
STRONG_CONCLUSION = re.compile(
    r"\b(?:prove[ds]?|definitively|conclusively|confirmed efficacy|"
    r"establish(?:es|ed)? efficacy|demonstrat(?:es|ed) efficacy)\b",
    re.I,
)
SINGLE_LAB = re.compile(
    r"\b(?:one|single|same) (?:lab|laboratory|research group)|"
    r"\bfoundational (?:lab|laboratory|research group)\b",
    re.I,
)
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
    "present_tense_care_model": (
        r"\b(?:(?:VendraRx|we|our practice) "
        r"(?:works?|partners?|sources?|prescribes?|provides?|monitors?|orders?|reviews?|uses?)|"
        r"(?:every|each) (?:case|patient).{0,80}(?:routes?|goes|is reviewed|"
        r"gets reviewed)|(?:every|all) protocols?.{0,60}(?:start|begin).{0,40}"
        r"(?:clinician|physician)|our (?:clinicians?|physicians?) "
        r"(?:review|prescribe|monitor)|medications?.{0,50}"
        r"(?:come from|comes from|are sourced|are compounded))\b"
    ),
}


class ComplianceError(RuntimeError):
    pass


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def serialize_output(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def _excerpt(text, start, end):
    left = max(
        text.rfind("\n", 0, start),
        text.rfind(". ", 0, start),
        text.rfind("? ", 0, start),
        text.rfind("! ", 0, start),
    )
    left = 0 if left < 0 else left + (1 if text[left] == "\n" else 2)
    stops = [value for value in (
        text.find("\n", end), text.find(". ", end),
        text.find("? ", end), text.find("! ", end),
    ) if value >= 0]
    right = min(stops) + 1 if stops else len(text)
    return text[left:right].strip().strip('"')


def _matches(text, patterns, source, *, excerpt=False):
    rows = []
    for raw in patterns or []:
        for match in re.finditer(raw, text, flags=re.IGNORECASE):
            rows.append({
                "text": _excerpt(text, match.start(), match.end()) if excerpt else match.group(0),
                "match": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "rule": source,
                "pattern": raw,
            })
    return rows


def _year_candidates(text):
    rows = []
    for match in re.finditer(r"\b(?:19|20)\d{2}\b", text):
        excerpt = _excerpt(text, match.start(), match.end())
        if RESEARCH_OR_REGULATORY_CONTEXT.search(excerpt):
            rows.append({
                "text": excerpt,
                "match": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "rule": "research_or_regulatory_year",
                "pattern": r"\b(?:19|20)\d{2}\b",
            })
    return rows


def _disallowed_matches(text, brief):
    rows = []
    for item in disallowed_claims(brief):
        if isinstance(item, dict) and item.get("pattern"):
            pattern = str(item["pattern"])
        else:
            pattern = re.escape(str(item))
        rows.extend(_matches(text, [pattern], "disallowed_claim", excerpt=True))
    return rows


def _regulatory_hold_matches(text, brief):
    rows = []
    for pack, hold in regulatory_holds(brief):
        if not regulatory_hold_is_active(hold):
            continue
        claim_ref = str(hold.get("claim_ref") or "").strip()
        if claim_ref:
            matches = _matches(
                text, [re.escape(claim_ref)], "regulatory_hold", excerpt=True)
            for item in matches:
                item.update({
                    "claim_ref": claim_ref,
                    "compound": pack.get("compound"),
                    "review_after": str(hold.get("review_after") or ""),
                })
            rows.extend(matches)
        for match in ELIGIBILITY_503A.finditer(text):
            rows.append({
                "text": _excerpt(text, match.start(), match.end()),
                "match": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "rule": "regulatory_hold",
                "pattern": ELIGIBILITY_503A.pattern,
                "claim_ref": claim_ref,
                "compound": pack.get("compound"),
                "review_after": str(hold.get("review_after") or ""),
            })
    return rows


def _caveat_matches(text, brief):
    rows = []
    for caveat in caveats(brief):
        if not re.search(r"\b(?:one|single) (?:lab|research group)\b", caveat, re.I):
            continue
        for match in STRONG_CONCLUSION.finditer(text):
            excerpt = _excerpt(text, match.start(), match.end())
            if SINGLE_LAB.search(excerpt):
                rows.append({
                    "text": excerpt,
                    "match": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "rule": "claim_pack_caveat",
                    "pattern": STRONG_CONCLUSION.pattern,
                    "caveat": caveat,
                })
    return rows


def layer1(text, brand, brief=None):
    brief = brief or {}
    hard = _matches(text, brand.compliance.get("hard_block") or [], "hard_block")
    hard.extend(_disallowed_matches(text, brief))
    hard.extend(_regulatory_hold_matches(text, brief))
    hard.extend(_caveat_matches(text, brief))
    review = _matches(text, brand.compliance.get("review") or [], "review")
    for rule, pattern in FALSE_PRECISION.items():
        review.extend(_matches(text, [pattern], rule, excerpt=True))
    for rule, pattern in PATTERNABLE_CLAIMS.items():
        review.extend(_matches(text, [pattern], rule, excerpt=True))
    review.extend(_year_candidates(text))
    for rule, pattern in OPERATIONAL_REVIEW.items():
        review.extend(_matches(text, [pattern], rule, excerpt=True))
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
        "claim_packs": brief.get("claim_packs") or [],
        "caveats": caveats(brief),
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
            "Treat claim_packs as the complete ground-truth set for specific evidence, mechanism, and regulatory claims.",
            "A specific claim not represented by an exact approved claim is fabrication; never infer permission from the topic.",
            "A disallowed_claims item is always a block, including a semantic paraphrase.",
            "Treat every claim-pack caveat as a framing constraint; flag copy that contradicts one.",
            "Never clear regulatory_hold. Layer 1 owns those hard blocks.",
            "For pre_launch operations, flag bare present-tense care delivery; clear explicit design/building/when-launch framing. For live operations, clear present tense.",
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
        ("regulatory", "unapproved_regulatory_claim"),
        ("legal", "unapproved_regulatory_claim"),
        ("disallowed", "disallowed_claim"),
        ("caveat", "claim_pack_caveat"),
        ("hold", "regulatory_hold"),
    ]
    known = {
        "fabricated_research_act", "unsourced_mechanism", "fabricated_evidence",
        "disease_claim", "rx_outcome_promise", "unverifiable_operational_claim",
        "missing_affiliate_disclosure", "missing_ai_label",
        "unapproved_regulatory_claim", "disallowed_claim",
        "claim_pack_caveat", "regulatory_hold",
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


def _contains_exact_approved_claim(text, brief):
    lowered = str(text).casefold()
    return any(claim.casefold() in lowered for claim in approved_claims(brief))


def context_clear_violations(violations, brief, context=None, brand=None):
    context = context or {}
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
        elif (rule in {"unsourced_mechanism", "fabricated_evidence",
                       "unapproved_regulatory_claim"}
              and _contains_exact_approved_claim(quoted, brief)):
            clear = True
        elif (rule == "unverifiable_operational_claim"
              and (context.get("operational_status") == "live"
                   or _design_framed(quoted)
                   or not _present_operational_assertion(quoted)
                   or any(
                       quoted in str(item.get("text") or "")
                       or str(item.get("text") or "") in quoted
                       for item in ((brand.compliance if brand else {}).get(
                           "required_disclaimers") or [])))):
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
        "claim_packs": brief.get("claim_packs") or [],
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


def _design_framed(text):
    return bool(re.search(
        r"(?i)\b(?:we(?:['’]re| are) building|we are designing|our model|"
        r"when we launch|at launch|will (?:route|review|work|source|prescribe|"
        r"provide|monitor|order)|designed to|planned (?:model|flow|practice))\b",
        text,
    ))


def _present_operational_assertion(text):
    return (
        any(re.search(pattern, text, re.I) for pattern in OPERATIONAL_REVIEW.values())
        or bool(re.search(
            r"(?i)\b(?:is|are) (?:determined|reviewed|compounded|sourced|"
            r"prescribed|monitored|ordered|provided)\b",
            text,
        ))
    )


def operational_candidate_fallbacks(candidates, violations, operational_status):
    if operational_status == "live":
        return []
    covered = " ".join(str(item.get("text") or "").casefold() for item in violations)
    fallbacks = []
    for item in candidates:
        if item.get("rule") not in OPERATIONAL_REVIEW:
            continue
        quoted = str(item.get("text") or "")
        if quoted.casefold() not in covered and not _design_framed(quoted):
            fallbacks.append({
                "text": quoted,
                "rule": "unverifiable_operational_claim",
                "severity": "warn",
            })
    return fallbacks


def _approved_candidate(text, candidate, claims):
    for claim in claims:
        for match in re.finditer(re.escape(claim), text, re.I):
            if candidate["start"] >= match.start() and candidate["end"] <= match.end():
                return claim
    return None


def deterministic_claim_violations(text, candidates, brief):
    claim_rules = set(PATTERNABLE_CLAIMS) | set(FALSE_PRECISION) | {
        "research_or_regulatory_year",
    }
    approved = approved_claims(brief)
    violations = []
    cleared = []
    seen = set()
    for item in candidates:
        if item.get("rule") not in claim_rules:
            continue
        exact_claim = _approved_candidate(text, item, approved)
        if exact_claim:
            cleared.append(
                f"claim-pack-cleared Layer-1 candidate: {item['match']} in {exact_claim}"
            )
            continue
        layer1_rule = item.get("rule")
        canonical = (
            "unapproved_regulatory_claim" if layer1_rule == "regulatory_conclusion"
            else "unsourced_mechanism" if layer1_rule == "named_mechanism"
            else "fabricated_evidence"
        )
        key = (item.get("text"), canonical)
        if key in seen:
            continue
        seen.add(key)
        violations.append({
            "text": item.get("text") or item.get("match") or "",
            "rule": canonical,
            "severity": "block",
            "layer1_rule": layer1_rule,
        })
    return violations, cleared


def hard_violations(hard):
    violations = []
    seen = set()
    for item in hard:
        source_rule = item.get("rule")
        rule = source_rule if source_rule in {
            "disallowed_claim", "regulatory_hold", "claim_pack_caveat"
        } else "hard_block"
        key = (item.get("text"), rule)
        if key in seen:
            continue
        seen.add(key)
        violation = {
            "text": item.get("text") or "",
            "rule": rule,
            "severity": "block",
        }
        if rule == "regulatory_hold":
            violation.update({
                "claim_ref": item.get("claim_ref"),
                "compound": item.get("compound"),
                "review_after": item.get("review_after"),
            })
        elif rule == "claim_pack_caveat":
            violation["caveat"] = item.get("caveat")
        violations.append(violation)
    return violations


def lint_output(output, brand, brief=None, format_name=None, context=None):
    brief = brief or {}
    text = serialize_output(output)
    hard, candidates = layer1(text, brand, brief)
    if hard:
        violations = hard_violations(hard)
        return {
            "status": "fail", "violations": violations, "checked_at": now_iso(),
            "candidates": candidates, "notes": [], "suggested_rewrite": "",
        }
    deterministic, deterministic_notes = deterministic_claim_violations(
        text, candidates, brief)
    if deterministic:
        return {
            "status": "fail", "violations": deterministic,
            "checked_at": now_iso(), "candidates": candidates,
            "notes": deterministic_notes, "suggested_rewrite": "",
        }
    semantic_context = dict(context or {})
    semantic_context.setdefault(
        "operational_status",
        brief.get("operational_status") or brand.operational_status,
    )
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
    judged_violations, semantic_notes = context_clear_violations(
        grounded, brief, semantic_context, brand)
    violations = judged_violations + _missing_disclaimers(text, brand, format_name)
    violations.extend(operational_candidate_fallbacks(
        candidates, violations, semantic_context["operational_status"]))
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
    notes = deterministic_notes + grounding_notes + semantic_notes + [
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


def _rewrite_target(output, format_name):
    if format_name == "reddit_longform":
        lines = str(output).splitlines()
        body = "\n".join(lines[2:]) if len(lines) > 2 else str(output)
        count = len(re.findall(r"\b[\w'-]+\b", body))
        return {
            "body_words": max(320, min(750, count)),
            "valid_range": "300-800 body words",
        }
    if format_name == "x_thread":
        tweets = output.get("tweets") if isinstance(output, dict) else []
        return {"tweet_count": len(tweets), "max_chars_per_tweet": 275}
    return {
        "word_count": len(re.findall(r"\b[\w'-]+\b", str(output))),
        "required_sections": ["HOOK", "BEATS", "CTA", "SHOTLIST"],
    }


def rewrite_output(output, format_name, brand, brief, violations, target, error=None):
    requirements = {
        "reddit_longform": "First line title, blank line, then 300-800 body words.",
        "x_thread": 'Strict JSON only: {"tweets":["..."]}; every tweet <=275 chars.',
        "tiktok_script": "Markdown with HOOK, BEATS, CTA, SHOTLIST in that order.",
    }[format_name]
    request = {
        "task": "Rewrite the complete output, replacing each violation with compliant same-length substance.",
        "format": format_name,
        "format_requirements": requirements,
        "length_target": target,
        "violations": violations,
        "approved_mechanism_claims": brief.get("mechanism_claims") or [],
        "claim_packs": brief.get("claim_packs") or [],
        "caveats": caveats(brief),
        "operational_status": brief.get("operational_status") or brand.operational_status,
        "previous_validation_error": error or "",
        "original_output": output,
        "instructions": [
            "Return only the full replacement output in the requested format.",
            "Replace violating specifics with qualitative, useful content; do not merely delete sentences.",
            "Stay at the supplied length target and preserve all required structure.",
            "Use exact approved claims only; otherwise generalize or omit the specific assertion.",
            "Respect every claim-pack caveat as a framing constraint.",
            "Never include a claim covered by an active regulatory_hold.",
            "Do not invent citations, dates, percentages, trial details, mechanisms, or regulatory conclusions.",
        ],
    }
    copy_prompt = brand.prompt_path("copy_system")
    format_prompt = brand.format_prompt_path(format_name)
    system = "\n\n".join([
        copy_prompt.read_text(encoding="utf-8"),
        format_prompt.read_text(encoding="utf-8"),
        "You are rewriting a complete rendered draft after compliance review. Replace violations; do not summarize or shorten the draft.",
    ])
    return complete(
        system=system,
        user=json.dumps(request, ensure_ascii=False),
        task="compliance_lint",
        max_tokens=1900,
        temperature=0,
    )


def lint_file(path, format_name, brand, brief, tracking_code=None, context=None):
    """Lint a rendered output and retry one full, length-preserving rewrite."""
    import text_formats as tf

    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    output = json.loads(raw) if format_name == "x_thread" else raw
    first = lint_output(output, brand, brief, format_name, context)
    if first["status"] != "fail":
        first["rewrite_attempted"] = False
        return first
    target = _rewrite_target(output, format_name)
    rewritten = None
    error = None
    for attempt in range(1, 4):
        try:
            raw_rewrite = rewrite_output(
                output, format_name, brand, brief, first["violations"], target, error)
            rewritten = tf.normalize_format(
                format_name,
                raw_rewrite,
                brand=brand,
                tracking_code=tracking_code,
            )
            tf.write_format(path.parent, format_name, rewritten)
            break
        except Exception as exc:
            error = str(exc)
            if attempt < 3:
                print(
                    f"[{format_name}] compliance rewrite failed validation; "
                    f"regenerating ({attempt + 1}/3): {exc}",
                    file=sys.stderr,
                )
    if rewritten is None:
        first["status"] = "needs_review"
        first["rewrite_attempted"] = True
        first["violations"].append({
            "text": "", "rule": "rewrite_render_error", "severity": "warn",
            "detail": error or "rewrite failed",
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
            "claim_packs": case.get("claim_packs") or [],
            "operational_status": case.get("operational_status") or brand.operational_status,
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
