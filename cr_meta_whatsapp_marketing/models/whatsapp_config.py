# -*- coding: utf-8 -*-
# Part of Creyox Technologies.

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
import json
import base64
from datetime import datetime

_logger = logging.getLogger(__name__)

class WhatsAppMarketingCampaign(models.Model):
    _name = 'whatsapp.marketing.campaign'
    _description = 'WhatsApp Marketing Campaign'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    in_queue_percentage = fields.Char(string='In Queue(%)')
    sent_percentage = fields.Char(string='Sent(%)')
    delivered_percentage = fields.Char(string='Delivered(%)')
    received_percentage = fields.Char(string='Received(%)')
    read_percentage = fields.Char(string='Read(%)')
    fail_percentage = fields.Char(string='Fail(%)')
    recipients_model_id = fields.Many2one("ir.model.fields",
        string="Recipients Model",
    )
    company_id = fields.Many2one(
        'res.company', string="Company", default=lambda self: self.env.company
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sent', 'Sent'),
    ], string='Status', default='draft', tracking=True)
    template_id = fields.Many2one(
        'whatsapp.template',
        string="Select Template",
        help="Template used for the message, if any"
    )