# © 2017 Opener BV (<https://opener.amsterdam>)
# © 2020 Vanmoof BV (<https://www.vanmoof.com>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import api, models


class BankStatement(models.Model):
    _inherit = 'account.bank.statement'

    @api.multi
    def get_reconcile_clearing_account_lines(self):
        if (self.journal_id.default_debit_account_id !=
                self.journal_id.default_credit_account_id or
                not self.journal_id.default_debit_account_id.reconcile):
            return False
        account = self.journal_id.default_debit_account_id
        currency = self.journal_id.currency_id or self.company_id.currency_id

        def get_bank_line(st_line):
            for line in st_line.journal_entry_ids:
                if st_line.amount > 0:
                    compare_amount = st_line.amount
                    field = 'debit'
                else:
                    compare_amount = -st_line.amount
                    field = 'credit'
                if (line[field] and
                        not currency.compare_amounts(
                            line[field], compare_amount) and
                        line.account_id == account):
                    return line
            return False

        move_lines = self.env['account.move.line']
        for st_line in self.line_ids:
            bank_line = get_bank_line(st_line)
            if not bank_line:
                return False
            move_lines += bank_line
        balance = sum(line.debit - line.credit for line in move_lines)
        if not currency.is_zero(balance):
            return False
        return move_lines

    @api.multi
    def reconcile_clearing_account(self):
        self.ensure_one()
        lines = self.get_reconcile_clearing_account_lines()
        if not lines:
            return False
        if any(line.full_reconcile_id for line in lines):
            return False
        lines.reconcile()

    @api.multi
    def unreconcile_clearing_account(self):
        self.ensure_one()
        lines = self.get_reconcile_clearing_account_lines()
        if not lines:
            return False
        reconciliation = lines[0].full_reconcile_id
        if reconciliation and lines == reconciliation.reconciled_line_ids:
            lines.remove_move_reconcile()

    @api.multi
    def button_draft(self):
        res = super(BankStatement, self).button_draft()
        for statement in self:
            statement.unreconcile_clearing_account()
        return res

    @api.multi
    def button_confirm_bank(self):
        res = super(BankStatement, self).button_confirm_bank()
        for statement in self:
            statement.reconcile_clearing_account()
        return res
