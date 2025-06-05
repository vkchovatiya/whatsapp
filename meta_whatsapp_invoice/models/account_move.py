# -*- coding: utf-8 -*-

from odoo import models, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_send_whatsapp(self):
        """Open wizard to send invoice via WhatsApp."""
        self.ensure_one()
        if self.move_type not in ('out_invoice', 'out_refund'):
            raise UserError(_('This action is only available for customer invoices and credit notes.'))
        if not self.partner_id.phone and not self.partner_id.mobile:
            raise UserError(_('Please set a phone number for the customer.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send by WhatsApp'),
            'res_model': 'whatsapp.invoice.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('meta_whatsapp_invoice.view_whatsapp_invoice_wizard_form').id,
            'target': 'new',
            'context': {
                'default_invoice_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_phone': self.partner_id.phone or self.partner_id.mobile,
            },
        }