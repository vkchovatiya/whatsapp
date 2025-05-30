# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class WhatsAppTemplateSale(models.Model):
    _inherit = 'whatsapp.template'

    # # Add sale-specific fields
    # sale_specific = fields.Boolean(
    #     string="Sale Specific Template",
    #     default=False,
    #     help="If checked, this template is specifically for sales use cases."
    # )
    # available = fields.Many2one(
    #     'ir.model',
    #     string="Available In",
    #     default=lambda self: self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1),
    #     help="Set to Sale Order to restrict this template for sales use."
    # )
    #
    # @api.constrains('sale_specific', 'available')
    # def _check_sale_specific(self):
    #     for template in self:
    #         if template.sale_specific and template.available.model != 'sale.order':
    #             raise UserError(_('Sale-specific templates must be available for Sale Order model only.'))
    #
    # def action_create_template(self):
    #     """Override to add sale-specific logic if needed."""
    #     self.ensure_one()
    #     # Ensure the template is linked to sale.order if sale_specific is True
    #     if self.sale_specific and self.available.model != 'sale.order':
    #         raise UserError(_('Sale-specific templates must be linked to Sale Order model.'))
    #     # Call the parent method to maintain existing functionality
    #     return super(WhatsAppTemplateSale, self).action_create_template()
    #
    # def action_resubmit_template(self):
    #     """Override to add sale-specific logic if needed."""
    #     self.ensure_one()
    #     if self.sale_specific and self.available.model != 'sale.order':
    #         raise UserError(_('Sale-specific templates must be linked to Sale Order model.'))
    #     return super(WhatsAppTemplateSale, self).action_resubmit_template()