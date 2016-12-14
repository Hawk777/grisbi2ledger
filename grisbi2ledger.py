#!/usr/bin/env python3

import argparse
import datetime
import decimal
import sys
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

    def resolve_references(self, data):
        """Resolve the reference to the account’s currency."""
        self.currency = data.currencies[self.currency]

    def ledger_name(self):
        """Return the name of the account in Ledger."""
        return "{}:{}".format("Liabilities" if self.kind == ACCOUNT_KIND_LIABILITY else "Assets", self.name)


class Category(object):
    """A transaction payee category.

    number -- the Grisbi-internal ID number of the category
    name -- the name of the category
    is_expenses -- whether this category is used for expenses (versus income)
    sub_categories -- the subcategories in this category
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
        self.sub_categories = {}

    def resolve_references(self, data):
        """Do nothing."""
        pass


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

    def resolve_references(self, data):
        """Resolve the reference to the Category and add self to it."""
        self.category = data.categories[self.category]
        self.category.sub_categories[self.number] = self


class Currency(object):
    """A currency.

    number -- the Grisbi-internal ID number of the currency
    name -- the long human-readable name of the currency (e.g. Canadian Dollar)
    symbol -- the very short symbolic identifier of the currency (e.g. $)
    abbreviation -- the short abbreviation of the currency (e.g. CAD)
    ledger_symbol -- symbol or abbreviation, whichever is appropriate
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

    def resolve_references(self, data):
        """Decide what symbol to use for this currency."""
        if (self.symbol is None) or any(i.number < self.number and i.symbol == self.symbol for i in data.currencies.values()):
            # Some other currency uses the same symbol and appears before us,
            # or we have no symbol; use the abbreviation.
            self.ledger_symbol = self.abbreviation
        else:
            # No other currency uses the same symbol, or we are the first to
            # use it; use the symbol.
            self.ledger_symbol = self.symbol


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

    def resolve_references(self, data):
        """Do nothing."""
        pass


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

    def resolve_references(self, data):
        """Resolve the reference to the account."""
        self.account = data.accounts[self.account]


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
    children -- the children of this transaction, if it is a split transaction
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
        self.children = {}

    def resolve_references(self, data):
        """Resolve references to various other objects."""
        self.account = data.accounts[self.account]
        self.currency = data.currencies[self.currency]
        if self.party is not None:
            self.party = data.parties[self.party]
        if self.category is not None:
            self.category = data.categories[self.category]
        if self.sub_category is not None:
            self.sub_category = self.category.sub_categories[self.sub_category]
        if self.reconciliation is not None:
            self.reconciliation = data.reconciles[self.reconciliation]
        if self.contra_transaction is not None:
            self.contra_transaction = data.transactions[self.contra_transaction]
        if self.mother is not None:
            self.mother = data.transactions[self.mother]
            self.mother.children[self.number] = self
            if self.date is None:
                self.date = self.mother.date
            # Grisbi sometimes records children of splits as reconciled and
            # sometimes doesn’t. There is no clear logic as to why it picks
            # either status. The UI never shows a marking on children, and does
            # not allow selecting children independently for reconciliation.
            # The data seems useless. Instead, just inherit the reconiliation
            # situation from the mother.
            self.reconciled = self.mother.reconciled
            self.reconciliation = self.mother.reconciliation

    def effective_exchange_rate(self):
        """Return the exchange rate.

        This is a number of account currency units per transaction currency
        units.
        """
        if self.currency == self.account.currency:
            return decimal.Decimal("1.00")
        elif not self.change_between:
            return self.exchange_rate
        else:
            return decimal.Decimal("1.00") / self.exchange_rate


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

        # Resolve inter-object references from IDs to objects.
        for i in self.accounts, self.categories, subCategories, self.currencies, self.parties, self.reconciles, self.transactions:
            for j in i:
                i[j].resolve_references(self)


    def check(self):
        """Perform some basic sanity checks."""
        ok = True
        # We do not support transactions without a party, other than the parent
        # part of a split.
        for i in sorted(self.transactions.keys()):
            txn = self.transactions[i]
            if txn.party is None and not txn.is_split:
                print("Transaction {} in account {} on date {} has no party and is not a split.".format(txn.number, txn.account.name, txn.date))
                ok = False

        # We cannot have a split transaction with no children, or a non-split
        # transaction with children.
        for i in sorted(self.transactions.keys()):
            txn = self.transactions[i]
            if txn.is_split and not txn.children:
                print("Transaction {} in account {} on date {} is a split but has no children.".format(txn.number, txn.account.name, txn.date))
                ok = False
            elif not txn.is_split and txn.children:
                print("Transaction {} in account {} on date {} is not a split but has children.".format(txn.number, txn.account.name, txn.date))
                ok = False

        # The contra relationship between transactions must be symmetric.
        for i in sorted(self.transactions.keys()):
            txn = self.transactions[i]
            if txn.contra_transaction is not None:
                if txn.contra_transaction.contra_transaction is not txn:
                    print("Transaction {} in account {} on date {} has contra transaction {} in account {} on date {} but the latter transaction’s contra is {}, not {} as expected.".format(txn.number, txn.account.name, txn.date, txn.contra_transaction.number, txn.contra_transaction.account.name, txn.contra_transaction.date, txn.contra_transaction.contra_transaction.number, txn.number))
                    ok = False

        # We do not support transactions without a category or contra that are
        # not splits (a contra and a split both show up as if they were a
        # category in the Grisbi UI, but are not stored as such in the data
        # file).
        for i in sorted(self.transactions.keys()):
            txn = self.transactions[i]
            if txn.category is None and txn.contra_transaction is None and not txn.is_split:
                print("Transaction {} in account {} on date {} has no category or contra and is not a split.".format(txn.number, txn.account.name, txn.date))
                ok = False

        # A category or subcategory cannot contain two spaces or a tab in its
        # name.
        for i in sorted(self.categories.keys()):
            cat = self.categories[i]
            if "  " in cat.name or "\t" in cat.name:
                print("Category {} has two spaces or a tab in its name.".format(cat.name))
                ok = False
            for j in sorted(cat.sub_categories.keys()):
                sub_cat = cat.sub_categories[j]
                if "  " in sub_cat.name or "\t" in sub_cat.name:
                    print("Subcategory {}:{} has two spaces or a tab in its name.".format(cat.name, sub_cat.name))
                    ok = False

        # A transaction and its contra cannot both be part of splits.
        for i in sorted(self.transactions.keys()):
            txn = self.transactions[i]
            contra = txn.contra_transaction
            if contra is not None:
                if txn.mother is not None and contra.mother is not None:
                    print("Transaction {} in account {} on date {} has contra {} in account {} on date {} and both are part of splits.".format(txn.number, txn.account.name, txn.date, contra.number, contra.account.name, contra.date))
                    ok = False

        # Two reconciliations on the same account must not have the same date.
        seen = {}
        for rec in self.reconciles.values():
            if rec.account.number not in seen:
                seen[rec.account.number] = {}
            acc = seen[rec.account.number]
            if rec.date in acc:
                print("Reconciliation {} in account {} on date {} happened on the same day as reconciliation {}.".format(rec.name, rec.account.name, rec.date, acc[rec.date].name))
                ok = False
            acc[rec.date] = rec

        # A transaction must be reconciled if and only if it has a
        # reconciliation. Note that having a reconciliation but not being
        # marked reconciled is impossible due to how we load data.
        for i in sorted(self.transactions.keys()):
            txn = self.transactions[i]
            if txn.reconciled and txn.reconciliation is None:
                print("Transaction {} in account {} on date {} is reconciled but has no reconciliation.".format(i, txn.account.name, txn.date))
                ok = False

        # A transaction’s reconciliation must be for its own account.
        for i in sorted(self.transactions.keys()):
            outer_txn = self.transactions[i]
            for txn in outer_txn.all_transactions():
                if txn.reconciled and txn.reconciliation is not None:
                    if txn.reconciliation.account is not txn.account:
                        print("Transaction {} in account {} on date {} is reconciled by reconciliation {} on account {}.".format(txn.number, txn.account.name, txn.date, txn.reconciliation.name, txn.reconciliation.account.name))
                        ok = False

        return ok


    def clean(self):
        """Clean various things that need to be cleaned after the sanity checks
        are complete.
        """
        # A split transaction will be represented on the Ledger side as a
        # single transaction with many postings. On the Grisbi side, it is
        # represented as many transactions with a mother/child relationship
        # between them. Furthermore, each child might possibly be a transfer
        # and therefore, on the Grisbi side, have another transaction which is
        # its contra. All this should be packed up into a single transaction on
        # the Ledger side, which is best represented by the mother of the
        # split. Remove all the others.
        to_remove = []
        for txn in self.transactions.values():
            if txn.is_split:
                for child in txn.children.values():
                    to_remove.append(child.number)
                    contra = child.contra_transaction
                    if contra is not None:
                        to_remove.append(contra.number)
        for i in to_remove:
            del self.transactions[i]

        # A transfer will be represented on the Ledger side as a single
        # transaction with a posting in each involved account. On the Grisbi
        # side, it is represented as two transactions which are each other’s
        # contras. Remove one of them.
        to_remove = set()
        for i in sorted(self.transactions.keys()):
            if i not in to_remove:
                txn = self.transactions[i]
                contra = txn.contra_transaction
                if contra is not None:
                    to_remove.add(contra.number)
        for i in to_remove:
            del self.transactions[i]


    def _generate_reconciliation(self, fp, rec):
        """Generate a transaction for a reconciliation.

        fp -- the text file-like object to write to
        rec -- the reconciliation object to write out
        """
        fp.write("{} Reconciliation\n".format(rec.date))
        fp.write("\t; Grisbi reconciliation name: {}\n".format(rec.name))
        for i in sorted(self.transactions.keys()):
            outer_txn = self.transactions[i]
            for txn in (outer_txn, outer_txn.contra_transaction):
                if txn is not None:
                    if txn.reconciliation is rec:
                        fp.write("\t; Includes Grisbi transaction {}\n".format(txn.number))
        fp.write("\t* [{}]  ={}{}\n".format(rec.account.ledger_name(), rec.account.currency.ledger_symbol, rec.balance))
        fp.write("\n")


    def _get_cleared_string(self, txn):
        """Return the string for whether a transaction has cleared or not.

        txn -- the transaction
        """
        return "* " if txn.reconciled else ""


    def _generate_acc_posting(self, fp, txn, comment_bank_ref):
        """Generate a posting for an account.

        This is either the account part of a normal transaction (or split part)
        or one of the parts of a transfer.

        fp -- the text file-like object to write to
        txn -- the transaction to write
        comment_bank_ref -- whether to include the bank reference, if any, in
            the posting’s comment
        """
        if comment_bank_ref and txn.bank_reference is not None:
            comment = " ; Grisbi bank reference: {}".format(txn.bank_reference)
        else:
            comment = ""
        fp.write("\t{}{}  {}{}{}\n".format(self._get_cleared_string(txn), txn.account.ledger_name(), txn.account.currency.ledger_symbol, (txn.amount * txn.effective_exchange_rate()).quantize(decimal.Decimal("0.01")), comment))


    def _generate_cat_posting(self, fp, txn):
        """Generate a posting for a category.

        This could be the category part of a normal transaction or of a split
        part.

        fp -- the text file-like object to write to
        txn -- the transaction to write
        """
        # Build account name.
        cat = txn.category
        target = "{}:{}".format("Expenses" if cat.is_expenses else "Income", cat.name)
        if txn.sub_category is not None:
            target += ":" + txn.sub_category.name
        # Build amount, possibly with @-formatted commodity price.
        amount = "{}{}".format(txn.currency.ledger_symbol, -txn.amount)
        if txn.currency != txn.account.currency:
            amount += " @ {}{}".format(txn.account.currency.ledger_symbol, txn.effective_exchange_rate())
        # Render.
        fp.write("\t{}{}  {}\n".format(self._get_cleared_string(txn), target, amount))


    def generate_output(self, fp):
        """Generate a Ledger file.

        fp -- the text file-like object to write to
        """
        # Generate commodities.
        for i in sorted(self.currencies.keys()):
            curr = self.currencies[i]
            fp.write("commodity {}\n".format(curr.ledger_symbol))
            fp.write("\tnote {}\n".format(curr.name))
            fp.write("\n")

        # Generate accounts.
        for i in sorted(self.accounts.keys()):
            acc = self.accounts[i]
            fp.write("account {}\n".format(acc.ledger_name()))
            fp.write("\tassert commodity == \"{}\"\n".format(acc.currency.ledger_symbol))
            if acc.account_number is not None:
                if acc.branch_code is not None:
                    fp.write("\tnote Account number {}-{}\n".format(acc.branch_code, acc.account_number))
                else:
                    fp.write("\tnote Account number {}\n".format(acc.account_number))
            fp.write("\n")

        # Generate initial balances.
        if any(i.initial_balance != 0 for i in self.accounts.values()):
            fp.write("account Equity:Opening Balance\n")
            fp.write("\n")
            first_date = min(i.date for i in self.transactions.values())
            fp.write("{} Opening Balances\n".format(first_date))
            for i in sorted(self.accounts.keys()):
                acc = self.accounts[i]
                if acc.initial_balance != 0:
                    fp.write("\t* {}  {}{}\n".format(acc.ledger_name(), acc.currency.ledger_symbol, acc.initial_balance))
            fp.write("\t* Equity:Opening Balance\n\n")

        # Generate transactions. Interleave reconciliation records as
        # appropriate.
        last_reconcile = {i: None for i in self.accounts.keys()}
        for i in sorted(self.transactions.keys()):
            txn = self.transactions[i]
            # If this transaction is in a different reconciliation than the
            # last reconciliation in any account it touches, then write out
            # reconciliations for those accounts.
            for exact in txn.all_transactions():
                last = last_reconcile[exact.account.number]
                if exact.reconciliation is not last:
                    if last is not None:
                        self._generate_reconciliation(fp, last)
                    last_reconcile[exact.account.number] = exact.reconciliation

            # Check for bank references. If there is one, we will emit it
            # as a CODE. If multiple, we will emit them as comments on the
            # postings.
            bank_refs = set()
            for txns in ({txn.number: txn}, txn.children):
                for j in sorted(txns.keys()):
                    child_txn = txns[j]
                    if child_txn.bank_reference is not None:
                        bank_refs.add(child_txn.bank_reference)
                    if child_txn.contra_transaction is not None and child_txn.contra_transaction.bank_reference is not None:
                        bank_refs.add(child_txn.contra_transaction.bank_reference)
            comment_bank_ref = len(bank_refs) > 1
            code_bank_ref = "({}) ".format(list(bank_refs)[0]) if len(bank_refs) == 1 else ""

            # Write out basic top matter.
            fp.write("{} {}{}\n".format(txn.date, code_bank_ref, txn.party.name))
            fp.write("\t; Imported from Grisbi transaction {}.\n".format(txn.number))
            if txn.notes is not None:
                fp.write("\t; Grisbi notes: {}\n".format(txn.notes))

            if txn.is_split:
                # Split transaction. The parent and each child become a
                # posting.
                fp.write("\t; Grisbi transaction was a split totalling {}{}.\n".format(txn.currency.ledger_symbol, txn.amount))
                self._generate_acc_posting(fp, txn, comment_bank_ref)
                for j in sorted(txn.children.keys()):
                    child = txn.children[j]
                    if child.contra_transaction is None:
                        self._generate_cat_posting(fp, child)
                    else:
                        self._generate_acc_posting(fp, child.contra_transaction, comment_bank_ref)
                        fp.write("\t; Grisbi transaction {} was the contra and was not imported separately.\n".format(child.contra_transaction.number))
                fp.write("\n")
            else:
                # Non-split transaction.
                self._generate_acc_posting(fp, txn, comment_bank_ref)
                if txn.contra_transaction is not None:
                    # Transfer. Second posting is the other account.
                    self._generate_acc_posting(fp, txn.contra_transaction, comment_bank_ref)
                    fp.write("\t; Grisbi transaction {} was the contra and was not imported separately.\n".format(txn.contra_transaction.number))
                    fp.write("\n")
                else:
                    # Normal transaction. Second posting is the category.
                    self._generate_cat_posting(fp, txn)
                    fp.write("\n")

        # Generate the final reconciliations.
        for i in last_reconcile:
            rec = last_reconcile[i]
            if rec is not None:
                self._generate_reconciliation(fp, rec)

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

    # Sanity check.
    if not data.check():
        sys.exit(1)

    # Post-check cleanup.
    data.clean()

    # Generate output.
    with open(args.output, "w") as fp:
        data.generate_output(fp)


if __name__ == "__main__":
    main()
