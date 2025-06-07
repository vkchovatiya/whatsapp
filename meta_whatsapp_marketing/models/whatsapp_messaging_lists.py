# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
import json
import base64
from datetime import datetime

_logger = logging.getLogger(__name__)

class WhatsAppMarketingLists(models.Model):
    _name = 'whatsapp.messaging.lists'
    _description = 'WhatsApp Marketing Lists'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    lists_selected_model = fields.Char(string='Selected Model', store=True)
    msg_lists_recipients_model_id = fields.Many2one(
        'ir.model',
        string="Contact Type",
        help="Model for contacts (e.g., res_partner, whatsapp messaging lists contacts)",
        domain="[('model', 'in', ('res.partner', 'whatsapp.messaging.lists.contacts'))]"
    )
    # message_list_contacts = fields.One2many('whatsapp.messaging.lists.contacts','message_contacts',
    #     string="Message List Contacts",
    #     help="Select The Contacts")
    message_list_contacts_ids = fields.Many2many('whatsapp.messaging.lists.contacts',
        string="Message List Contacts",
        help="Select The Contacts")
    partner_ids = fields.Many2many(
        'res.partner',
        string="Partners",
        help="Select partner contacts"
    )

    @api.onchange('msg_lists_recipients_model_id')
    def _onchange_recipients_model(self):
        if self.msg_lists_recipients_model_id.model == 'whatsapp.messaging.lists.contacts':
            self.lists_selected_model = self.msg_lists_recipients_model_id.model
        if self.msg_lists_recipients_model_id.model == 'res.partner':
            self.lists_selected_model = self.msg_lists_recipients_model_id.model