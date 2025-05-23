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

class WhatsAppMarketingListsContacts(models.Model):
    _name = 'whatsapp.messaging.lists.contacts'
    _description = 'WhatsApp Messaging Lists Contacts'
    _rec_name = 'name'

    name = fields.Char(string='Contact Name', required=True)
    whatsapp_number = fields.Char(string='WhatsApp Number', required=True)
    message_contacts = fields.Many2one('whatsapp.messaging.lists',string="Messaging List")
