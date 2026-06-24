"""Action-oriented admin APIs for AI quality operations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.quality_schemas import (
    ProductionQualitySummary,
    QualityActionQueue,
    QualityBlockers,
    QualityDataStatus,
    QualityIssueDetail,
    QualityIssueItem,
    QualityIssueListResponse,
    QualityIssueReviewRequest,
    QualityObservationDetail,
    QualityOverviewResponse,
    QualityVerdict,
    ReleaseCaseItem,
    ReleaseCheckDetail,
    ReleaseCheckListResponse,
    ReleaseCheckSummary,
    ReleaseMetric,
    TraceCoverage,
)
from src.auth.dependencies import require_admin
from src.core.config import settings
from src.db.session import get_session
from src.models.quality import (
    QualityIssue,
    QualityObservation,
    QualityReleaseCase,
    QualityReleaseCheck,
)
from src.models.user import User

router = APIRouter(
    prefix="/admin/quality",
    tags=["admin-quality"],
    dependencies=[Depends(require_admin)],
)

_OPEN_STATUSES = ("open", "reviewing")
_ABSTENTION_REASONS = (
    "low_confidence_retrieval",
    "missing_citation",
    "no_supported_citation",
    "faithfulness_below_floor",
    "hallucination_detected",
)

_NEXT_ACTIONS = {
    "active_filter_violation": "Khóa release và kiểm tra active filter trước retrieval.",
    "disclaimer_missing": "Sửa output guardrail và thêm regression case.",
    "unsupported_claim": "Đối chiếu claim, citation và context trước khi phát hành.",
    "citation_verification": "Phân loại verifier error, retrieval miss hoặc KB gap.",
    "low_confidence": "Xác định KB gap hay retrieval miss rồi thêm regression case.",
    "chat_error": "Kiểm tra pipeline stage lỗi và theo dõi sau khi sửa.",
    "user_report": "Reviewer đối chiếu feedback với bằng chứng pháp lý.",
}


def _release_summary(check: QualityReleaseCheck) -> ReleaseCheckSummary:
    metrics = check.metrics or {}
    return ReleaseCheckSummary(
        run_id=check.run_id,
        status=check.status,
        dataset_version=check.dataset_version,
        executed=check.executed_cases,
        required=check.total_cases,
        valid=check.valid_cases,
        skipped=check.skipped_cases,
        invalid=check.invalid_cases,
        evaluator_errors=check.evaluator_errors,
        execution_coverage=(
            check.executed_cases / check.total_cases if check.total_cases else 0.0
        ),
        faithfulness=ReleaseMetric(
            value=metrics.get("faithfulness"),
            threshold=0.92,
            sample_size=metrics.get("faithfulness_sample_size"),
            eligible_count=metrics.get("faithfulness_eligible_cases"),
            minimum=metrics.get("faithfulness_min"),
            p10=metrics.get("faithfulness_p10"),
        ),
        citation_accuracy=ReleaseMetric(
            value=metrics.get("citation_accuracy"),
            threshold=0.98,
            numerator=metrics.get("citation_correct_cases"),
            denominator=metrics.get("citation_eligible_cases"),
        ),
        gate_failures=check.gate_failures or [],
        generated_at=check.generated_at,
    )


def build_quality_verdict(
    *,
    critical_issues: int,
    review_issues: int,
    release_status: str | None,
    data_status: str,
) -> QualityVerdict:
    if critical_issues > 0 or release_status == "failed":
        reason = (
            f"Có {critical_issues} vấn đề nghiêm trọng chưa xử lý."
            if critical_issues
            else "Release check gần nhất không đạt quality gate."
        )
        return QualityVerdict(
            status="blocked",
            title="Chưa đủ điều kiện phát hành",
            reason=reason,
            next_action="Mở danh sách vấn đề chặn phát hành.",
        )
    if release_status in {None, "invalid"} or data_status != "complete":
        return QualityVerdict(
            status="unknown",
            title="Chưa đủ dữ liệu để kết luận",
            reason="Release check hoặc coverage production chưa hợp lệ.",
            next_action="Hoàn tất eval và bổ sung observation còn thiếu.",
        )
    if review_issues > 0:
        return QualityVerdict(
            status="needs_attention",
            title="Chatbot đang phục vụ nhưng cần review",
            reason=f"Có {review_issues} vấn đề đang chờ phân loại.",
            next_action="Review các vấn đề có ảnh hưởng lớn nhất.",
        )
    return QualityVerdict(
        status="healthy",
        title="Chất lượng đang đạt ngưỡng",
        reason="Release check đạt và chưa có vấn đề mở.",
        next_action="Tiếp tục theo dõi production coverage.",
    )


def _issue_item(issue: QualityIssue) -> QualityIssueItem:
    return QualityIssueItem(
        issue_id=issue.issue_id,
        trace_id=issue.trace_id,
        issue_type=issue.issue_type,
        severity=issue.severity,
        status=issue.status,
        title=issue.title,
        summary=issue.summary,
        machine_reason=issue.machine_reason,
        affected_count=issue.affected_count,
        first_seen_at=issue.created_at,
        last_seen_at=issue.updated_at,
        next_action=_NEXT_ACTIONS.get(issue.issue_type, "Mở bằng chứng và phân loại vấn đề."),
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )


@router.get("/overview", response_model=QualityOverviewResponse)
async def get_quality_overview(
    period_days: int = Query(7, ge=1, le=90),
    db_session: AsyncSession = Depends(get_session),
):
    now = datetime.now(UTC)
    since = now - timedelta(days=period_days)

    observation_row = (
        await db_session.execute(
            select(
                func.count(QualityObservation.trace_id),
                func.count(QualityObservation.trace_id).filter(
                    QualityObservation.status != "started"
                ),
                func.count(QualityObservation.trace_id).filter(
                    QualityObservation.faithfulness_score.is_not(None)
                ),
                func.avg(QualityObservation.faithfulness_score),
                func.count(QualityObservation.trace_id).filter(
                    QualityObservation.guardrail_reason.in_(_ABSTENTION_REASONS)
                ),
                func.count(QualityObservation.trace_id).filter(
                    QualityObservation.status == "failed"
                ),
                func.percentile_cont(0.95).within_group(QualityObservation.latency_ms),
            ).where(QualityObservation.created_at >= since)
        )
    ).one()
    total, completed, evaluated, avg_faithfulness, abstained, failed, p95_latency = (
        observation_row
    )
    total = int(total or 0)
    completed = int(completed or 0)
    coverage_rate = completed / total if total else 0.0

    issue_counts = (
        await db_session.execute(
            select(
                func.count(QualityIssue.issue_id).filter(QualityIssue.severity == "critical"),
                func.count(QualityIssue.issue_id).filter(QualityIssue.severity != "critical"),
                func.min(QualityIssue.created_at),
                func.count(QualityIssue.issue_id).filter(
                    QualityIssue.issue_type == "active_filter_violation"
                ),
                func.count(QualityIssue.issue_id).filter(
                    QualityIssue.issue_type == "disclaimer_missing"
                ),
                func.count(QualityIssue.issue_id).filter(
                    QualityIssue.issue_type == "unsupported_claim"
                ),
            ).where(QualityIssue.status.in_(_OPEN_STATUSES))
        )
    ).one()
    critical, review, oldest, active_violations, disclaimer_missing, unsupported = issue_counts
    critical = int(critical or 0)
    review = int(review or 0)

    latest_release = (
        await db_session.execute(
            select(QualityReleaseCheck).order_by(desc(QualityReleaseCheck.generated_at)).limit(1)
        )
    ).scalar_one_or_none()

    blind_spots: list[str] = []
    if total < settings.QUALITY_MIN_PRODUCTION_SAMPLE:
        blind_spots.append(
            f"Mới có {total}/{settings.QUALITY_MIN_PRODUCTION_SAMPLE} request tối thiểu."
        )
    if total and completed < total:
        blind_spots.append(f"{total - completed} request chưa có observation hoàn chỉnh.")
    data_status = (
        "empty"
        if total == 0
        else "complete"
        if total >= settings.QUALITY_MIN_PRODUCTION_SAMPLE and coverage_rate >= 0.95
        else "partial"
    )
    verdict = build_quality_verdict(
        critical_issues=critical,
        review_issues=review,
        release_status=latest_release.status if latest_release else None,
        data_status=data_status,
    )

    return QualityOverviewResponse(
        verdict=verdict,
        as_of=now,
        period_days=period_days,
        data_quality=QualityDataStatus(
            status=data_status,
            production_trace_coverage=TraceCoverage(
                traced=completed,
                total=total,
                rate=coverage_rate,
            ),
            blind_spots=blind_spots,
        ),
        blockers=QualityBlockers(
            open=critical,
            active_filter_violations=int(active_violations or 0),
            disclaimer_missing=int(disclaimer_missing or 0),
            high_risk_unsupported_claims=int(unsupported or 0),
        ),
        latest_release_check=_release_summary(latest_release) if latest_release else None,
        action_queue=QualityActionQueue(
            critical=critical,
            needs_review=review,
            oldest_opened_at=oldest,
        ),
        production=ProductionQualitySummary(
            total_requests=total,
            completed_requests=completed,
            evaluated_responses=int(evaluated or 0),
            average_faithfulness=float(avg_faithfulness) if avg_faithfulness is not None else None,
            abstained_responses=int(abstained or 0),
            failed_requests=int(failed or 0),
            p95_latency_ms=int(p95_latency) if p95_latency is not None else None,
        ),
    )


@router.get("/issues", response_model=QualityIssueListResponse)
async def list_quality_issues(
    severity: Literal["critical", "high", "medium", "low"] | None = Query(None),
    issue_type: Literal[
        "active_filter_violation",
        "disclaimer_missing",
        "unsupported_claim",
        "citation_verification",
        "low_confidence",
        "chat_error",
        "user_report",
    ]
    | None = Query(None),
    issue_status: Literal["open", "reviewing", "resolved", "dismissed"] | None = Query(
        None, alias="status"
    ),
    source: Literal["production"] | None = Query(None),
    from_date: datetime | None = Query(None, alias="from"),
    to_date: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db_session: AsyncSession = Depends(get_session),
):
    filters = []
    if severity:
        filters.append(QualityIssue.severity == severity)
    if issue_type:
        filters.append(QualityIssue.issue_type == issue_type)
    if issue_status:
        filters.append(QualityIssue.status == issue_status)
    if from_date:
        filters.append(QualityIssue.created_at >= from_date)
    if to_date:
        filters.append(QualityIssue.created_at <= to_date)

    total = int(
        (await db_session.scalar(select(func.count(QualityIssue.issue_id)).where(*filters))) or 0
    )
    severity_order = case(
        (QualityIssue.severity == "critical", 0),
        (QualityIssue.severity == "high", 1),
        (QualityIssue.severity == "medium", 2),
        else_=3,
    )
    result = await db_session.execute(
        select(QualityIssue)
        .where(*filters)
        .order_by(desc(QualityIssue.affected_count), severity_order, desc(QualityIssue.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return QualityIssueListResponse(
        items=[_issue_item(issue) for issue in result.scalars().all()],
        total=total,
        page=page,
        page_size=page_size,
    )


async def _get_issue_detail(db_session: AsyncSession, issue_id: str) -> QualityIssueDetail:
    issue = await db_session.get(QualityIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quality issue not found")
    observation = await db_session.get(QualityObservation, issue.trace_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quality observation is missing",
        )
    return QualityIssueDetail(
        **_issue_item(issue).model_dump(),
        evidence=issue.evidence or {},
        reviewer_conclusion=issue.reviewer_conclusion,
        root_cause=issue.root_cause,
        reviewer_note=issue.reviewer_note,
        reviewed_by=issue.reviewed_by,
        reviewed_at=issue.reviewed_at,
        observation=QualityObservationDetail(
            trace_id=observation.trace_id,
            session_id=observation.session_id,
            environment=observation.environment,
            status=observation.status,
            query_text=observation.query_text,
            response_text=observation.response_text,
            citations=observation.citations or [],
            evidence=observation.evidence or [],
            pipeline_metadata=observation.pipeline_metadata or {},
            faithfulness_score=observation.faithfulness_score,
            is_out_of_scope=observation.is_out_of_scope,
            low_confidence=observation.low_confidence,
            has_hallucination=observation.has_hallucination,
            active_filter_violation=observation.active_filter_violation,
            disclaimer_missing=observation.disclaimer_missing,
            guardrail_stage=observation.guardrail_stage,
            guardrail_reason=observation.guardrail_reason,
            first_token_latency_ms=observation.first_token_latency_ms,
            latency_ms=observation.latency_ms,
            error_summary=observation.error_summary,
            created_at=observation.created_at,
            completed_at=observation.completed_at,
        ),
    )


@router.get("/issues/{issue_id}", response_model=QualityIssueDetail)
async def get_quality_issue(
    issue_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    return await _get_issue_detail(db_session, issue_id)


@router.post("/issues/{issue_id}/review", response_model=QualityIssueDetail)
async def review_quality_issue(
    issue_id: str,
    payload: QualityIssueReviewRequest,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    issue = await db_session.get(QualityIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quality issue not found")
    issue.status = payload.status
    issue.reviewer_conclusion = payload.conclusion
    issue.root_cause = payload.root_cause
    issue.reviewer_note = payload.note
    issue.reviewed_by = current_user.user_id
    issue.reviewed_at = datetime.now(UTC)
    await db_session.commit()
    return await _get_issue_detail(db_session, issue_id)


@router.get("/release-checks", response_model=ReleaseCheckListResponse)
async def list_release_checks(
    check_status: Literal["passed", "failed", "invalid"] | None = Query(
        None, alias="status"
    ),
    dataset_version: str | None = Query(None, min_length=1, max_length=80),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db_session: AsyncSession = Depends(get_session),
):
    filters = [QualityReleaseCheck.status == check_status] if check_status else []
    if dataset_version:
        filters.append(QualityReleaseCheck.dataset_version == dataset_version)
    total = int(
        (await db_session.scalar(select(func.count(QualityReleaseCheck.run_id)).where(*filters)))
        or 0
    )
    result = await db_session.execute(
        select(QualityReleaseCheck)
        .where(*filters)
        .order_by(desc(QualityReleaseCheck.generated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ReleaseCheckListResponse(
        items=[_release_summary(check) for check in result.scalars().all()],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/release-checks/{run_id}", response_model=ReleaseCheckDetail)
async def get_release_check(
    run_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    check = await db_session.get(QualityReleaseCheck, run_id)
    if check is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release check not found")
    result = await db_session.execute(
        select(QualityReleaseCase)
        .where(QualityReleaseCase.run_id == run_id)
        .order_by(QualityReleaseCase.case_id)
    )
    cases = result.scalars().all()
    return ReleaseCheckDetail(
        **_release_summary(check).model_dump(),
        config=check.config or {},
        metrics=check.metrics or {},
        cases=[
            ReleaseCaseItem(
                case_id=item.case_id,
                category=item.category,
                status=item.status,
                faithfulness_score=item.faithfulness_score,
                answer_relevancy=item.answer_relevancy,
                details=item.details or {},
            )
            for item in cases
        ],
    )


__all__ = ["build_quality_verdict", "router"]
