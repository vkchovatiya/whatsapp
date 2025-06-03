# -*- coding: utf-8 -*-

from odoo import models, api, _
from odoo.exceptions import UserError

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def action_send_whatsapp(self):
        """Open wizard to send CRM lead/opportunity via WhatsApp."""
        self.ensure_one()
        if not self.partner_id and (not self.phone and not self.mobile):
            raise UserError(_('Please set a phone number for the lead or associate it with a contact.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send by WhatsApp'),
            'res_model': 'whatsapp.crm.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('meta_whatsapp_crm.view_whatsapp_crm_wizard_form').id,
            'target': 'new',
            'context': {
                'default_lead_id': self.id,
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'default_phone': self.phone or self.mobile or (self.partner_id.phone if self.partner_id else False) or (self.partner_id.mobile if self.partner_id else False),
            },
        }