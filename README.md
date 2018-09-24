# What is Grisbi2Ledger? #

Grisbi2Ledger is a script to convert financial tracking files from the
XML-based format used by the open-source tool Grisbi <http://grisbi.org> into
the plain-text format used by Ledger <http://ledger-cli.org> and similar tools.


# How do I run it? #

./grisbi2ledger /path/to/input.gsb /path/to/output.ldg


# What exactly does it convert to? #

## Accounts ##

Each account in Grisbi turns into one account in Ledger. The name is the Grisbi
name prefixed with either `Assets:` or `Liabilities:` depending on the Grisbi
account type. An `account` directive is added, along with a currency assertion
and notes for certain Grisbi fields such as account number. Any nonzero opening
balance is taken from an account called `Equity:Opening Balance` in a single
transaction generated at the top of the Ledger file.

## Currencies ##

Each currency in Grisbi turns into one currency in Ledger. The symbol in Ledger
is the symbol in Grisbi if either that symbol is unique or this is the first
currency using it; otherwise, the symbol in Ledger is the abbreviation in
Grisbi. A note is added to the `commodity` directive with the name of the
currency.

## Transactions ##

Each normal transaction (i.e. not a split or transfer) in Grisbi becomes a
transaction in Ledger with two postings, one for the asset or liability account
and one for an account named after the category (and sub-category if present)
prefixed with either `Income:` or `Expenses:` depending on the Grisbi category
type. If the transaction involved a foreign currency, the asset or liability
posting uses its native currency while the income or expense posting uses the
foreign currency amount with @ syntax.

Each pair of transactions forming a transfer in Grisbi becomes a single
transaction in Ledger with two postings, one for each account, in its native
currency.

Each split transaction in Grisbi becomes a single transaction in Ledger with
one posting for the account in which the split transaction appeared plus one
more posting for each child transaction. Both normal and transfer transactions
may appear as children of splits, and their postings are generated as per the
preceding two paragraphs.

In all cases, the payee name of a transaction is copied from Grisbi to Ledger.
Any Grisbi notes are copied into Ledger comments. If a bank reference is
present on exactly one Grisbi transaction, it is copied into the Ledger
transaction’s CODE field; otherwise, the bank references are copied into
comments. Comments indicating the Grisbi transaction numbers involved are
written out in the Ledger transaction.

Each posting is marked with a `*` (cleared) if and only if the corresponding
Grisbi transaction has been reconciled.

## Reconciliations ##

Each reconciliation in Grisbi becomes a transaction in Ledger with the payee
name `Reconciliation` and a single balanced-virtual (i.e.
square-bracket-syntax) posting with a balance assertion against the reconciled
value. The reconciliation name from Grisbi is copied into a comment, as is the
list of which Grisbi transactions are covered by the reconciliation.


# Is it production-ready? #

Nope.

There are probably certain Grisbi features it doesn’t handle. It makes many
sanity checks before starting the conversion, so in most cases, if it sees
something it doesn’t understand, it will abort and explain the problem. Its
output is also a bit messy in some cases.

It also probably doesn’t produce output in exactly the format you want. That’s
because it produces output in the format *I* want, and we probably want
slightly different formats. Please fork and change the output format to your
taste.

Please check the Issues tab for more details.


# Something is broken! #

Fix it and submit a pull request, please. I don’t use Grisbi2Ledger (I used it
exactly once, immediately after writing it); therefore I don’t actively
maintain it. I’ll accept pull requests that fix bugs, though, so other people
can benefit.



# License #

Grisbi2Ledger is © Christopher Head and is released under the GNU General
Public License version 3.
