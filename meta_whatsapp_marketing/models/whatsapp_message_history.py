# -*- coding: utf-8 -*-

from odoo import models, fields, api

class WhatsAppMessageHistory(models.Model):
    _inherit = 'whatsapp.message.history'

    campaign_id = fields.Many2one(
        'whatsapp.marketing.campaign',
        string="Campaign",
        help="Associated marketing campaign"
    )
    config_id = fields.Many2one(
        'whatsapp.config',
        string="Provider",
        help="WhatsApp provider configuration"
    )
    date = fields.Datetime(
        string="Date",
        default=fields.Datetime.now,
        help="Date the message was sent or failed"
    )
    user = fields.Many2one(
        'res.users',
        string="User",
        help="User who sent the message"
    )
    author = fields.Char(
        string="Author",
        compute='_compute_author',
        store=True,
        help="Company and user who sent the message"
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Recipient",
        help="Recipient of the message"
    )
    number = fields.Char(
        string="WhatsApp Number",
        help="Phone number the message was sent to"
    )
    message = fields.Text(
        string="Message",
        help="Content of the message"
    )
    error = fields.Text(
        string="Error",
        help="Reason for message failure, if any"
    )

    @api.depends('user', 'user.company_id')
    def _compute_author(self):
        for record in self:
            if record.user and record.user.company_id:
                record.author = f"{record.user.company_id.name} - {record.user.name}"
            elif record.user:
                record.author = record.user.name
            else:
                record.author = False