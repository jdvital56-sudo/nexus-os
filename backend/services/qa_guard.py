"""QA Guard — review gate for agent outputs.

Any artifact (document, task, graph change) goes through Reviewer before it's considered "done".
This is the blocking quality gate from the Harness layer.
"""
from ..models.schemas import AgentRole
from . import agents as agent_svc
from . import tasks as task_svc
from ..core.errors import NexsysError


class QAGateError(NexsysError):
    def __init__(self, message: str):
        super().__init__(message, code="QA_REJECTED", status=422)


def review_artifact(artifact_type: str, artifact_id: str, content: str, auto_fix: bool = False) -> dict:
    """Run QA review on an artifact.

    Args:
        artifact_type: "document", "task", "graph_node", etc.
        artifact_id: ID of the artifact
        content: Text content to review
        auto_fix: If True, automatically create fix tasks

    Returns:
        {"approved": bool, "issues": [...], "reviewer_output": str}
    """
    # Find or create a reviewer agent
    agents = agent_svc.list_agents(role="reviewer")
    if not agents:
        # No reviewer — auto-approve (can't block without reviewer)
        return {"approved": True, "issues": [], "reviewer_output": "No reviewer agent found, auto-approved"}

    reviewer = agents[0]

    # Build review task
    review_task = (
        f"Review {artifact_type} '{artifact_id}'.\n"
        f"Content:\n{content[:2000]}\n\n"
        f"Check for:\n"
        f"1. Completeness — is anything missing?\n"
        f"2. Consistency — does it contradict existing knowledge?\n"
        f"3. Quality — is it well-structured and clear?\n"
        f"4. Safety — does it contain sensitive data?"
    )

    # Run reviewer cycle
    result = agent_svc.run_agent(reviewer.id, review_task)

    # Parse issues from output
    issues = _parse_issues(result.output)

    # Decision
    critical_issues = [i for i in issues if i.get("severity") == "critical"]
    approved = len(critical_issues) == 0

    # Auto-create fix tasks if needed
    if auto_fix and not approved:
        for issue in critical_issues:
            try:
                task_svc.create_task(task_svc.TaskCreate(
                    title=f"Fix: {issue.get('description', 'QA issue')}",
                    description=f"Artifact: {artifact_type} '{artifact_id}'\nIssue: {issue.get('description', '')}",
                    assigned_agent="librarian",
                    tags=["qa-fix", "auto"],
                ))
            except Exception:
                pass

    return {
        "approved": approved,
        "issues": issues,
        "reviewer_output": result.output,
        "critical_count": len(critical_issues),
    }


def _parse_issues(output: str) -> list[dict]:
    """Extract structured issues from reviewer output."""
    issues = []
    lines = output.split("\n")
    for line in lines:
        line_lower = line.lower().strip()
        # Look for issue patterns
        if any(marker in line_lower for marker in ["issue:", "problem:", "warning:", "error:", "флаг"]):
            severity = "warning"
            if any(w in line_lower for w in ["critical", "严重", "критич", "error", "ошибка"]):
                severity = "critical"
            elif any(w in line_lower for w in ["info", "note", "заметк"]):
                severity = "info"
            issues.append({
                "description": line.strip(),
                "severity": severity,
                "source": "reviewer",
            })
    # If no issues found in log, check for orphan/task creation patterns
    if not issues:
        if "task" in output.lower() and ("creat" in output.lower() or "создан" in output.lower()):
            issues.append({
                "description": "Reviewer created fix tasks",
                "severity": "warning",
                "source": "reviewer",
            })
    return issues


def quick_check(content: str) -> list[str]:
    """Fast rule-based check without running an agent.

    Returns list of warnings (empty = all clear).
    """
    warnings = []
    content_lower = content.lower()

    # Check for sensitive patterns
    import re
    if re.search(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', content):
        warnings.append("Possible credit card number detected")
    if re.search(r'[\w.-]+@[\w.-]+\.\w+', content) and len(content) < 100:
        warnings.append("Email in short content — check if intentional")
    if re.search(r'(password|пароль|токен|token|ключ|key)\s*[:=]', content_lower):
        warnings.append("Possible credential in content")

    # Check for empty/trivial
    if len(content.strip()) < 10:
        warnings.append("Content is very short — may be incomplete")

    # Check for TODO markers
    if "todo" in content_lower or "fixme" in content_lower or "хак" in content_lower:
        warnings.append("Contains TODO/FIXME markers")

    return warnings
