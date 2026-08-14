from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.regulatory_rule import IndexedRule


def retrieve_rules(
    db: Session,
    authority_code: str,
    *,
    category: str | None = None,
    rule_type: str | None = None,
    query: str | None = None,
    limit: int = 50,
) -> list[IndexedRule]:
    """Retrieve indexed regulatory rules using deterministic metadata filters."""

    if limit <= 0:
        return []

    statement = select(IndexedRule).where(
        IndexedRule.authority_code == authority_code
    )

    if category is not None:
        statement = statement.where(IndexedRule.category == category)

    if rule_type is not None:
        statement = statement.where(IndexedRule.rule_type == rule_type)

    if query:
        search_text = query.strip().lower()

        if search_text:
            statement = statement.where(
                (
                    IndexedRule.rule_id.ilike(f"%{search_text}%")
                    | IndexedRule.category.ilike(f"%{search_text}%")
                    | IndexedRule.rule_type.ilike(f"%{search_text}%")
                    | IndexedRule.description.ilike(f"%{search_text}%")
                )
            )

    statement = statement.order_by(
        IndexedRule.category,
        IndexedRule.rule_id,
    ).limit(limit)

    return list(db.execute(statement).scalars().all())