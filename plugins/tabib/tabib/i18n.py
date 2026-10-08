"""tabib's words in English and Arabic (TABIB_LANG, else "lang" in ~/.claude/nexika/tabib/config.json,
else Arabic for an Arabic locale, else English)."""
from __future__ import annotations

import json
import os

TEXT = {
    "en": {
        "title": "CI run {run} ({workflow}) on {branch}, commit {sha}",
        "k_code_tests": "{count} failing test(s)", "k_code_lint": "{count} lint error(s)",
        "k_code_build": "{count} build error(s)", "k_code_check": "{count} failed check(s)",
        "k_code_merge": "the branch does not merge into its base: rebase",
        "k_code_generated": "{count} generated file(s) out of date",
        "k_code_": "{count} failure(s)", "one_job": "{label}, in one job",
        "k_matrix": "fails only on {value}", "k_flaky": "likely flaky: the same commit passed",
        "k_infra": "outside the code: {signal}", "k_dependency": "a dependency problem",
        "k_dependency_module": "a dependency problem: {module} is not installed",
        "k_setup": "the CI setup is broken",
        "k_dependency_package": "a dependency problem: raised inside {package}",
        "next_package": "The error is raised inside {package}, not in the code this change touched: check "
                        "what changed in {package} (a new release, or the version this job installs), "
                        "then adapt the code to it or pin the version.",
        "k_unknown": "unclear: read the log",
        "n_jobs": "{label}, in {jobs} jobs",
        "s_timeout": "a time limit", "s_oom": "out of memory", "s_network": "the network",
        "s_rate_limit": "a rate limit", "s_runner": "the CI machine", "s_auth": "missing credentials",
        "s_cancelled": "the run was cancelled (a newer run or a person stopped it)",
        "confidence": "confidence: {level}",
        "flaky_test": "flaky: {test} passed in {passed} and failed in {failed} other run(s) of this commit",
        "h_failed": "What failed", "h_kind": "Kind", "h_evidence": "Evidence", "h_since": "Since the last green run",
        "h_repro": "Reproduced locally", "h_cause": "Cause (reported by Claude)", "h_next": "Next",
        "since": "{count} commit(s) since run {run}", "suspect": "suspect", "deps": "dependency files changed: {files}",
        "no_green": "no earlier green run to compare with",
        "r_reproduced": "yes: {why} ({command})", "r_not_reproduced": "no: {why} ({command})",
        "r_skipped": "not run: {why}", "r_error": "could not run: {why}", "r_none": "not tried yet (/tabib:diagnose)",
        "next_fix": "Fix it with /itqan:ship, starting from the failing test above.",
        "next_hook": "Run the hook(s) locally and commit what they change: {commands}",
        "next_format": "Run the formatter and commit what it changes: {commands}",
        "next_regenerate": "Regenerate {files} and commit the result: {command}",
        "next_rebase": "The branch does not merge into {base}: rebase it on {base} and resolve the conflicts "
                       "in {files}.",
        "next_check": "Do what the check's message above asks: it comes from the workflow, not from a test.",
        "next_unknown": "tabib could not tell from the log; read it: {url}",
        "next_setup": "Nothing to change in the code, and a re-run fails the same way: fix the workflow "
                      "(the line above says what it could not do).",
        "next_rerun": "Re-run only the failed jobs if you want (tabib never does it): {command}",
        "next_infra": "Nothing to change in the code; check the CI setup, then re-run if you want: {command}",
        "injection": "Note: the log contains text that tries to give instructions ({labels}); it was treated as data.",
        "none": "No diagnosis for this branch yet.",
    },
    "ar": {
        "title": "تشغيل CI رقم {run} ({workflow}) على {branch}، التعديل {sha}",
        "k_code_tests": "{count} اختبار فاشل", "k_code_lint": "{count} خطأ تنسيق",
        "k_code_build": "{count} خطأ بناء", "k_code_check": "{count} فحص فاشل",
        "k_code_merge": "الفرع لا يندمج في الفرع الأساسي: أعد بناءه (rebase)",
        "k_code_generated": "{count} ملف مولَّد غير محدَّث",
        "k_code_": "{count} إخفاق", "one_job": "{label}، في مهمة واحدة",
        "k_matrix": "يفشل فقط على {value}", "k_flaky": "متقلّب على الأرجح: نفس التعديل نجح",
        "k_infra": "خارج الكود: {signal}", "k_dependency": "مشكلة في الاعتماديات",
        "k_dependency_module": "مشكلة في الاعتماديات: {module} غير مثبّت",
        "k_setup": "إعداد CI معطّل",
        "k_dependency_package": "مشكلة في الاعتماديات: الخطأ من داخل {package}",
        "next_package": "الخطأ يُرفع من داخل {package} لا من الكود الذي غيّره هذا التعديل: راجع ما تغيّر في "
                        "{package} (إصدار جديد أو النسخة التي تثبّتها هذه المهمة)، ثم كيّف الكود معه أو ثبّت النسخة.",
        "k_unknown": "غير واضح: اقرأ السجل",
        "n_jobs": "{label}، في {jobs} مهام",
        "s_timeout": "حد زمني", "s_oom": "نفاد الذاكرة", "s_network": "الشبكة",
        "s_rate_limit": "حد عدد الطلبات", "s_runner": "جهاز CI", "s_auth": "بيانات اعتماد ناقصة",
        "s_cancelled": "أُلغي التشغيل (أوقفه تشغيل أحدث أو شخص)",
        "confidence": "الثقة: {level}",
        "flaky_test": "متقلّب: {test} نجح في {passed} وفشل في {failed} تشغيل آخر لهذا التعديل",
        "h_failed": "ما الذي فشل", "h_kind": "النوع", "h_evidence": "الدليل", "h_since": "منذ آخر تشغيل ناجح",
        "h_repro": "إعادة الإنتاج محليًا", "h_cause": "السبب (كما أبلغ Claude)", "h_next": "الخطوة التالية",
        "since": "{count} تعديل منذ التشغيل {run}", "suspect": "مشتبه به",
        "deps": "تغيّرت ملفات الاعتماديات: {files}",
        "no_green": "لا تشغيل ناجح سابق للمقارنة",
        "r_reproduced": "نعم: {why} ({command})", "r_not_reproduced": "لا: {why} ({command})",
        "r_skipped": "لم يُشغَّل: {why}", "r_error": "تعذّر التشغيل: {why}",
        "r_none": "لم تُجرَّب بعد (‎/tabib:diagnose)",
        "next_fix": "أصلحه عبر ‎/itqan:ship بدءًا من الاختبار الفاشل أعلاه.",
        "next_hook": "شغّل الأداة محليًا ثم احفظ ما غيّرته في تعديل: {commands}",
        "next_format": "شغّل أداة التنسيق ثم احفظ ما غيّرته في تعديل: {commands}",
        "next_regenerate": "أعد توليد {files} ثم احفظ النتيجة في تعديل: {command}",
        "next_rebase": "الفرع لا يندمج في {base}: أعد بناءه على {base} (rebase) "
                       "وحلّ التعارض في {files}.",
        "next_check": "نفّذ ما تطلبه رسالة الفحص أعلاه: مصدرها ملف سير العمل لا اختبار.",
        "next_unknown": "لم يستطع tabib الحكم من السجل؛ اقرأه: {url}",
        "next_setup": "لا شيء يتغيّر في الكود، وإعادة التشغيل تفشل بالطريقة نفسها: أصلح ملف سير العمل "
                      "(السطر أعلاه يقول ما تعذّر عليه).",
        "next_rerun": "أعد تشغيل المهام الفاشلة فقط إن شئت (tabib لا يفعل ذلك أبدًا): {command}",
        "next_infra": "لا شيء يتغيّر في الكود؛ راجع إعداد CI ثم أعد التشغيل إن شئت: {command}",
        "injection": "تنبيه: في السجل نص يحاول إعطاء أوامر ({labels})؛ عومل كبيانات فقط.",
        "none": "لا تشخيص لهذا الفرع بعد.",
    },
}


def lang() -> str:
    chosen = os.environ.get("TABIB_LANG") or ""
    if not chosen:
        home = os.path.expanduser(os.environ.get("TABIB_HOME") or "~/.claude/nexika/tabib")
        try:
            with open(os.path.join(home, "config.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            chosen = str(data.get("lang") or "") if isinstance(data, dict) else ""
        except (OSError, ValueError):
            chosen = ""
    chosen = chosen.lower()
    if chosen in TEXT:
        return chosen
    locale = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    return "ar" if locale.lower().startswith("ar") else "en"


def t(key: str, language: str = "", **values) -> str:
    table = TEXT.get(language or lang(), TEXT["en"])
    template = table.get(key) or TEXT["en"].get(key, key)
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


def label(kind: str, detail: dict, language: str = "") -> str:
    """A failure kind in a few words: '3 failing test(s)', 'fails only on py3.10', 'likely flaky ...'."""
    detail = detail or {}
    if kind == "code":
        text = t(f"k_code_{detail.get('what', '')}", language, count=detail.get("count", 0))
        if detail.get("jobs", 0) > 1:
            return t("n_jobs", language, label=text, jobs=detail["jobs"])
        return t("one_job", language, label=text) if detail.get("jobs") == 1 else text
    if kind == "infra":
        return t("k_infra", language, signal=t(f"s_{detail.get('signal', 'runner')}", language))
    if kind == "dependency" and detail.get("package"):
        return t("k_dependency_package", language, package=detail["package"])
    if kind == "dependency" and detail.get("module"):
        return t("k_dependency_module", language, module=detail["module"])
    if kind == "matrix":
        return t("k_matrix", language, value=detail.get("value", "?"))
    return t(f"k_{kind}", language)
