"""
Single entrypoint for every parser call.

Everything outside ``app.libs.parsers`` goes through :class:`StatementParser`
-- it picks the concrete parser by a source's ``code`` (see
``StatementSourceRecord.code``) and falls back to the LLM-backed
:class:`~app.libs.parsers.unknown.UnknownParser` for a source with no
dedicated parser.
"""

import inspect
from typing import Any, ClassVar

from app.libs.parsers.base import BaseParser
from app.libs.parsers.bunq import BunqStatementParser
from app.libs.parsers.credo import CredoStatementParser
from app.libs.parsers.deblock import DeblockStatementParser
from app.libs.parsers.dukascopy import DukascopyStatementParser
from app.libs.parsers.market_bill import MarketBillParser
from app.libs.parsers.nexo import NexoStatementParser
from app.libs.parsers.revolut import RevolutStatementParser
from app.libs.parsers.unknown import UnknownParser
from app.libs.parsers.wise import WiseStatementParser


class StatementParser:
    """Parses an uploaded file with whichever parser a source code maps to."""

    _parsers_mapping: ClassVar[dict[str, type[BaseParser]]] = {
        "wise": WiseStatementParser,
        "bunq": BunqStatementParser,
        "deblock": DeblockStatementParser,
        "dukascopy": DukascopyStatementParser,
        "market_bill": MarketBillParser,
        "revolut": RevolutStatementParser,
        "nexo": NexoStatementParser,
        "credo": CredoStatementParser,
    }

    def __init__(self, source: str) -> None:
        self._source = source

    @property
    def source(self) -> str:
        """The source code this entrypoint dispatches on."""
        return self._source

    @source.setter
    def source(self, value: str) -> None:
        self._source = value

    @property
    def parser(self) -> BaseParser:
        """The parser instance for the current source."""
        return self._parsers_mapping.get(self._source, UnknownParser)()

    async def parse(self, file_bytes: bytes, *args: Any, **kwargs: Any) -> Any:
        """
        Parse a file with the current source's parser.

        :param file_bytes: the raw uploaded file.
        :param args: parser-specific positional arguments (e.g. a bill's
            content type).
        :param kwargs: parser-specific keyword arguments.
        :return: the parser's result -- rows for a statement, a
            ``ParsedBill`` for ``market_bill``.
        """
        result = self.parser.parse(file_bytes, *args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result
