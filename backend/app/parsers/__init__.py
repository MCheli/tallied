from app.parsers.monarch import MonarchParser
from app.parsers.etrade import ETradeParser
from app.parsers.mortgage import MortgageParser
from app.parsers.student_loan import StudentLoanParser
from app.parsers.generic import GenericParser

PARSERS = {
    "monarch": MonarchParser(),
    "etrade": ETradeParser(),
    "mortgage": MortgageParser(),
    "student_loan": StudentLoanParser(),
}


def get_parser(source: str):
    return PARSERS.get(source, GenericParser())
