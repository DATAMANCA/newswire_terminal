import os

from .models import NewsItem, SourceResult


def write_step_summary(
    results: dict[str, SourceResult], new_items: list[NewsItem], is_first_run: bool, email_sent: bool
) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")

    lines = ["# Newswire Terminal run summary", ""]
    if is_first_run:
        lines.append("First run: seeded state, no email sent.")
    lines.append("")
    lines.append("| Source | Status | Items fetched |")
    lines.append("|---|---|---|")
    for source, result in results.items():
        status = "OK" if result.ok else f"FAILED: {result.error}"
        lines.append(f"| {source} | {status} | {len(result.items)} |")
    lines.append("")
    lines.append(f"New items this run: {len(new_items)}")
    lines.append(f"Email sent: {'yes' if email_sent else 'no'}")

    text = "\n".join(lines) + "\n"
    print(text)

    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(text)
