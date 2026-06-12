from datetime import datetime

from app.domain.models import PageInfo, Transaction, TransactionPage
from app.repository.transactions_repo import TransactionsRepository, build_list_query
from app.services import pagination


class TransactionsService:
    def __init__(self, repo: TransactionsRepository | None = None) -> None:
        self.repo = repo or TransactionsRepository()

    async def list_transactions(
        self,
        *,
        cursor: str | None,
        limit: int,
        sort: str,
        status: list[str] | None,
        type_: str | None,
        min_amount: float | None,
        max_amount: float | None,
        currency: str | None,
        counterparty: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> TransactionPage:
        sort_field, direction = pagination.parse_sort(sort)
        query = build_list_query(
            status=status,
            type_=type_,
            min_amount=min_amount,
            max_amount=max_amount,
            currency=currency,
            counterparty=counterparty,
            date_from=date_from,
            date_to=date_to,
        )
        has_filters = bool(query)
        if cursor:
            value, doc_id = pagination.decode_cursor(cursor, sort_field)
            after = pagination.cursor_filter(sort_field, direction, value, doc_id)
            query = {"$and": [query, after]} if query else after

        docs = await self.repo.list_page(query, sort_field, direction, limit)
        has_next = len(docs) > limit
        docs = docs[:limit]

        next_cursor = None
        if has_next and docs:
            last = docs[-1]
            next_cursor = pagination.encode_cursor(sort_field, last[sort_field], last["_id"])

        return TransactionPage(
            items=[Transaction.model_validate(d) for d in docs],
            pageInfo=PageInfo(
                hasNextPage=has_next,
                nextCursor=next_cursor,
                totalEstimate=await self.repo.estimated_total(has_filters),
            ),
        )

    async def get_transaction(self, txn_id: str) -> Transaction | None:
        doc = await self.repo.find_by_id(txn_id)
        return Transaction.model_validate(doc) if doc else None

    async def get_audit(self, txn_id: str) -> list[dict] | None:
        if not await self.repo.find_by_id(txn_id):
            return None
        return await self.repo.audit_for(txn_id)
