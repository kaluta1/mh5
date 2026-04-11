from sqlalchemy import or_
from sqlalchemy.orm import Session
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Optional, List, Tuple, Any, Dict
from datetime import datetime

from app.accounting.distribution_formulas import club_markup_split, kyc_verification_recognition_split
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.affiliate import AffiliateCommission
from app.models.accounting import ChartOfAccounts, JournalEntry, JournalLine
from app.services.accounting_service import accounting_service

logger = logging.getLogger(__name__)

_CENT = Decimal("0.01")


def _money_dec(x: Decimal) -> Decimal:
    return x.quantize(_CENT, rounding=ROUND_HALF_UP)


def _journal_entry_date(deposit: Deposit, entry_date: Optional[datetime]) -> datetime:
    if entry_date is not None:
        return entry_date
    return deposit.validated_at or deposit.created_at or datetime.utcnow()


def get_latest_validated_kyc_deposit(db: Session, user_id: int) -> Optional[Deposit]:
    kyc_pt = db.query(ProductType).filter(ProductType.code == "kyc").first()
    if not kyc_pt:
        return None
    return (
        db.query(Deposit)
        .filter(
            Deposit.user_id == user_id,
            Deposit.product_type_id == kyc_pt.id,
            Deposit.status == DepositStatus.VALIDATED,
        )
        .order_by(Deposit.id.desc())
        .first()
    )


def _journal_entry_line_totals(
    db: Session, je_id: int
) -> List[Tuple[Any, float, float]]:
    return (
        db.query(ChartOfAccounts.account_code, JournalLine.debit_amount, JournalLine.credit_amount)
        .join(JournalLine, JournalLine.account_id == ChartOfAccounts.id)
        .filter(JournalLine.entry_id == je_id)
        .all()
    )


def kyc_deferred_receipt_posted(db: Session, deposit_id: int) -> bool:
    """
    Step 1: USDT (BSC) inflow to deferred 2113. Matches standard description or legacy rows (Dr 1001 / Cr 2113, no 2113 Dr / no 4001 Cr).
    """
    dep_prefix = f"%KYC Payment - Deposit #{deposit_id}%"
    if (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(dep_prefix),
            or_(
                JournalEntry.description.like("%(Deferred cash receipt)%"),
                JournalEntry.description.like("%(Deferred receipt - USDT BSC)%"),
            ),
        )
        .first()
        is not None
    ):
        return True

    if (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(f"%KYC Payment - Deposit #{deposit_id}%"),
            JournalEntry.description.ilike("%deferred%"),
            ~JournalEntry.description.ilike("%verification performed%"),
        )
        .first()
        is not None
    ):
        return True

    needle = f"Deposit #{deposit_id}"
    je_ids = [
        r[0]
        for r in db.query(JournalEntry.id)
        .filter(JournalEntry.description.like(f"%{needle}%"))
        .all()
    ]
    for je_id in je_ids:
        rows = _journal_entry_line_totals(db, je_id)
        has_1001_dr = any(str(c) == "1001" and float(dr or 0) > 0 for c, dr, _cr in rows)
        has_2113_cr = any(str(c) == "2113" and float(cr or 0) > 0 for c, _dr, cr in rows)
        has_2113_dr = any(str(c) == "2113" and float(dr or 0) > 0 for c, dr, _cr in rows)
        has_4001_cr = any(str(c) == "4001" and float(cr or 0) > 0 for c, _dr, cr in rows)
        if has_1001_dr and has_2113_cr and not has_2113_dr and not has_4001_cr:
            return True
    return False


def kyc_recognition_posted(db: Session, deposit_id: int) -> bool:
    """True if Step 2 posted: standard description or legacy entry with Dr 2113 + Cr 4001 for this deposit."""
    if (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(f"%KYC Payment - Deposit #{deposit_id}%(Verification performed)%")
        )
        .first()
        is not None
    ):
        return True
    needle_dep = f"Deposit #{deposit_id}"
    je_ids = [
        r[0]
        for r in db.query(JournalEntry.id)
        .filter(JournalEntry.description.like(f"%{needle_dep}%"))
        .all()
    ]
    for je_id in je_ids:
        rows = _journal_entry_line_totals(db, je_id)
        has_2113_dr = any(str(c) == "2113" and float(dr or 0) > 0 for c, dr, _cr in rows)
        has_4001_cr = any(str(c) == "4001" and float(cr or 0) > 0 for c, _dr, cr in rows)
        if has_2113_dr and has_4001_cr:
            return True
    return False


def _legacy_instant_kyc_amount_and_revenue(
    db: Session, deposit: Deposit) -> Tuple[Optional[float], Optional[str]]:
    """
    Detect legacy 'instant' KYC posting: Dr 1001 / Cr revenue (4001 or 4002) with no 2113 movement,
    for a journal that references this deposit. Returns (cash_amount, revenue_account_code) or (None, None).
    """
    needle = f"Deposit #{deposit.id}"
    target = float(deposit.amount)
    je_ids = [
        r[0]
        for r in db.query(JournalEntry.id)
        .filter(JournalEntry.description.like(f"%{needle}%"))
        .all()
    ]
    for je_id in je_ids:
        rows = _journal_entry_line_totals(db, je_id)
        sums: Dict[str, Dict[str, float]] = {}
        for c, d, cr in rows:
            code = str(c)
            sums.setdefault(code, {"d": 0.0, "c": 0.0})
            sums[code]["d"] += float(d or 0)
            sums[code]["c"] += float(cr or 0)
        d1 = float(sums.get("1001", {}).get("d", 0.0))
        c2113 = float(sums.get("2113", {}).get("c", 0.0))
        d2113 = float(sums.get("2113", {}).get("d", 0.0))
        c4001 = float(sums.get("4001", {}).get("c", 0.0))
        c4002 = float(sums.get("4002", {}).get("c", 0.0))
        if c2113 > 0.01 or d2113 > 0.01:
            continue
        if d1 < 0.01:
            continue
        rev_cr = c4001 + c4002
        if rev_cr < 0.01:
            continue
        if abs(d1 - rev_cr) > 0.03:
            continue
        if abs(d1 - target) > 0.08 and abs(rev_cr - target) > 0.08:
            continue
        rev_code = "4001" if c4001 >= c4002 else "4002"
        return (d1, rev_code)
    return (None, None)


def kyc_legacy_instant_cash_to_revenue_detected(db: Session, deposit: Deposit) -> bool:
    amt, _ = _legacy_instant_kyc_amount_and_revenue(db, deposit)
    return amt is not None


def kyc_reclass_correction_posted(db: Session, deposit_id: int) -> bool:
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(f"%Deposit #{deposit_id}%"),
            JournalEntry.description.ilike("%legacy instant revenue correction%"),
        )
        .first()
        is not None
    )


def post_kyc_legacy_instant_to_deferred(db: Session, deposit: Deposit) -> None:
    """
    Dr revenue / Cr 2113 for the legacy instant-recognition amount so Step 2 can run (Dr 2113 / Cr 4001 / …).
    Idempotent if correction journal already exists.
    """
    dep_id = deposit.id
    if kyc_reclass_correction_posted(db, dep_id):
        logger.info("KYC legacy reclass already posted for deposit %s", dep_id)
        return
    amt, rev_code = _legacy_instant_kyc_amount_and_revenue(db, deposit)
    if amt is None or rev_code is None:
        raise ValueError(
            f"No legacy instant KYC revenue-without-deferred pattern found for deposit {dep_id}"
        )
    uid = deposit.user_id
    description = (
        f"KYC Payment - Deposit #{dep_id} - User #{uid} "
        f"(Deferred setup — legacy instant revenue correction)"
    )
    jdate = _journal_entry_date(deposit, None)
    accounting_service.create_journal_entry(
        db,
        description=description,
        lines=[
            {
                "account_code": rev_code,
                "debit": float(amt),
                "credit": 0.0,
                "description": "Reclass verification revenue to deferred 2113",
            },
            {
                "account_code": "2113",
                "debit": 0.0,
                "credit": float(amt),
                "description": "Deferred revenue — verification (unearned until performed)",
            },
        ],
        date=jdate,
    )
    logger.info(
        "Posted KYC legacy instant-to-deferred correction for deposit %s amount=%s via %s",
        dep_id,
        amt,
        rev_code,
    )


def _annual_membership_legacy_income_posted(db: Session, deposit_id: int) -> bool:
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(f"%Membership Payment - Deposit #{deposit_id}%(Income)%")
        )
        .first()
        is not None
    )


def _annual_membership_deferred_posted(db: Session, deposit_id: int) -> bool:
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(f"%Membership Payment - Deposit #{deposit_id}%"),
            JournalEntry.description.like("%(Deferred receipt - annual membership)%"),
        )
        .first()
        is not None
    )


def _annual_membership_recognition_posted(db: Session, deposit_id: int) -> bool:
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(f"%Membership Payment - Deposit #{deposit_id}%"),
            JournalEntry.description.like("%(Recognition - annual membership)%"),
        )
        .first()
        is not None
    )


def _annual_membership_commissions_posted(db: Session, deposit_id: int) -> bool:
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(f"%Membership Payment - Deposit #{deposit_id}%(Commissions)%")
        )
        .first()
        is not None
    )


def _founding_membership_legacy_income_posted(db: Session, deposit_id: int) -> bool:
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(
                f"%Founding Membership Payment - Deposit #{deposit_id}%(Income)%"
            )
        )
        .first()
        is not None
    )


def _founding_membership_deferred_posted(db: Session, deposit_id: int) -> bool:
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(f"%Founding Membership Payment - Deposit #{deposit_id}%"),
            JournalEntry.description.like("%(Deferred receipt - founding membership)%"),
        )
        .first()
        is not None
    )


def _founding_membership_recognition_posted(db: Session, deposit_id: int) -> bool:
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(f"%Founding Membership Payment - Deposit #{deposit_id}%"),
            JournalEntry.description.like("%(Recognition - founding membership)%"),
        )
        .first()
        is not None
    )


def _founding_membership_commissions_posted(db: Session, deposit_id: int) -> bool:
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.description.like(
                f"%Founding Membership Payment - Deposit #{deposit_id}%(Commissions)%"
            )
        )
        .first()
        is not None
    )


class PaymentAccountingService:
    """
    Payment-specific journals using generic accounting_service (CoA codes in init_coa.py).

    **Founding Members 10% pool (2104)** accrues on gross for every product we account for here:
    KYC (on verification recognition), annual membership, founding/MFM membership, and club markup.

    KYC verification fee:
    - USDT (BSC) receipt: Dr 1001 / Cr 2113 (deferred until service performed).
    - When Shufti/KYC completes: Dr 2113 / Cr 4001 (net), Cr 2104 (10% founding pool), Cr 2003 (Shufti);
 plus Dr 5001 / Cr 2001–2002 for sponsor commissions.

    Annual / founding membership (aligned with deferred revenue policy):
    - Dr 1001 / Cr 2110 or 2111 (receipt), then Dr deferred / Cr 4002 (net), Cr 2104 (10%), optional Cr 2003 (Shufti);
      commissions in a separate Dr 5001 / Cr 2001–2002 entry.
    """

    def process_kyc_cash_receipt_accounting(
        self,
        db: Session,
        deposit: Deposit,
        entry_date: Optional[datetime] = None,
        *,
        journal_commit: bool = True,
    ) -> None:
        """Step 1: validated payment in — unearned until verification completes."""
        dep_id = deposit.id
        if kyc_deferred_receipt_posted(db, dep_id):
            logger.info("KYC deferred receipt already posted for deposit %s", dep_id)
            return
        amount = Decimal(str(deposit.amount))
        description = f"KYC Payment - Deposit #{dep_id} - User #{deposit.user_id}"
        jdate = _journal_entry_date(deposit, entry_date)
        lines = [
            {
                "account_code": "1001",
                "debit": float(amount),
                "credit": 0.0,
                "description": (
                    f"USDT (BSC) on-chain inflow — KYC verification fee from member; "
                    f"Deposit #{dep_id} User #{deposit.user_id}"
                ),
            },
            {
                "account_code": "2113",
                "debit": 0.0,
                "credit": float(amount),
                "description": "Deferred revenue — verification (unearned until KYC performed)",
            },
        ]
        accounting_service.create_journal_entry(
            db,
            description=description + " (Deferred receipt - USDT BSC)",
            lines=lines,
            date=jdate,
            commit=journal_commit,
        )
        logger.info("KYC deferred USDT (BSC) receipt posted for deposit %s", dep_id)

    def process_kyc_verification_performed_accounting(
        self,
        db: Session,
        deposit: Deposit,
        commissions: List[AffiliateCommission],
        entry_date: Optional[datetime] = None,
        *,
        journal_commit: bool = True,
    ) -> None:
        """Step 2: release deferred revenue when verification service is performed (e.g. Shufti accepted)."""
        dep_id = deposit.id
        if kyc_recognition_posted(db, dep_id):
            logger.info("KYC verification recognition already posted for deposit %s", dep_id)
            return

        amount = Decimal(str(deposit.amount))
        total_comm = sum(Decimal(str(c.commission_amount)) for c in commissions)
        split = kyc_verification_recognition_split(amount, total_comm)
        # 4001 = gross − founding pool − Shufti; sponsor commissions hit 5001 / payables in a separate JE.
        verification_fee_revenue = amount - split.founding_pool_accrual - split.shufti_payable

        description = f"KYC Payment - Deposit #{dep_id} - User #{deposit.user_id}"
        jdate = _journal_entry_date(deposit, entry_date)

        recognition_lines = [
            {
                "account_code": "2113",
                "debit": float(split.gross),
                "credit": 0.0,
                "description": "Release deferred revenue — verification service performed",
            },
            {
                "account_code": "4001",
                "debit": 0.0,
                "credit": float(verification_fee_revenue),
                "description": (
                    "Verification fee revenue after founding pool and Shufti "
                    "(sponsor commissions — separate commission expense entry)"
                ),
            },
            {
                "account_code": "2104",
                "debit": 0.0,
                "credit": float(split.founding_pool_accrual),
                "description": "Accrued liability — Founding Members pool (10% of gross)",
            },
            {
                "account_code": "2003",
                "debit": 0.0,
                "credit": float(split.shufti_payable),
                "description": "Accounts payable — Shufti (KYC provider fee)",
            },
        ]
        accounting_service.create_journal_entry(
            db,
            description=description + " (Verification performed)",
            lines=recognition_lines,
            date=jdate,
            commit=journal_commit,
        )

        if commissions:
            commission_lines: List[dict] = []
            total_comm_expense = Decimal("0.0")
            for comm in commissions:
                comm_amount = Decimal(str(comm.commission_amount))
                total_comm_expense += comm_amount
                payable_account = "2001" if comm.level == 1 else "2002"
                commission_lines.append(
                    {
                        "account_code": payable_account,
                        "debit": 0.0,
                        "credit": float(comm_amount),
                        "description": f"Commission Level {comm.level} to User #{comm.user_id}",
                    }
                )
            commission_lines.insert(
                0,
                {
                    "account_code": "5001",
                    "debit": float(total_comm_expense),
                    "credit": 0.0,
                    "description": "Referral commission expense — verification fee",
                },
            )
            accounting_service.create_journal_entry(
                db,
                description=description + " (Commissions)",
                lines=commission_lines,
                date=jdate,
                commit=journal_commit,
            )

        logger.info("KYC verification performed accounting posted for deposit %s", dep_id)

    def post_kyc_verification_recognition_for_user(
        self,
        db: Session,
        user_id: int,
        entry_date: Optional[datetime] = None,
    ) -> bool:
        """
        Idempotent: post Step 2 when KYC is approved. Returns True if recognition was posted.
        """
        deposit = get_latest_validated_kyc_deposit(db, user_id)
        if not deposit:
            logger.warning("post_kyc_verification_recognition: no validated KYC deposit for user %s", user_id)
            return False
        if kyc_recognition_posted(db, deposit.id):
            return False
        commissions = (
            db.query(AffiliateCommission).filter(AffiliateCommission.deposit_id == deposit.id).all()
        )
        self.process_kyc_verification_performed_accounting(
            db, deposit, commissions, entry_date=entry_date, journal_commit=True
        )
        return True

    def process_kyc_payment_accounting(
        self,
        db: Session,
        deposit: Deposit,
        commissions: List[AffiliateCommission],
        entry_date: Optional[datetime] = None,
        *,
        journal_commit: bool = True,
    ):
        """
        Backward-compatible name: Step 1 only (USDT BSC receipt / deferred).
        Step 2 runs via post_kyc_verification_recognition_for_user when KYC is approved.
        """
        self.process_kyc_cash_receipt_accounting(
            db, deposit, entry_date=entry_date, journal_commit=journal_commit
        )

    def process_membership_payment_accounting(
        self,
        db: Session,
        deposit: Deposit,
        commissions: List[AffiliateCommission],
        entry_date: Optional[datetime] = None,
        *,
        journal_commit: bool = True,
    ):
        """
        Annual membership: Dr 1001 / Cr 2110 (deferred), then recognition with 10% gross to2104,
        optional $2 Shufti pass-through on small tiers, net to 4002. Commissions: Dr 5001 / Cr2001–2002.

        Legacy rows that already have ``(Income)`` journals keep the old pattern; new deposits use deferred 2110.
        """
        dep_id = deposit.id
        if _annual_membership_legacy_income_posted(db, dep_id):
            logger.info(
                "Annual membership legacy (Income) already posted for deposit %s; skipping new flow",
                dep_id,
            )
            return

        gross = _money_dec(Decimal(str(deposit.amount)))
        description = f"Membership Payment - Deposit #{dep_id} - User #{deposit.user_id}"
        jdate = _journal_entry_date(deposit, entry_date)

        pool_amt = _money_dec(gross * Decimal("0.10"))
        shufti_amt = (
            _money_dec(Decimal("2.00")) if gross <= Decimal("12.00") else _money_dec(Decimal("0"))
        )
        net_revenue = _money_dec(gross - pool_amt - shufti_amt)

        if commissions and not _annual_membership_commissions_posted(db, dep_id):
            commission_lines = []
            total_comm = Decimal("0.0")

            for comm in commissions:
                c_amt = Decimal(str(comm.commission_amount))
                total_comm += c_amt
                payable_acc = "2001" if comm.level == 1 else "2002"

                commission_lines.append(
                    {
                        "account_code": payable_acc,
                        "debit": 0.0,
                        "credit": float(c_amt),
                        "description": f"Comm L{comm.level} User #{comm.user_id}",
                    }
                )

            commission_lines.insert(
                0,
                {
                    "account_code": "5001",
                    "debit": float(total_comm),
                    "credit": 0.0,
                    "description": "Total Commissions",
                },
            )

            accounting_service.create_journal_entry(
                db,
                description=description + " (Commissions)",
                lines=commission_lines,
                date=jdate,
                commit=journal_commit,
            )

        if not _annual_membership_deferred_posted(db, dep_id):
            accounting_service.create_journal_entry(
                db,
                description=description + " (Deferred receipt - annual membership)",
                lines=[
                    {
                        "account_code": "1001",
                        "debit": float(gross),
                        "credit": 0.0,
                        "description": (
                            f"USDT (BSC) on-chain inflow — annual membership from member; "
                            f"Deposit #{dep_id} User #{deposit.user_id}"
                        ),
                    },
                    {
                        "account_code": "2110",
                        "debit": 0.0,
                        "credit": float(gross),
                        "description": "Deferred revenue — annual membership (unearned until recognized)",
                    },
                ],
                date=jdate,
                commit=journal_commit,
            )

        if not _annual_membership_recognition_posted(db, dep_id):
            rec_lines: List[dict] = [
                {
                    "account_code": "2110",
                    "debit": float(gross),
                    "credit": 0.0,
                    "description": "Release deferred revenue — annual membership activated",
                },
                {
                    "account_code": "4002",
                    "debit": 0.0,
                    "credit": float(net_revenue),
                    "description": (
                        "Membership revenue after Founding Members pool (10% of gross) "
                        "and Shufti pass-through (if applicable)"
                    ),
                },
                {
                    "account_code": "2104",
                    "debit": 0.0,
                    "credit": float(pool_amt),
                    "description": "Accrued liability — Founding Members pool (10% of gross)",
                },
            ]
            if shufti_amt > 0:
                rec_lines.append(
                    {
                        "account_code": "2003",
                        "debit": 0.0,
                        "credit": float(shufti_amt),
                        "description": "Payable to KYC verification provider (annual tier pass-through)",
                    }
                )
            accounting_service.create_journal_entry(
                db,
                description=description + " (Recognition - annual membership)",
                lines=rec_lines,
                date=jdate,
                commit=journal_commit,
            )

    def process_founding_membership_payment_accounting(
        self,
        db: Session,
        deposit: Deposit,
        commissions: List[AffiliateCommission],
        entry_date: Optional[datetime] = None,
        *,
        journal_commit: bool = True,
    ):
        """
        Founding / MFM membership (e.g. $100): Dr 1001 / Cr 2111 (deferred), then recognition:
        Dr 2111 / Cr 4002 (net after 10% pool), Cr 2104 (10% of gross). Commissions: Dr 5001 / Cr 2001–2002.

        Legacy ``(Income)`` journals are left unchanged; new deposits use deferred 2111.
        """
        dep_id = deposit.id
        if _founding_membership_legacy_income_posted(db, dep_id):
            logger.info(
                "Founding membership legacy (Income) already posted for deposit %s; skipping new flow",
                dep_id,
            )
            return

        gross = _money_dec(Decimal(str(deposit.amount)))
        description = f"Founding Membership Payment - Deposit #{dep_id} - User #{deposit.user_id}"
        jdate = _journal_entry_date(deposit, entry_date)

        pool_amt = _money_dec(gross * Decimal("0.10"))
        net_revenue = _money_dec(gross - pool_amt)

        if commissions and not _founding_membership_commissions_posted(db, dep_id):
            commission_lines = []
            total_comm = Decimal("0.0")
            for comm in commissions:
                c_amt = Decimal(str(comm.commission_amount))
                total_comm += c_amt
                payable_acc = "2001" if comm.level == 1 else "2002"
                commission_lines.append(
                    {
                        "account_code": payable_acc,
                        "debit": 0.0,
                        "credit": float(c_amt),
                        "description": f"Comm L{comm.level} User #{comm.user_id}",
                    }
                )
            commission_lines.insert(
                0,
                {
                    "account_code": "5001",
                    "debit": float(total_comm),
                    "credit": 0.0,
                    "description": "Total commissions",
                },
            )
            accounting_service.create_journal_entry(
                db,
                description=description + " (Commissions)",
                lines=commission_lines,
                date=jdate,
                commit=journal_commit,
            )

        if not _founding_membership_deferred_posted(db, dep_id):
            accounting_service.create_journal_entry(
                db,
                description=description + " (Deferred receipt - founding membership)",
                lines=[
                    {
                        "account_code": "1001",
                        "debit": float(gross),
                        "credit": 0.0,
                        "description": (
                            f"USDT (BSC) on-chain inflow — founding membership from member; "
                            f"Deposit #{dep_id} User #{deposit.user_id}"
                        ),
                    },
                    {
                        "account_code": "2111",
                        "debit": 0.0,
                        "credit": float(gross),
                        "description": "Deferred revenue — founding membership (unearned until recognized)",
                    },
                ],
                date=jdate,
                commit=journal_commit,
            )

        if not _founding_membership_recognition_posted(db, dep_id):
            accounting_service.create_journal_entry(
                db,
                description=description + " (Recognition - founding membership)",
                lines=[
                    {
                        "account_code": "2111",
                        "debit": float(gross),
                        "credit": 0.0,
                        "description": "Release deferred revenue — founding membership activated",
                    },
                    {
                        "account_code": "4002",
                        "debit": 0.0,
                        "credit": float(net_revenue),
                        "description": (
                            "Founding membership revenue after Founding Members pool (10% of gross)"
                        ),
                    },
                    {
                        "account_code": "2104",
                        "debit": 0.0,
                        "credit": float(pool_amt),
                        "description": "Accrued liability — Founding Members pool (10% of gross)",
                    },
                ],
                date=jdate,
                commit=journal_commit,
            )

    def process_club_membership_payment_accounting(
        self,
        db: Session,
        deposit: Deposit,
        commissions: List[AffiliateCommission],
        entry_date: Optional[datetime] = None,
        *,
        journal_commit: bool = True,
    ) -> None:
        """
        Club membership: member pays base + 20% platform markup. Base is owed to the club owner (2120);
        markup clears via 2112 to 2104 (10% of markup — Founding pool), sponsor payables, and net platform revenue (4003).
        """
        charge = Decimal(str(deposit.amount))
        base = (charge / Decimal("1.2")).quantize(Decimal("0.01"))
        split = club_markup_split(base)
        dep_id = deposit.id
        description = f"Club Membership Payment - Deposit #{dep_id} - User #{deposit.user_id}"
        jdate = _journal_entry_date(deposit, entry_date)

        markup_amt = split.markup
        pool_amt = split.founding_pool
        c_total = sum(Decimal(str(c.commission_amount)) for c in commissions)
        plat = markup_amt - pool_amt - c_total
        if plat < Decimal("0"):
            logger.warning(
                "Club membership deposit %s: commissions (%s) exceed markup net of pool; zeroing platform revenue",
                dep_id,
                c_total,
            )
            plat = Decimal("0")

        accounting_service.create_journal_entry(
            db,
            description=description + " (USDT BSC receipt and payables)",
            lines=[
                {
                    "account_code": "1001",
                    "debit": float(charge),
                    "credit": 0.0,
                    "description": (
                        f"USDT (BSC) on-chain inflow — club membership from member; "
                        f"Deposit #{dep_id} User #{deposit.user_id}"
                    ),
                },
                {
                    "account_code": "2120",
                    "debit": 0.0,
                    "credit": float(split.base_to_owner),
                    "description": "Payable to club owner — member base subscription (pass-through)",
                },
                {
                    "account_code": "2112",
                    "debit": 0.0,
                    "credit": float(markup_amt),
                    "description": "Club platform markup (20%) — clearing",
                },
            ],
            date=jdate,
            commit=journal_commit,
        )

        alloc_lines: List[dict] = [
            {
                "account_code": "2112",
                "debit": float(markup_amt),
                "credit": 0.0,
                "description": "Release markup for allocation",
            },
        ]
        if commissions:
            alloc_lines.append(
                {
                    "account_code": "5001",
                    "debit": float(c_total),
                    "credit": 0.0,
                    "description": "Commission expense — club membership markup",
                }
            )
        alloc_lines.extend(
            [
                {
                    "account_code": "2104",
                    "debit": 0.0,
                    "credit": float(pool_amt),
                    "description": "Accrued liability — Founding Members pool (10% of club markup)",
                },
                {
                    "account_code": "4003",
                    "debit": 0.0,
                    "credit": float(plat),
                    "description": "Club subscription — net platform revenue (markup after pool and sponsors)",
                },
            ]
        )
        for comm in commissions:
            ca = Decimal(str(comm.commission_amount))
            payable_acc = "2001" if comm.level == 1 else "2002"
            alloc_lines.append(
                {
                    "account_code": payable_acc,
                    "debit": 0.0,
                    "credit": float(ca),
                    "description": f"Affiliate commission L{comm.level} User #{comm.user_id}",
                }
            )

        accounting_service.create_journal_entry(
            db,
            description=description + " (Markup allocation — Founding pool and platform)",
            lines=alloc_lines,
            date=jdate,
            commit=journal_commit,
        )

    def record_kyc_provider_settlement(
        self,
        db: Session,
        amount: float,
        entry_date: Optional[datetime] = None,
        reference: str = "",
    ) -> JournalEntry:
        """
        Operational payment to Shufti: Dr 2003 (reduce AP), Cr 1001 (USDT BSC outflow).
        """
        if amount <= 0:
            raise ValueError("amount must be positive")
        jdate = entry_date or datetime.utcnow()
        desc = "KYC provider (Shufti) settlement — USDT (BSC) paid out"
        if reference:
            desc += f" ref={reference}"
        lines = [
            {
                "account_code": "2003",
                "debit": float(amount),
                "credit": 0.0,
                "description": "Pay Shufti — clear accounts payable (KYC verification provider)",
            },
            {
                "account_code": "1001",
                "debit": 0.0,
                "credit": float(amount),
                "description": "USDT (BSC) on-chain outflow — settlement to Shufti (KYC provider)",
            },
        ]
        return accounting_service.create_journal_entry(db, description=desc, lines=lines, date=jdate)


payment_accounting = PaymentAccountingService()
