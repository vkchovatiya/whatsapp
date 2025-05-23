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

class WhatsAppMarketingLists(models.Model):
    _name = 'whatsapp.messaging.lists'
    _description = 'WhatsApp Marketing Lists'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    message_list_contacts = fields.One2many('whatsapp.messaging.lists.contacts','message_contacts',
        string="Message List Contacts",
        help="Select The Contacts")