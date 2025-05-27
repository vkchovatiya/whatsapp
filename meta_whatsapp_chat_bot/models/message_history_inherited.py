# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
import requests
import base64
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class WhatsAppsTemplate(models.Model):
    _inherit = 'whatsapp.message.history'

    chatbot_id = fields.Many2one(
        'chatbot.configuration',
        string="Chatbot",
    )
    current_script_id = fields.Many2one(
        'chatbot.script',string= 'script' 
    )