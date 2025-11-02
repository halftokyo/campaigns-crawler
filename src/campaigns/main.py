from __future__ import annotations

import argparse
from . import pipeline
from .notion_client import upsert_to_notion, archive_by_external_ids, ensure_database_schema
from .state import load_state, save_state, compute_weekly_changes


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="JP Campaigns Crawler")
    p.add_argument("--config", default="configs/sources.json", help="Path to sources.json")
    p.add_argument("--out", default="output/campaigns.json", help="Output JSON path")
    p.add_argument("--no-notion", action="store_true", help="Skip Notion upsert")
    p.add_argument(
        "--valid-within-days",
        type=int,
        default=None,
        help="Keep items whose deadline is within N days from today (inclusive)",
    )
    p.add_argument(
        "--require-deadline",
        action="store_true",
        help="Drop items without a parsable deadline",
    )
    p.add_argument(
        "--active-only",
        action="store_true",
        help="Keep only items whose deadline is in the future (ignore window)",
    )
    p.add_argument(
        "--weekly-new-and-archive",
        action="store_true",
        help="Weekly mode: upsert newly discovered in last 7 days and archive expired",
    )
    p.add_argument(
        "--state-file",
        default="output/state.json",
        help="Path to persistent state file for weekly/incremental operations",
    )
    p.add_argument(
        "--setup-notion-schema",
        action="store_true",
        help="Ensure Notion database has required properties (idempotent)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.setup_notion_schema:
        ensure_database_schema()
    if args.weekly_new_and_archive:
        # Weekly flow: get all active items (require deadline), then compute new/expired against state
        active = [
            c.to_dict()
            for c in pipeline.run(
                args.config,
                args.out,
                valid_within_days=None,
                require_deadline=True,
            )
        ]
        state = load_state(args.state_file)
        new_items, expired_ids, updated = compute_weekly_changes(state, active, window_days=7)

        # write helper outputs
        if new_items:
            with open("output/new_this_week.json", "w", encoding="utf-8") as f:
                import json
                json.dump(new_items, f, ensure_ascii=False, indent=2)
        if expired_ids:
            with open("output/expired_to_archive.json", "w", encoding="utf-8") as f:
                import json
                json.dump(expired_ids, f, ensure_ascii=False, indent=2)

        if not args.no_notion:
            if new_items:
                upsert_to_notion(new_items)
            if expired_ids:
                archive_by_external_ids(expired_ids)

        # Mark archived ones in state and save
        for eid in expired_ids:
            if eid in updated:
                updated[eid].archived = True
        save_state(updated, args.state_file)
    else:
        # Default flow: fetch + optional filters + upsert all
        valid_within_days = args.valid_within_days
        require_deadline = args.require_deadline
        if args.active_only:
            valid_within_days = None
            if not require_deadline:
                require_deadline = True

        items = [
            c.to_dict()
            for c in pipeline.run(
                args.config,
                args.out,
                valid_within_days=valid_within_days,
                require_deadline=require_deadline,
            )
        ]
        if not args.no_notion:
            upsert_to_notion(items)


if __name__ == "__main__":
    main()
