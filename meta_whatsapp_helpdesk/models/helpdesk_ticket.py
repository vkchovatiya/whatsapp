# -*- coding: utf-8 -*-

from odoo import models, api, _
from odoo.exceptions import UserError

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    def action_send_whatsapp(self):
        """Open wizard to send Helpdesk ticket via WhatsApp."""
        self.ensure_one()
        if not self.partner_id.phone and not self.partner_id.mobile:
            raise UserError(_('Please set a phone number for the customer.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send by WhatsApp'),
            'res_model': 'whatsapp.helpdesk.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('meta_whatsapp_helpdesk.view_whatsapp_helpdesk_wizard_form').id,
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_phone': self.partner_id.phone or self.partner_id.mobile,
            },
        }