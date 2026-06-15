"""Audit or apply expired-document reconciliation from the command line."""

import argparse
import asyncio

from src.db.session import async_session_factory
from src.kb.lifecycle import (
    count_expiry_candidates,
    current_legal_date,
    reconcile_expired_documents,
)


async def run(*, apply: bool) -> None:
    async with async_session_factory() as session:
        as_of = current_legal_date()
        count = await count_expiry_candidates(session, as_of=as_of)
        print(f"Lifecycle candidates as of {as_of.isoformat()}: {count}")
        if not apply or count == 0:
            return
        changed = await reconcile_expired_documents(session, as_of=as_of, source="manual_job")
        await session.commit()
        print(f"Archived documents: {len(changed)}")
        for doc_id in changed:
            print(doc_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag the command is dry-run only.",
    )
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
