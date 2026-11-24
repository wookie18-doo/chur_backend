"""
Dukascopy statement parser -- deliberately unimplemented.

Dukascopy is a trading platform, not a bank: its account statement mixes
deposits/withdrawals, trade P&L, swaps, and commissions in one export,
and the platform offers this in more than one format (a JForex-generated
CSV/Excel report, or an API pull) whose exact shape isn't something this
module can respond to without a real, current sample -- unlike Wise/bunq
(bank statements with a fairly standard "row = one payment" shape),
Dukascopy's rows need an explicit, verified decision about which row
types even belong in a spend/income ledger (see the build plan's Phase 9
note: skip deposits/withdrawals as transfers, keep trade P&L/commissions)
before any parsing logic can be written correctly.

Writing a guessed parser here would be actively worse than not having
one: a wrong mapping could silently record a trade's gross P&L as a
income/spend and mislead the user's own financial picture. Get one real
Dukascopy export, decide the row-type handling explicitly, and replace
this module (with a test fixture pinned to that sample) before enabling
the ``dukascopy`` source in the parser registry.
"""

from app.libs.parsers.base import BaseParser, ParsedTransaction, UnparseableRow


class DukascopyStatementParser(BaseParser):
    """Placeholder -- see this module's docstring for why."""

    def parse(self, file_bytes: bytes) -> list[ParsedTransaction | UnparseableRow]:
        """
        Not implemented -- see this module's docstring.

        :param file_bytes: the raw uploaded file.
        :raises NotImplementedError: always, until a real sample export
            has been used to write and verify this parser.
        """
        raise NotImplementedError(
            "Dukascopy import isn't implemented yet -- it needs a real "
            "sample export and an explicit row-type decision first "
            "(see app/libs/parsers/dukascopy.py)."
        )
