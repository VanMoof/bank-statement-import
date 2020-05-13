# © 2017 Opener BV (<https://opener.amsterdam>)
# © 2020 Vanmoof BV (<https://www.vanmoof.com>)
# © 2015 Therp BV (<http://therp.nl>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import base64
from odoo import tests
from odoo.tests.common import TransactionCase
from odoo.modules.module import get_module_resource


@tests.tagged('standard', 'at_install')
class TestImportAdyen(TransactionCase):
    def setUp(self):
        super(TestImportAdyen, self).setUp()
        self.journal = self.env['account.journal'].create({
            'company_id': self.env.user.company_id.id,
            'name': 'Adyen test',
            'code': 'ADY',
            'type': 'bank',
        })
        self.journal.default_debit_account_id.reconcile = True
        self.journal.write({
            'adyen_merchant_account': 'YOURCOMPANY_ACCOUNT',
            'update_posted': True,
            'currency_id': self.ref('base.USD'),
        })

    def test01_import_adyen(self):
        self._test_statement_import(
            'account_bank_statement_import_adyen', 'adyen_test.xlsx',
            'YOURCOMPANY_ACCOUNT 2016/48', self.journal)
        statement = self.env['account.bank.statement'].search(
            [], order='create_date desc', limit=1)
        self.assertEqual(len(statement.line_ids), 22)
        self.assertTrue(
            self.env.user.company_id.currency_id.is_zero(
                sum(line.amount for line in statement.line_ids)))

        account = self.env['account.account'].search([(
            'internal_type', '=', 'receivable')], limit=1)
        for line in statement.line_ids:
            line.process_reconciliation(new_aml_dicts=[{
                'debit': -line.amount if line.amount < 0 else 0,
                'credit': line.amount if line.amount > 0 else 0,
                'account_id': account.id}])

        statement.button_confirm_bank()
        self.assertEqual(statement.state, 'confirm')
        lines = self.env['account.move.line'].search([
            ('account_id', '=', self.journal.default_debit_account_id.id),
            ('statement_id', '=', statement.id)])
        reconcile = lines.mapped('full_reconcile_id')
        self.assertEqual(len(reconcile), 1)
        self.assertTrue(lines.mapped('matched_debit_ids'))
        self.assertTrue(lines.mapped('matched_credit_ids'))
        self.assertEqual(lines, reconcile.reconciled_line_ids)

        statement.button_draft()
        self.assertEqual(statement.state, 'open')
        self.assertFalse(lines.mapped('matched_debit_ids'))
        self.assertFalse(lines.mapped('matched_credit_ids'))
        self.assertFalse(lines.mapped('full_reconcile_id'))

    def test_import_adyen_credit_fees(self):
        self._test_statement_import(
            'account_bank_statement_import_adyen',
            'adyen_test_credit_fees.xlsx',
            'YOURCOMPANY_ACCOUNT 2016/8', self.journal)

    def _test_statement_import(
            self, module_name, file_name, statement_name, journal_id=False,
            local_account=False, start_balance=False, end_balance=False,
            transactions=None):
        """Test correct creation of single statement."""
        import_model = self.env['account.bank.statement.import']
        partner_bank_model = self.env['res.partner.bank']
        statement_model = self.env['account.bank.statement']
        statement_path = get_module_resource(
            module_name,
            'test_files',
            file_name
        )
        statement_file = open(statement_path, 'rb').read()
        bank_statement_id = import_model.create(
            dict(
                data_file=base64.b64encode(statement_file),
                filename=file_name,
            )
        )
        bank_statement_id.with_context(journal_id=journal_id.id).import_file()
        # Check wether bank account has been created:
        if local_account:
            bids = partner_bank_model.search(
                [('acc_number', '=', local_account)])
            self.assertTrue(
                bids,
                'Bank account %s not created from statement' % local_account
            )
        # statement name is account number + '-' + date of last 62F line:
        ids = statement_model.search([('name', '=', statement_name)])
        self.assertTrue(ids)

        statement_obj = ids[0]
        if start_balance:
            self.assertTrue(
                abs(statement_obj.balance_start - start_balance) < 0.00001,
                'Start balance %f not equal to expected %f' %
                (statement_obj.balance_start, start_balance)
            )
        if end_balance:
            self.assertTrue(
                abs(statement_obj.balance_end_real - end_balance) < 0.00001,
                'End balance %f not equal to expected %f' %
                (statement_obj.balance_end_real, end_balance)
            )
        # Maybe we need to test transactions?
        if transactions:
            for transaction in transactions:
                self._test_transaction(statement_obj, **transaction)
