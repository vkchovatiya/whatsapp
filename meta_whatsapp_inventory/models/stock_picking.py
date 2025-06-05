# -*- coding: utf-8 -*-

from odoo import models, api, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_send_whatsapp(self):
        """Open wizard to send inventory transfer via WhatsApp."""
        self.ensure_one()
        if not self.partner_id.phone and not self.partner_id.mobile:
            raise UserError(_('Please set a phone number for the contact.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send by WhatsApp'),
            'res_model': 'whatsapp.inventory.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('meta_whatsapp_inventory.view_whatsapp_inventory_wizard_form').id,
            'target': 'new',
            'context': {
                'default_picking_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_phone': self.partner_id.phone or self.partner_id.mobile,
            },
        }