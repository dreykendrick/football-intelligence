"""
Sprint 6.3 Internal Developer CLI Commands (Section 69)
Provides CLI interfaces: shadow-predict, shadow-score-results, shadow-replay, shadow-monitor.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.prediction.domain import ShadowPredictionInput
from app.prediction.monitoring import ShadowMonitoringService
from app.prediction.replay import CleanRoomReplayService
from app.prediction.scoring import PostMatchScoringService
from app.prediction.service import ShadowPredictionService


def cmd_shadow_predict(args: argparse.Namespace) -> int:
    fixture_id = UUID(args.fixture_id) if args.fixture_id else uuid4()
    now = datetime.now(UTC)
    kickoff = now + timedelta(hours=args.lead_hours)

    inp = ShadowPredictionInput(
        fixture_id=fixture_id,
        competition_code=args.competition,
        season_year="2023-24",
        home_team_id=uuid4(),
        away_team_id=uuid4(),
        kickoff_utc=kickoff,
        prediction_time=now,
        feature_snapshot_id=uuid4(),
        feature_snapshot_fingerprint="fp_snap_02f8b524_demo",
        history_fingerprint="fp_hist_02f8b524_demo",
        feature_count=251,
        feature_values=[0.5] * 251,
        feature_keys=[f"f_{i}" for i in range(251)],
        snapshot_quality_state="VALID",
    )

    svc = ShadowPredictionService()
    res = svc.predict(inp, dry_run=args.dry_run)
    print(f"Shadow Prediction for Fixture {fixture_id}:")
    print(f"  Dry Run: {args.dry_run}")
    print(f"  Quality State: {res.quality_state}")
    if hasattr(res, "prob_home"):
        print(f"  1X2: H={res.prob_home:.3f}, D={res.prob_draw:.3f}, A={res.prob_away:.3f}")
        print(f"  Goals: lambda_home={res.lambda_home:.2f}, lambda_away={res.lambda_away:.2f}")
        print(f"  BTTS: Yes={res.btts_yes:.3f}, No={res.btts_no:.3f}")
        print(f"  O/U 2.5: Over={res.over_2_5:.3f}, Under={res.under_2_5:.3f}")
        print(f"  Fallback Used: {res.fallback_used}")
    return 0


def cmd_shadow_score(args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    fixture_id = UUID(args.fixture_id) if args.fixture_id else uuid4()
    inp = ShadowPredictionInput(
        fixture_id=fixture_id,
        competition_code="Premier League",
        season_year="2023-24",
        home_team_id=uuid4(),
        away_team_id=uuid4(),
        kickoff_utc=now + timedelta(hours=2),
        prediction_time=now,
        feature_snapshot_id=uuid4(),
        feature_snapshot_fingerprint="fp_snap_02f8b524",
        history_fingerprint="fp_hist_02f8b524",
        feature_count=251,
        feature_values=[0.5] * 251,
        feature_keys=[f"f_{i}" for i in range(251)],
    )

    svc = ShadowPredictionService()
    pred = svc.predict(inp, dry_run=False)

    scoring_svc = PostMatchScoringService()
    ev = scoring_svc.score_prediction(
        prediction=pred,
        actual_home_goals=args.home_goals,
        actual_away_goals=args.away_goals,
        match_status="FINISHED",
    )

    print(f"Evaluation for Prediction {pred.prediction_id}:")
    print(f"  Outcome: {ev.actual_1x2} ({ev.actual_home_goals}-{ev.actual_away_goals})")
    print(f"  1X2 Log Loss: {ev.log_loss_1x2:.4f}, Brier: {ev.brier_1x2:.4f}")
    print(f"  BTTS Log Loss: {ev.btts_log_loss:.4f}, Brier: {ev.btts_brier:.4f}")
    print(f"  OU2.5 Log Loss: {ev.ou25_log_loss:.4f}, Brier: {ev.ou25_brier:.4f}")
    print(f"  Top-1 Hit: {ev.top1_score_hit}, Top-3 Hit: {ev.top3_score_hit}")
    return 0


def cmd_shadow_replay(args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    fixture_id = UUID(args.fixture_id) if args.fixture_id else uuid4()
    inp = ShadowPredictionInput(
        fixture_id=fixture_id,
        competition_code="Premier League",
        season_year="2023-24",
        home_team_id=uuid4(),
        away_team_id=uuid4(),
        kickoff_utc=now + timedelta(hours=3),
        prediction_time=now,
        feature_snapshot_id=uuid4(),
        feature_snapshot_fingerprint="fp_snap_demo",
        history_fingerprint="fp_hist_demo",
        feature_count=251,
        feature_values=[0.4] * 251,
        feature_keys=[f"f_{i}" for i in range(251)],
    )

    svc = ShadowPredictionService()
    pred = svc.predict(inp, dry_run=False)

    matched, deltas = CleanRoomReplayService.replay_prediction(pred, inp)
    print(f"Clean-Room Replay Result: {'EXACT MATCH' if matched else 'MISMATCH'}")
    print(f"  Max Prob Delta: {deltas['max_prob_difference']:.8f}")
    print(f"  Max Lambda Delta: {deltas['max_lambda_difference']:.8f}")
    return 0 if matched else 1


def cmd_shadow_monitor(args: argparse.Namespace) -> int:
    mon = ShadowMonitoringService()
    now = datetime.now(UTC)
    dummy_preds = []
    svc = ShadowPredictionService()

    for i in range(20):
        inp = ShadowPredictionInput(
            fixture_id=uuid4(),
            competition_code="Premier League",
            season_year="2023-24",
            home_team_id=uuid4(),
            away_team_id=uuid4(),
            kickoff_utc=now + timedelta(hours=2 + i),
            prediction_time=now,
            feature_snapshot_id=uuid4(),
            feature_snapshot_fingerprint=f"fp_snap_{i}",
            history_fingerprint="fp_hist_batch",
            feature_count=251,
            feature_values=[0.1 * (i % 5)] * 251,
            feature_keys=[f"f_{k}" for k in range(251)],
        )
        p = svc.predict(inp, dry_run=False)
        dummy_preds.append(p)

    metrics = mon.evaluate_label_free_cohort(dummy_preds)
    print("Label-Free Monitoring Metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print(f"Active Alerts: {len(mon.alerts)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Football Intelligence Shadow Pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_predict = sub.add_parser("shadow-predict")
    p_predict.add_argument("--fixture-id", type=str, default=None)
    p_predict.add_argument("--competition", type=str, default="Premier League")
    p_predict.add_argument("--lead-hours", type=float, default=6.0)
    p_predict.add_argument("--dry-run", action="store_true")
    p_predict.set_defaults(func=cmd_shadow_predict)

    p_score = sub.add_parser("shadow-score-results")
    p_score.add_argument("--fixture-id", type=str, default=None)
    p_score.add_argument("--home-goals", type=int, default=2)
    p_score.add_argument("--away-goals", type=int, default=1)
    p_score.set_defaults(func=cmd_shadow_score)

    p_replay = sub.add_parser("shadow-replay")
    p_replay.add_argument("--fixture-id", type=str, default=None)
    p_replay.set_defaults(func=cmd_shadow_replay)

    p_mon = sub.add_parser("shadow-monitor")
    p_mon.set_defaults(func=cmd_shadow_monitor)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
