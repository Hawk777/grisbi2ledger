#!/usr/bin/env python3

import argparse
import datetime
import decimal
import xml.etree.ElementTree as ET


def _parse_date(d):
    """Parse a Grisby-style MM/dd/YYYY date into a datetime.date object."""
    if d == "(null)":
        return None
    else:
        parts = d.split("/")
        return datetime.date(int(parts[2]), int(parts[0]), int(parts[1]))


ACCOUNT_KIND_BANK = 0
ACCOUNT_KIND_CASH = 1
ACCOUNT_KIND_LIABILITY = 2
ACCOUNT_KIND_ASSET = 3


class Account(object):
    """An account.

    number -- the Grisbi-internal ID number of the account
    name -- the human-readable name of the account
    currency -- which native currency the account holds
    initial_balance -- the balance of the account at opening
    kind -- one of the account kind constants
    branch_code -- the bank branch code, or None
    account_number -- the account number from the bank, or None
    """
    def __init__(self, accountElt):
        """Construct an Account.

        accountElt -- the XML Account element
        """
        assert accountElt.tag == "Account"
        self.name = accountElt.get("Name")
        assert self.name is not None
        assert self.name != "(null)"
        self.number = int(accountElt.get("Number"))
        self.currency = int(accountElt.get("Currency"))
        self.initial_balance = decimal.Decimal(accountElt.get("Initial_balance"))
        self.kind = int(accountElt.get("Kind"))
        assert self.kind in (ACCOUNT_KIND_BANK, ACCOUNT_KIND_CASH, ACCOUNT_KIND_LIABILITY, ACCOUNT_KIND_ASSET)
        self.branch_code = accountElt.get("Bank_branch_code")
        if self.branch_code == "(null)":
            self.branch_code = None
        self.account_number = accountElt.get("Bank_account_number")
        if self.account_number == "(null)":
            self.account_number = None


class Category(object):
    """A transaction payee category.

    number -- the Grisbi-internal ID number of the category
    name -- the name of the category
    is_expenses -- whether this category is used for expenses (versus income)
    """
    def __init__(self, catElt):
        """Construct a Category.

        catElt -- the XML Category element
        """
        assert catElt.tag == "Category"
        self.number = int(catElt.get("Nb"))
        self.name = catElt.get("Na")
        kd = int(catElt.get("Kd"))
        assert kd in (0, 1)
        self.is_expenses = bool(kd)


class SubCategory(object):
    """A transaction payee subcategory.

    number -- the Grisbi-internal ID number of the subcategory (unique only
        within the parent category)
    name -- the name of the subcategory
    category -- the parent category
    """
    def __init__(self, subCatElt):
        """Construct a SubCategory

        subCatElt -- the XML Sub_category element
        """
        assert subCatElt.tag == "Sub_category"
        self.number = int(subCatElt.get("Nb"))
        self.category = int(subCatElt.get("Nbc"))
        self.name = subCatElt.get("Na")


class Currency(object):
    """A currency.

    number -- the Grisbi-internal ID number of the currency
    name -- the long human-readable name of the currency (e.g. Canadian Dollar)
    symbol -- the very short symbolic identifier of the currency (e.g. $)
    abbreviation -- the short abbreviation of the currency (e.g. CAD)
    """
    def __init__(self, curElt):
        """Construct a Currency.

        curElt -- the XML Currency element
        """
        assert curElt.tag == "Currency"
        self.number = int(curElt.get("Nb"))
        self.name = curElt.get("Na")
        self.symbol = curElt.get("Co")
        if self.symbol == "(null)":
            self.symbol = None
        self.abbreviation = curElt.get("Ico")
        assert curElt.get("Fl") == "2", "Only two-decimal-place currencies are supported."


class Party(object):
    """A counterparty to transactions.

    number -- the Grisbi-internal ID number of the counterparty
    name -- the name of the counterparty
    """
    def __init__(self, partyElt):
        """Construct a Party.

        partyElt -- the XML Party element
        """
        assert partyElt.tag == "Party"
        self.number = int(partyElt.get("Nb"))
        self.name = partyElt.get("Na")


class Reconcile(object):
    """A reconciliation.

    number -- the Grisbi-internal ID number of the reconciliation
    name -- the name of the reconciliation
    account -- which account is being reconciled
    date -- the date on which the reconciliation took place
    balance -- the balance of the account at the reconciled point
    """
    def __init__(self, recElt):
        """Construct a Reconcile.

        recElt -- the XML Reconcile element
        """
        assert recElt.tag == "Reconcile"
        self.number = int(recElt.get("Nb"))
        self.name = recElt.get("Na")
        self.account = int(recElt.get("Acc"))
        self.date = _parse_date(recElt.get("Fdate"))
        self.balance = decimal.Decimal(recElt.get("Fbal"))


class Transaction(object):
    """A transaction.

    number -- the Grisbi-internal ID number of the transaction
    account -- which account the transaction occurred on
    date -- the date on which the transaction took place
    currency -- which currency the amount field is measured in
    amount -- the amount of money moved
    change_between -- True if a transaction in a non-native currency to the
        account’s amount must be divided by the exchange rate to get the
        corresponding amount in the account’s native currency, or False if it
        must be multiplied (ignored if the transaction is in the account’s
        native currency, even if an exchange rate is provided)
    exchange_rate -- the exchange rate between the transaction’s currency and
        the containing account’s native currency (ignored if the transaction is
        in the account’s native currency, though a value may still be present
        in this field)
    party -- the counterparty with whom this transaction occurred, or None if
        one was not specified
    category -- the category of transaction, or None if one was not specified
    sub_category -- the subcategory of transaction, or None if no category was
        specified or only a top-level category was selected (no subcategory)
    is_split -- whether or not this is a split transaction
    notes -- additional notes attached to the transaction, or None if not
        provided
    reconciled -- whether this transaction is reconciled or not
    reconciliation -- which reconciliation this transaction is part of, or None
        if not reconciled yet or if it is reconciled but the reconciliation
        object has not been kept
    bank_reference -- a freeform reference number field, or None if not
        provided
    contra_transaction -- the other half of this transaction, or None if this
        is not part of an inter-account transfer
    mother -- the split transaction that this transaction is part of, or None
        if this is a top-level transaction
    """
    def __init__(self, txnElt):
        """Construct a Transaction.

        txnElt -- the XML Transaction element
        """
        assert txnElt.tag == "Transaction"
        self.account = int(txnElt.get("Ac"))
        self.number = int(txnElt.get("Nb"))
        self.date = _parse_date(txnElt.get("Dt"))
        self.currency = int(txnElt.get("Cu"))
        self.amount = decimal.Decimal(txnElt.get("Am"))
        self.change_between = int(txnElt.get("Exb"))
        assert self.change_between in (0, 1)
        self.change_between = bool(self.change_between)
        self.exchange_rate = decimal.Decimal(txnElt.get("Exr"))
        assert txnElt.get("Exf") == "0.00", "Exchange fees are not supported."
        self.party = int(txnElt.get("Pa")) or None
        self.category = int(txnElt.get("Ca")) or None
        self.sub_category = int(txnElt.get("Sca")) or None
        self.is_split = int(txnElt.get("Br"))
        assert self.is_split in (0, 1)
        self.is_split = bool(self.is_split)
        self.notes = txnElt.get("No")
        if self.notes == "(null)":
            self.notes = None
        marked = int(txnElt.get("Ma"))
        assert marked in (0, 3)
        self.reconciled = marked == 3
        if marked == 3:
            self.reconciliation = int(txnElt.get("Re")) or None
        else:
            self.reconciliation = None
        self.bank_reference = txnElt.get("Ba")
        if self.bank_reference == "(null)":
            self.bank_reference = None
        self.contra_transaction = int(txnElt.get("Trt")) or None
        self.mother = int(txnElt.get("Mo")) or None


class Data(object):
    """A Grisbi file.

    accounts -- a dict from ID to Account
    categories -- a dict from ID to Category
    currencies -- a dict from ID to Currency
    parties -- a dict from ID to Party
    reconciles -- a dict from ID to Reconcile
    transactions -- a dict from ID to Transaction
    """
    def __init__(self, grisbiElt):
        """Construct a new Data

        grisbiElt -- the XML Grisbi element
        """
        # Parse input.
        assert grisbiElt.tag == "Grisbi"
        self.accounts = {}
        self.categories = {}
        subCategories = {}
        self.currencies = {}
        self.parties = {}
        self.reconciles = {}
        self.transactions = {}
        for child in grisbiElt:
            if isinstance(child, ET.Element):
                if child.tag == "Account":
                    account = Account(child)
                    assert account.number not in self.accounts
                    self.accounts[account.number] = account
                elif child.tag == "Category":
                    category = Category(child)
                    assert category.number not in self.categories
                    self.categories[category.number] = category
                elif child.tag == "Sub_category":
                    subCat = SubCategory(child)
                    key = (subCat.category, subCat.number)
                    assert key not in subCategories
                    subCategories[key] = subCat
                elif child.tag == "Currency":
                    cur = Currency(child)
                    assert cur.number not in self.currencies
                    self.currencies[cur.number] = cur
                elif child.tag == "Party":
                    party = Party(child)
                    assert party.number not in self.parties
                    self.parties[party.number] = party
                elif child.tag == "Reconcile":
                    rec = Reconcile(child)
                    assert rec.number not in self.reconciles
                    self.reconciles[rec.number] = rec
                elif child.tag == "Transaction":
                    txn = Transaction(child)
                    assert txn.number not in self.transactions
                    self.transactions[txn.number] = txn


def main():
    """Application entry point."""
    # Parse parameters.
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Grisbi .gsb file to read from")
    parser.add_argument("output", help="Ledger .txt file to write to")
    args = parser.parse_args()

    # Parse input file.
    grisbiElt = ET.parse(args.input).getroot()
    data = Data(grisbiElt)


if __name__ == "__main__":
    main()
